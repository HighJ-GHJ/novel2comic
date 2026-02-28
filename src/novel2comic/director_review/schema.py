# -*- coding: utf-8 -*-
"""
novel2comic/director_review/schema.py

Director Review 数据契约：patch allowlist、校验规则。
"""

from __future__ import annotations

from typing import Any, Dict, List

# patch 允许修改的字段（存在才改）
PATCH_ALLOWLIST = frozenset({
	"gap_after_ms",
	"subtitle_tail_hold_ms",
	"emotion",
	"intensity",
	"pace",
	"motion",
	"overlays",
	"sfx_tags",
	"reasons",
})

# hard forbid：patch 不得修改这些目标字段（shot_id 在 patch 中仅作标识，允许存在）
FORBIDDEN_KEYS = frozenset({"text", "block_id", "order"})
PATCH_IDENTIFIER_KEYS = frozenset({"shot_id"})

# gap_after_ms 范围
GAP_AFTER_MS_MIN = 80
GAP_AFTER_MS_MAX = 1800

# subtitle_tail_hold_ms 范围
SUBTITLE_TAIL_HOLD_MS_MIN = 0
SUBTITLE_TAIL_HOLD_MS_MAX = 400


def _has_text_change(orig_shot: Dict, patched_shot: Dict) -> bool:
	"""检测 text 子树是否被修改。"""
	orig_text = orig_shot.get("text", {})
	patched_text = patched_shot.get("text", {})
	if orig_text != patched_text:
		return True
	return False


def validate_director_review(
	data: Dict[str, Any],
	original_shot_ids: List[str],
) -> tuple[bool, str]:
	"""
	校验 director_review 输出。
	Returns: (is_valid, error_message)
	"""
	if not isinstance(data, dict):
		return False, "director_review must be dict"

	patch = data.get("patch", {})
	if not isinstance(patch, dict):
		return False, "patch must be dict"

	shots = patch.get("shots", [])
	if not isinstance(shots, list):
		return False, "patch.shots must be list"

	# 不允许新增/删除 shots
	if len(shots) > len(original_shot_ids):
		return False, "patch must not add shots"

	orig_id_set = set(original_shot_ids)
	for item in shots:
		if not isinstance(item, dict):
			return False, "patch.shots[] must be dict"
		sid = item.get("shot_id")
		if sid and sid not in orig_id_set:
			return False, f"patch contains unknown shot_id: {sid}"
		for k in item:
			if k in PATCH_IDENTIFIER_KEYS:
				continue  # shot_id 仅作标识
			if k in FORBIDDEN_KEYS:
				return False, f"patch must not modify {k}"
			if k not in PATCH_ALLOWLIST:
				return False, f"patch field not in allowlist: {k}"

	return True, ""


def clamp_gap_after_ms(v: int) -> int:
	return max(GAP_AFTER_MS_MIN, min(GAP_AFTER_MS_MAX, v))


def clamp_subtitle_tail_hold_ms(v: int) -> int:
	return max(SUBTITLE_TAIL_HOLD_MS_MIN, min(SUBTITLE_TAIL_HOLD_MS_MAX, v))
