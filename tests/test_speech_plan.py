# -*- coding: utf-8 -*-
"""SpeechPlan validator 单元测试。"""

from __future__ import annotations

import pytest

from novel2comic.skills.speech_plan.validator import (
	validate_patch_shape,
	validate_shot_default,
	validate_segment,
	validate_patch,
)
from novel2comic.core.speech_schema import INTENSITY_VALUES, PACE_VALUES, PAUSE_MS_VALUES


def test_validate_patch_shape_valid():
	patch = {"schema_version": "speech_plan_patch.v0.1", "shots": []}
	validate_patch_shape(patch)


def test_validate_patch_shape_invalid_schema():
	with pytest.raises(ValueError, match="schema_version"):
		validate_patch_shape({"schema_version": "wrong", "shots": []})


def test_validate_shot_default_intensity_invalid():
	with pytest.raises(ValueError, match="intensity"):
		validate_shot_default({"intensity": 0.5})


def test_validate_shot_default_pace_invalid():
	with pytest.raises(ValueError, match="pace"):
		validate_shot_default({"pace": "super_fast"})


def test_validate_shot_default_pause_invalid():
	with pytest.raises(ValueError, match="pause_ms"):
		validate_shot_default({"pause_ms": 100})


def test_validate_segment_no_raw_text_modify():
	with pytest.raises(ValueError, match="raw_text"):
		validate_segment({"raw_text": "modified"})


def test_validate_patch_missing_shot_id():
	with pytest.raises(ValueError, match="missing"):
		validate_patch(
			{
				"schema_version": "speech_plan_patch.v0.1",
				"shots": [
					{"shot_id": "ch_0001_shot_0000", "default": {"intensity": 0.35, "pace": "normal", "pause_ms": 80}},
				],
			},
			["ch_0001_shot_0000", "ch_0001_shot_0001"],
		)
