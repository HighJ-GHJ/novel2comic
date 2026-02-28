# -*- coding: utf-8 -*-
"""
novel2comic/director_review/apply.py

Patch 合并器：apply_director_patch，严格 patch-only，不变量校验。
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from novel2comic.director_review.schema import (
	PATCH_ALLOWLIST,
	clamp_gap_after_ms,
	clamp_subtitle_tail_hold_ms,
	validate_director_review,
)


def apply_director_patch(
	shotscript: Dict[str, Any],
	director_review: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
	"""
	将 director_review.patch 合并到 shotscript，返回 (shotscript_directed, report)。
	report 记录 ignored/rejected 原因。
	"""
	shots = shotscript.get("shots", [])
	orig_ids = [s.get("shot_id", "") for s in shots]
	shot_map = {s["shot_id"]: i for i, s in enumerate(shots) if s.get("shot_id")}

	is_valid, err = validate_director_review(director_review, orig_ids)
	if not is_valid:
		return shotscript, {"valid": False, "error": err, "ignored": [], "applied": 0}

	patch_shots = director_review.get("patch", {}).get("shots", [])
	report: Dict[str, Any] = {"valid": True, "ignored": [], "applied": 0}

	result_shots = [copy.deepcopy(s) for s in shots]
	orig_text_hashes = [hash(str(s.get("text"))) for s in shots]

	for item in patch_shots:
		sid = item.get("shot_id")
		if not sid or sid not in shot_map:
			report["ignored"].append({"shot_id": sid, "reason": "unknown shot_id"})
			continue

		idx = shot_map[sid]
		target = result_shots[idx]

		for key, val in item.items():
			if key in ("reasons", "shot_id"):
				continue  # reasons 不写入 shot；shot_id 仅作标识
			if key not in PATCH_ALLOWLIST:
				report["ignored"].append({"shot_id": sid, "reason": f"field not in allowlist: {key}"})
				continue

			if key == "gap_after_ms":
				if isinstance(val, (int, float)):
					target[key] = clamp_gap_after_ms(int(val))
				else:
					report["ignored"].append({"shot_id": sid, "reason": f"gap_after_ms invalid: {type(val)}"})
			elif key == "subtitle_tail_hold_ms":
				if isinstance(val, (int, float)):
					target[key] = clamp_subtitle_tail_hold_ms(int(val))
				else:
					report["ignored"].append({"shot_id": sid, "reason": f"subtitle_tail_hold_ms invalid: {type(val)}"})
			else:
				target[key] = val

		report["applied"] += 1

	# 不变量校验
	if len(result_shots) != len(shots):
		return shotscript, report | {"invariant_violation": "shot count changed"}

	for i, (orig, res) in enumerate(zip(shots, result_shots)):
		if hash(str(res.get("text"))) != orig_text_hashes[i]:
			return shotscript, report | {"invariant_violation": f"text changed in shot {i}"}
		if res.get("order") != orig.get("order"):
			return shotscript, report | {"invariant_violation": f"order changed in shot {i}"}

	result = dict(shotscript)
	result["shots"] = result_shots
	return result, report
