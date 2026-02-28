# -*- coding: utf-8 -*-
"""
novel2comic/stages/align.py

Align-Lite：按 shot wav 时长与 segments 比例生成 SRT/ASS。
quote 段字幕保留 ""。
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

from novel2comic.core.io import ChapterPaths
from novel2comic.core.manifest import load_manifest, save_manifest
from novel2comic.core.tts_utils import SHOT_BOUNDARY_PAUSE_MS


def _ms_to_srt_time(ms: int) -> str:
	h = ms // 3600000
	m = (ms % 3600000) // 60000
	s = (ms % 60000) // 1000
	frac = ms % 1000
	return f"{h:02d}:{m:02d}:{s:02d},{frac:03d}"


def _ms_to_ass_time(ms: int) -> str:
	h = ms // 3600000
	m = (ms % 3600000) // 60000
	s = (ms % 60000) // 1000
	cs = (ms % 1000) // 10
	return f"{h:01d}:{m:02d}:{s:02d}.{cs:02d}"


def _write_srt(entries: list[tuple[int, int, str]], path: Path) -> None:
	lines = []
	for i, (start_ms, end_ms, text) in enumerate(entries, 1):
		lines.append(str(i))
		lines.append(f"{_ms_to_srt_time(start_ms)} --> {_ms_to_srt_time(end_ms)}")
		lines.append(text)
		lines.append("")
	path.write_text("\n".join(lines), encoding="utf-8")


def _write_ass(entries: list[tuple[int, int, str]], path: Path) -> None:
	header = """[Script Info]
Title: novel2comic
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
	lines = [header]
	for start_ms, end_ms, text in entries:
		# 两行断行：每行约 20 字
		parts = []
		while len(text) > 20:
			parts.append(text[:20])
			text = text[20:]
		if text:
			parts.append(text)
		display = "\\N".join(parts)
		lines.append(f"Dialogue: 0,{_ms_to_ass_time(start_ms)},{_ms_to_ass_time(end_ms)},Default,,0,0,0,,{display}")
	path.write_text("\n".join(lines), encoding="utf-8")


class AlignStage:
	name = "align"

	def run(self, paths: ChapterPaths, ctx: object) -> None:
		shotscript_path = paths.effective_shotscript()
		if not shotscript_path.exists():
			raise FileNotFoundError(f"missing {shotscript_path}")

		data = json.loads(shotscript_path.read_text(encoding="utf-8"))
		shots = data.get("shots", [])
		m = load_manifest(paths.manifest)

		if m.stage not in ("tts_done", "aligned", "rendered"):
			raise ValueError(f"Align requires tts_done, got {m.stage}")

		entries = []
		cur_ms = 0

		for i, shot in enumerate(shots):
			shot_id = shot.get("shot_id", "")
			shot_wav_path = paths.audio_shots_dir / f"{shot_id}.wav"

			if not shot_wav_path.exists():
				continue

			with wave.open(str(shot_wav_path), "rb") as wf:
				frames = wf.getnframes()
				rate = wf.getframerate()
				shot_duration_ms = int(frames / rate * 1000)

			segments = shot.get("speech", {}).get("segments", [])
			if not segments:
				entries.append((cur_ms, cur_ms + shot_duration_ms, shot.get("text", {}).get("raw_text", "")))
				cur_ms += shot_duration_ms
			else:
				total_chars = sum(len(s.get("raw_text", "")) for s in segments)
				if total_chars == 0:
					cur_ms += shot_duration_ms
				else:
					for seg in segments:
						raw_text = seg.get("raw_text", "").strip()
						if not raw_text:
							continue
						seg_len = len(raw_text) / total_chars * shot_duration_ms
						end_ms = cur_ms + int(seg_len)
						entries.append((cur_ms, end_ms, raw_text))
						cur_ms = end_ms

			# 加上 shot 间停顿（与 chapter.wav 一致）
			gap = shot.get("gap_after_ms", SHOT_BOUNDARY_PAUSE_MS)
			cur_ms += gap

		paths.subtitles_dir.mkdir(parents=True, exist_ok=True)
		_write_srt(entries, paths.subtitles_srt)
		_write_ass(entries, paths.subtitles_ass)

		m.set_stage("aligned")
		m.mark_done("align")
		save_manifest(paths.manifest, m)
