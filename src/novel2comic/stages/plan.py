# -*- coding: utf-8 -*-
"""
novel2comic/stages/plan.py

Plan 阶段：为 shots 补齐 speech 字段（default + segments）。
1) deterministic 按引号切 segments
2) 调用 SpeechPlanSkill 得到 patch
3) 应用 patch，落盘 shotscript
"""

from __future__ import annotations

import json
from pathlib import Path

from novel2comic.core.io import ChapterPaths, find_project_root
from novel2comic.core.manifest import load_manifest, save_manifest
from novel2comic.core.quote_splitter import split_quote_segments, QuoteSegment
from novel2comic.core.speech_schema import default_speech, default_segment
from novel2comic.stages.base import StageContext


def _ensure_speech_on_shots(shots: list[dict]) -> list[dict]:
	"""为每个 shot 补齐 speech（segments 由 quote_splitter 生成）。"""
	result = []
	for shot in shots:
		if shot.get("speech") and shot["speech"].get("segments"):
			result.append(shot)
			continue

		raw_text = shot.get("text", {}).get("raw_text", "")
		shot_id = shot.get("shot_id", "")

		segments_raw = split_quote_segments(raw_text)
		segments = []
		for i, seg in enumerate(segments_raw):
			seg_id = f"{shot_id}_seg_{i}"
			segments.append({
				"seg_id": seg_id,
				"kind": seg.kind,
				"raw_text": seg.raw_text,
				"speaker": "unknown",
				"gender_hint": "unknown",
				"tone": "neutral",
				"intensity": None,
				"pace": None,
			})

		default = default_speech()["default"]
		new_shot = dict(shot)
		new_shot["speech"] = {"default": default, "segments": segments}
		result.append(new_shot)
	return result


class PlanStage:
	name = "plan"

	def run(self, paths: ChapterPaths, ctx: StageContext) -> None:
		if not paths.shotscript.exists():
			raise FileNotFoundError(f"missing {paths.shotscript}")

		data = json.loads(paths.shotscript.read_text(encoding="utf-8"))
		shots = data.get("shots", [])

		if not shots:
			raise ValueError("shotscript has no shots")

		# 1) 补齐 segments（引号切分）
		shots = _ensure_speech_on_shots(shots)

		# 2) 调用 SpeechPlanSkill（LLM 可用时）
		m = load_manifest(paths.manifest)
		try:
			from novel2comic.providers.llm.siliconflow_client import load_siliconflow_client
			from novel2comic.skills.speech_plan.skill import SpeechPlanSkill

			llm = load_siliconflow_client(project_root=str(find_project_root()))
			try:
				skill = SpeechPlanSkill(llm)
				result = skill.run(ctx.chapter_id, shots)
				shots = result.shots
			finally:
				llm.close()
		except Exception as e:
			# 无 LLM 或失败：使用默认模板，但必须记录
			err_msg = f"SpeechPlan failed: {type(e).__name__}: {str(e)[:300]}"
			m.add_warning(err_msg)
			print(f"[WARN] {err_msg}")
			# 落盘到 logs/plan_error.json
			paths.logs_dir.mkdir(parents=True, exist_ok=True)
			import json as _json
			paths.logs_dir.joinpath("plan_error.json").write_text(
				_json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False, indent=2),
				encoding="utf-8",
			)
			save_manifest(paths.manifest, m)

		# 3) 落盘
		data["shots"] = shots
		paths.shotscript.write_text(
			json.dumps(data, ensure_ascii=False, indent=2),
			encoding="utf-8",
		)

		m.set_stage("planned")
		m.mark_done("plan")
		save_manifest(paths.manifest, m)
