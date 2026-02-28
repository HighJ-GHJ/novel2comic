# -*- coding: utf-8 -*-
"""Skills 模块测试（无 LLM 调用）。"""

from __future__ import annotations

from novel2comic.core.schemas import Shot
from novel2comic.skills.refine_shot_split.schema import Constraints
from novel2comic.skills.refine_shot_split.validator import (
	validate_count_range,
	validate_text_conservation,
	normalize_text,
	concat_text,
)
from novel2comic.skills.refine_shot_split.applier import apply_patch


class TestValidator:
	def test_validate_count_range_relaxed(self):
		"""短章时 effective_min 放宽，应通过。"""
		shots = [Shot(i, "mixed", f"文本{i}。") for i in range(20)]
		c = Constraints(min_shots=60, max_shots=120)
		# 20 在 [20, 120] 内应通过
		validate_count_range(shots, c, effective_min=20, effective_max=120)

	def test_validate_text_conservation(self):
		base = [Shot(0, "mixed", "你好。"), Shot(1, "mixed", "世界！")]
		refined = [Shot(0, "mixed", "你好。"), Shot(1, "mixed", "世界！")]
		validate_text_conservation(base, refined)

	def test_validate_text_conservation_fail(self):
		base = [Shot(0, "mixed", "原文")]
		refined = [Shot(0, "mixed", "改写了")]
		import pytest
		with pytest.raises(ValueError, match="text conservation"):
			validate_text_conservation(base, refined)


class TestApplier:
	def test_op_tag(self):
		shots = [Shot(0, "mixed", "文本。")]
		patch = {"ops": [{"op": "tag", "idx": 0, "tags": {"emotion": "calm"}}]}
		result = apply_patch(shots, patch, Constraints())
		assert result[0].tags == {"emotion": "calm"}

	def test_op_split(self):
		shots = [Shot(0, "mixed", "前半。后半。")]
		patch = {"ops": [{"op": "split", "idx": 0, "at": "前半。"}]}
		result = apply_patch(shots, patch, Constraints())
		assert len(result) == 2
		assert result[0].text == "前半。"
		assert result[1].text == "后半。"
