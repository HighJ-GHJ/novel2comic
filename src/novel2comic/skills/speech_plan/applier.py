# -*- coding: utf-8 -*-
"""
speech_plan/applier.py

应用 patch 到 shots，只改 speech 字段，不碰 raw_text。
"""

from __future__ import annotations

from typing import Any, Dict, List

from novel2comic.core.speech_schema import default_speech, default_segment


def apply_patch(
	shots: List[Dict[str, Any]],
	patch: Dict[str, Any],
) -> List[Dict[str, Any]]:
	"""
	将 patch 应用到 shots。shots 需含 shot_id, text.raw_text, 以及 segments（由 quote_splitter 生成）。
	patch 含 shots[].default 与 shots[].segments 的标签覆盖。
	"""
	patch_by_id = {s["shot_id"]: s for s in patch.get("shots", [])}
	result = []

	for shot in shots:
		shot_id = shot["shot_id"]
		raw_text = shot.get("text", {}).get("raw_text", "")
		existing_segments = shot.get("speech", {}).get("segments", [])

		# 若已有 segments 结构，保留；否则用 patch 或空
		patch_shot = patch_by_id.get(shot_id, {})

		# 构建 default
		default = default_speech()["default"].copy()
		if "default" in patch_shot and isinstance(patch_shot["default"], dict):
			for k, v in patch_shot["default"].items():
				if v is not None:
					default[k] = v

		# 构建 segments
		segments = []
		for i, seg in enumerate(existing_segments):
			seg_id = seg.get("seg_id", f"{shot_id}_seg_{i}")
			kind = seg.get("kind", "narration")
			raw = seg.get("raw_text", "")

			seg_out = default_segment(seg_id, kind, raw)
			# 从 patch 中找对应 segment
			patch_segs = [s for s in patch_shot.get("segments", []) if s.get("seg_id") == seg_id]
			if patch_segs:
				ps = patch_segs[0]
				for k in ("speaker", "gender_hint", "tone", "intensity", "pace"):
					if k in ps and ps[k] is not None:
						seg_out[k] = ps[k]
			segments.append(seg_out)

		speech = {"default": default, "segments": segments}
		new_shot = dict(shot)
		new_shot["speech"] = speech
		result.append(new_shot)

	return result
