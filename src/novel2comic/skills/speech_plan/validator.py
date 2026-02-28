# -*- coding: utf-8 -*-
"""
speech_plan/validator.py

SpeechPlan patch 强校验。不允许改 raw_text，枚举必须在允许集合内。
"""

from __future__ import annotations

from typing import Any, Dict, List

from novel2comic.core.speech_schema import (
	INTENSITY_VALUES,
	PACE_VALUES,
	PAUSE_MS_VALUES,
	TONE_VALUES,
	GENDER_HINT_VALUES,
	MODE_VALUES,
)


def validate_patch_shape(patch: Dict[str, Any]) -> None:
	if not isinstance(patch, dict):
		raise ValueError("patch must be a JSON object")
	if "schema_version" not in patch or patch["schema_version"] != "speech_plan_patch.v0.1":
		raise ValueError("invalid schema_version")
	if "shots" not in patch or not isinstance(patch["shots"], list):
		raise ValueError("patch must have shots array")


def validate_shot_default(d: Dict[str, Any]) -> None:
	if not isinstance(d, dict):
		raise ValueError("default must be object")
	if "intensity" in d and d["intensity"] is not None:
		if d["intensity"] not in INTENSITY_VALUES:
			raise ValueError(f"intensity must be in {INTENSITY_VALUES}")
	if "pace" in d and d["pace"] is not None:
		if d["pace"] not in PACE_VALUES:
			raise ValueError(f"pace must be in {PACE_VALUES}")
	if "pause_ms" in d and d["pause_ms"] is not None:
		if d["pause_ms"] not in PAUSE_MS_VALUES:
			raise ValueError(f"pause_ms must be in {PAUSE_MS_VALUES}")
	if "mode" in d and d["mode"] is not None:
		if d["mode"] not in MODE_VALUES:
			raise ValueError(f"mode must be in {MODE_VALUES}")


def validate_segment(seg: Dict[str, Any]) -> None:
	if not isinstance(seg, dict):
		raise ValueError("segment must be object")
	if "speaker" in seg and seg["speaker"] is not None:
		if not isinstance(seg["speaker"], str):
			raise ValueError("speaker must be string")
	if "gender_hint" in seg and seg["gender_hint"] is not None:
		if seg["gender_hint"] not in GENDER_HINT_VALUES:
			raise ValueError(f"gender_hint must be in {GENDER_HINT_VALUES}")
	if "tone" in seg and seg["tone"] is not None:
		if seg["tone"] not in TONE_VALUES:
			raise ValueError(f"tone must be in {TONE_VALUES}")
	if "intensity" in seg and seg["intensity"] is not None:
		if seg["intensity"] not in INTENSITY_VALUES:
			raise ValueError(f"intensity must be in {INTENSITY_VALUES}")
	if "pace" in seg and seg["pace"] is not None:
		if seg["pace"] not in PACE_VALUES:
			raise ValueError(f"pace must be in {PACE_VALUES}")
	# 不允许改 raw_text
	if "raw_text" in seg:
		raise ValueError("patch must not modify raw_text")


def validate_patch(patch: Dict[str, Any], expected_shot_ids: List[str]) -> None:
	validate_patch_shape(patch)
	seen = set()
	for shot in patch["shots"]:
		if not isinstance(shot, dict):
			raise ValueError("each shot must be object")
		sid = shot.get("shot_id")
		if sid not in expected_shot_ids:
			raise ValueError(f"unknown shot_id: {sid}")
		if sid in seen:
			raise ValueError(f"duplicate shot_id: {sid}")
		seen.add(sid)
		if "default" in shot:
			validate_shot_default(shot["default"])
		for seg in shot.get("segments", []):
			validate_segment(seg)

	if len(seen) != len(expected_shot_ids):
		missing = set(expected_shot_ids) - seen
		raise ValueError(f"missing shot_ids: {missing}")
