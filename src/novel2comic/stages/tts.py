# -*- coding: utf-8 -*-
"""
novel2comic/stages/tts.py

TTS 阶段：按 shot.speech 合成 audio/shots/<shot_id>.wav，拼接 chapter.wav。
- TTS 输入清洗（省略号移除、引号去除）
- 标点驱动停顿
- 多音色（narration/quote 按 gender_hint）
- segment 覆盖 pace
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from novel2comic.core.audio_utils import concat_wavs_with_pauses, wav_duration_ms
from novel2comic.core.io import ChapterPaths, find_project_root
from novel2comic.core.manifest import load_manifest, save_manifest
from novel2comic.core.speech_schema import PACE_TO_SPEED, cosyvoice2_short_instruction
from novel2comic.core.tts_utils import get_tail_pause_ms, normalize_tts_input
from novel2comic.core.tts_utils import SHOT_BOUNDARY_PAUSE_MS
from novel2comic.providers.tts.siliconflow_tts import load_siliconflow_tts, select_voice


def _synthesize_shot(tts_client, shot: dict) -> tuple[str, bytes | None, int, str | None]:
	"""
	合成单个 shot 的 wav。返回 (shot_id, wav_bytes, audio_ms, error)。
	使用 normalize_tts_input、标点停顿、segment pace 覆盖。
	"""
	shot_id = shot.get("shot_id", "")
	try:
		speech = shot.get("speech", {})
		default = speech.get("default", {})
		segments = speech.get("segments", [])
		shot_pace = default.get("pace", "normal")
		shot_emotion = default.get("emotion", "neutral")
		shot_intensity = default.get("intensity", 0.35)

		parts = []
		pauses_after = []

		for seg in segments:
			raw_text = seg.get("raw_text", "").strip()
			if not raw_text:
				continue

			kind = seg.get("kind", "narration")
			is_quote = kind == "quote"
			tts_clean, extra_pause_ms = normalize_tts_input(raw_text, is_quote=is_quote)
			if not tts_clean:
				continue

			# segment 覆盖 pace
			pace = seg.get("pace") or shot_pace
			speed = PACE_TO_SPEED.get(pace, 1.0)

			voice = select_voice(kind, seg.get("gender_hint", "unknown"), tts_client.cfg)
			# 硅基流动文档：instruction 需简短（~10 字），否则会被当正文读出
			emotion = seg.get("emotion") or shot_emotion
			intensity = seg.get("intensity") or shot_intensity
			# 二次防线：neutral + 低 intensity 时不传 style_prompt
			style = cosyvoice2_short_instruction(emotion) if not (emotion == "neutral" and (intensity or 0.35) <= 0.35) else ""
			style = (style or "").strip().replace("\n", "").replace("\r", "").replace("\t", "") or None

			for attempt in range(3):
				try:
					wav_bytes = tts_client.synthesize(
						tts_clean,
						voice=voice,
						style_prompt=style,
						speed=speed,
					)
					parts.append(wav_bytes)
					tail_ms = get_tail_pause_ms(raw_text) + extra_pause_ms
					pauses_after.append(tail_ms)
					break
				except Exception as e:
					if attempt == 2:
						err_msg = str(e)
						if hasattr(e, "args") and e.args:
							err_msg = f"{type(e).__name__}: {err_msg}"
						return (shot_id, None, 0, err_msg)
					time.sleep(1)

		if not parts:
			return (shot_id, None, 0, "no segments")

		# pauses_after 长度应为 len(parts)-1，最后一段后无静音
		if len(pauses_after) > len(parts):
			pauses_after = pauses_after[: len(parts) - 1]
		while len(pauses_after) < len(parts) - 1:
			pauses_after.append(SHOT_BOUNDARY_PAUSE_MS)

		combined = concat_wavs_with_pauses(parts, pauses_after)
		return (shot_id, combined, wav_duration_ms(combined), None)
	except Exception as e:
		return (shot_id, None, 0, f"{type(e).__name__}: {e}")


class TTSStage:
	name = "tts"

	def run(self, paths: ChapterPaths, ctx: object) -> None:
		shotscript_path = paths.effective_shotscript()
		if not shotscript_path.exists():
			raise FileNotFoundError(f"missing {shotscript_path}")

		data = json.loads(shotscript_path.read_text(encoding="utf-8"))
		shots = data.get("shots", [])
		if not shots:
			raise ValueError("shotscript has no shots")

		m = load_manifest(paths.manifest)
		if m.stage not in ("planned", "directed", "tts_done", "aligned", "rendered"):
			raise ValueError(f"TTS requires planned or directed stage, got {m.stage}")

		paths.audio_shots_dir.mkdir(parents=True, exist_ok=True)

		tts = load_siliconflow_tts(project_root=str(find_project_root()))

		try:
			chapter_parts = []
			shot_gaps = []
			synthesized_count = 0
			for shot in shots:
				shot_id = shot.get("shot_id", "")
				shot_wav = paths.audio_shots_dir / f"{shot_id}.wav"

				if shot_wav.exists() and m.shots_index.get(shot_id, {}).get("status") == "ok":
					chapter_parts.append(shot_wav.read_bytes())
					shot_gaps.append(shot.get("gap_after_ms", SHOT_BOUNDARY_PAUSE_MS))
					continue

				_, wav_bytes, audio_ms, err = _synthesize_shot(tts, shot)
				if err:
					m.shots_index[shot_id] = m.shots_index.get(shot_id, {}) | {
						"status": "error",
						"error": err[:500] if len(err) > 500 else err,
					}
					print(f"[WARN] TTS shot {shot_id} failed: {err[:200]}")
					save_manifest(paths.manifest, m)
					continue

				shot_wav.write_bytes(wav_bytes)
				m.shots_index[shot_id] = {
					"audio_path": f"audio/shots/{shot_id}.wav",
					"audio_ms": audio_ms,
					"status": "ok",
				}
				chapter_parts.append(wav_bytes)
				shot_gaps.append(shot.get("gap_after_ms", SHOT_BOUNDARY_PAUSE_MS))
				synthesized_count += 1
				# 每 5 个新合成落盘一次，减少 I/O（断点续跑）
				if synthesized_count % 5 == 0:
					save_manifest(paths.manifest, m)

			if chapter_parts:
				# 使用 per-shot gap_after_ms（director_review 或 fallback），无则用默认
				pauses = shot_gaps[:-1] if len(shot_gaps) > 1 else []
				chapter_wav = concat_wavs_with_pauses(chapter_parts, pauses)
				paths.audio_chapter_wav.write_bytes(chapter_wav)
				m.durations["audio_ms"] = wav_duration_ms(chapter_wav)
			m.set_stage("tts_done")
			m.mark_done("tts")
			save_manifest(paths.manifest, m)
		finally:
			tts.close()
