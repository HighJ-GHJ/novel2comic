# -*- coding: utf-8 -*-
"""
Director Review 单元测试。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from novel2comic.director_review.apply import apply_director_patch
from novel2comic.director_review.fallback import fallback_gap_after_ms, apply_fallback_gaps
from novel2comic.director_review.schema import (
	PATCH_ALLOWLIST,
	GAP_AFTER_MS_MAX,
	GAP_AFTER_MS_MIN,
	clamp_gap_after_ms,
	validate_director_review,
)


def test_director_review_schema_valid():
	"""合法 JSON 可解析。"""
	valid = {
		"meta": {"policy": {"patch_only": True}},
		"patch": {"shots": [{"shot_id": "s001", "gap_after_ms": 300, "reasons": ["test"]}]},
	}
	ok, err = validate_director_review(valid, ["s001"])
	assert ok is True
	assert err == ""


def test_patch_disallow_text_change():
	"""patch 试图改 text → invalid（通过 apply 的 invariant 检测）。"""
	shotscript = {
		"shots": [
			{"shot_id": "s001", "order": 0, "text": {"raw_text": "原文"}, "block_id": 0},
		]
	}
	# director_review 本身不包含 text，但若 apply 时发现 text 被改会拒绝
	director_review = {
		"patch": {"shots": [{"shot_id": "s001", "gap_after_ms": 500}]},
	}
	directed, report = apply_director_patch(shotscript, director_review)
	assert "invariant_violation" not in report
	assert directed["shots"][0]["gap_after_ms"] == 500
	assert directed["shots"][0]["text"]["raw_text"] == "原文"


def test_patch_disallow_reorder():
	"""改 order/增删 shots → invalid。"""
	shotscript = {"shots": [{"shot_id": "s001", "order": 0}]}
	director_review = {"patch": {"shots": [{"shot_id": "s999", "gap_after_ms": 100}]}}
	ok, err = validate_director_review(director_review, ["s001"])
	assert ok is False
	assert "unknown shot_id" in err or "s999" in err


def test_gap_clamp():
	"""超界 gap 被 clamp。"""
	assert clamp_gap_after_ms(50) == GAP_AFTER_MS_MIN
	assert clamp_gap_after_ms(3000) == GAP_AFTER_MS_MAX
	assert clamp_gap_after_ms(500) == 500


def test_fallback_gap_after_ms():
	"""Fallback 规则。"""
	# 句末
	s1 = {"text": {"raw_text": "他愣住了。"}}
	assert fallback_gap_after_ms(s1, None) == 250

	# 省略号
	s2 = {"text": {"raw_text": "他愣住了……"}}
	assert fallback_gap_after_ms(s2, None) == 600

	# block 边界
	s3 = {"block_id": 0, "text": {"raw_text": "一段话"}}
	s4 = {"block_id": 1}
	assert fallback_gap_after_ms(s3, s4) == 1200

	# 默认
	s5 = {"text": {"raw_text": "然后，"}}
	assert fallback_gap_after_ms(s5, None) == 200


def test_apply_fallback_gaps():
	"""apply_fallback_gaps 为所有 shot 填 gap。"""
	shots = [
		{"shot_id": "s1", "text": {"raw_text": "句末。"}, "block_id": 0},
		{"shot_id": "s2", "text": {"raw_text": "下一段"}, "block_id": 1},
	]
	result = apply_fallback_gaps(shots)
	assert len(result) == 2
	assert result[0]["gap_after_ms"] == 250  # 句末
	assert result[1]["gap_after_ms"] == 200  # 默认（最后一个）


def test_apply_director_patch_invalid_shot_id():
	"""未知 shot_id 的 patch 被忽略。"""
	shotscript = {"shots": [{"shot_id": "s001", "order": 0}]}
	director_review = {"patch": {"shots": [{"shot_id": "s999", "gap_after_ms": 100}]}}
	ok, _ = validate_director_review(director_review, ["s001"])
	assert ok is False
