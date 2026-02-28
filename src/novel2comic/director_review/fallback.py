# -*- coding: utf-8 -*-
"""
novel2comic/director_review/fallback.py

LLM 失败时的规则 fallback：生成保守的 gap_after_ms。
"""

from __future__ import annotations

from typing import Any, Dict, List


def fallback_gap_after_ms(shot: Dict[str, Any], next_shot: Dict[str, Any] | None) -> int:
	"""
	根据 shot 文本结尾与 block 边界，返回保守的 gap_after_ms。
	"""
	raw = (shot.get("text") or {}).get("raw_text", "").rstrip()
	# 省略号结尾
	if raw.endswith("……"):
		return 600
	# 句末标点
	if raw.endswith(("。", "！", "？")):
		return 250
	# scene/block 边界
	if next_shot is not None and shot.get("block_id") != next_shot.get("block_id"):
		return 1200
	return 200


def apply_fallback_gaps(shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
	"""为所有 shot 应用 fallback gap_after_ms，返回新 shots（不修改原对象）。"""
	result = []
	for i, s in enumerate(shots):
		next_s = shots[i + 1] if i + 1 < len(shots) else None
		new_shot = dict(s)
		new_shot["gap_after_ms"] = fallback_gap_after_ms(s, next_s)
		result.append(new_shot)
	return result
