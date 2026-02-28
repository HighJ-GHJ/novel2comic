# -*- coding: utf-8 -*-
"""
refine_shot_split/validator.py

这个文件做什么：
- 对 LLM 输出的 patch 做强校验。
- 任何不合规：直接报错，让上层回退 baseline。

为什么必须强校验：
- LLM 偶尔会越界、胡写字段、偷偷改字。
- 我们要的是“可控、可回归”的工程行为，不是一次性作文。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .schema import Shot, Constraints


def normalize_text(s: str) -> str:
	"""
	文本守恒校验用的规范化：
	- 去掉所有空白字符（含全角空格、换行）
	- 这样能容忍切分导致的换行/空格差异，但不能容忍改字
	"""
	return re.sub(r"\s+", "", s, flags=re.UNICODE)


def concat_text(shots: List[Shot]) -> str:
	return "".join(s.text for s in shots)


def validate_patch_shape(patch: Dict[str, Any]) -> None:
	if not isinstance(patch, dict):
		raise ValueError("patch must be a JSON object")

	for k in ("schema_version", "chapter_id", "constraints", "ops"):
		if k not in patch:
			raise ValueError(f"missing key: {k}")

	if patch["schema_version"] != "shotsplit_patch.v0.1":
		raise ValueError("unsupported schema_version")

	if not isinstance(patch["ops"], list):
		raise ValueError("ops must be a list")


def validate_ops_syntax(ops: List[Dict[str, Any]]) -> None:
	allowed = {"merge", "split", "move_tail", "tag"}

	for op in ops:
		if not isinstance(op, dict):
			raise ValueError("each op must be an object")

		t = op.get("op")
		if t not in allowed:
			raise ValueError(f"invalid op type: {t}")


def validate_constraints(c_from_patch: Dict[str, Any], c: Constraints) -> None:
	"""
	patch 里可能带 constraints，但我们不信它，仍以本地为准。
	这里主要检查 patch 没乱写（可选）。
	"""
	if not isinstance(c_from_patch, dict):
		raise ValueError("constraints must be an object")

	for k in ("min_shots", "max_shots", "forbid_cross_scene_break"):
		if k not in c_from_patch:
			raise ValueError(f"constraints missing: {k}")

	# 不强制相等，但至少类型要对
	if not isinstance(c_from_patch["min_shots"], int):
		raise ValueError("constraints.min_shots must be int")
	if not isinstance(c_from_patch["max_shots"], int):
		raise ValueError("constraints.max_shots must be int")
	if not isinstance(c_from_patch["forbid_cross_scene_break"], bool):
		raise ValueError("constraints.forbid_cross_scene_break must be bool")


def validate_text_conservation(base_shots: List[Shot], refined_shots: List[Shot]) -> None:
	base = normalize_text(concat_text(base_shots))
	refined = normalize_text(concat_text(refined_shots))

	if base != refined:
		raise ValueError("text conservation failed: refined text differs from baseline")


def validate_count_range(
	refined_shots: List[Shot],
	c: Constraints,
	effective_min: int | None = None,
	effective_max: int | None = None,
) -> None:
	"""
	校验 shot 数量在允许范围内。
	短章时调用方传入 effective_min/effective_max 放宽约束。
	"""
	n = len(refined_shots)
	min_s = effective_min if effective_min is not None else c.min_shots
	max_s = effective_max if effective_max is not None else c.max_shots
	if n < min_s or n > max_s:
		raise ValueError(f"shot count out of range: {n} not in [{min_s},{max_s}]")
