# -*- coding: utf-8 -*-
"""
speech_plan/schema.py

SpeechPlan patch schema。LLM 只输出标签，不改写 raw_text。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from novel2comic.core.speech_schema import (
	INTENSITY_VALUES,
	PACE_VALUES,
	PAUSE_MS_VALUES,
	TONE_VALUES,
	GENDER_HINT_VALUES,
)


def validate_intensity(v: Any) -> bool:
	return v in INTENSITY_VALUES


def validate_pace(v: Any) -> bool:
	return v in PACE_VALUES


def validate_pause_ms(v: Any) -> bool:
	return v in PAUSE_MS_VALUES


def validate_tone(v: Any) -> bool:
	return v in TONE_VALUES


def validate_gender_hint(v: Any) -> bool:
	return v in GENDER_HINT_VALUES
