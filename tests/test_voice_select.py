# -*- coding: utf-8 -*-
"""
tests/test_voice_select.py

多音色 voice 选择逻辑单元测试。
"""

from __future__ import annotations

from novel2comic.providers.tts.siliconflow_tts import (
	SiliconFlowTTSConfig,
	select_voice,
)


def _make_cfg(
	voice_narrator: str = "narrator",
	voice_male: str = "male",
	voice_female: str = "female",
) -> SiliconFlowTTSConfig:
	return SiliconFlowTTSConfig(
		api_key="x",
		base_url="https://x",
		model="x",
		voice_narrator=voice_narrator,
		voice_male=voice_male,
		voice_female=voice_female,
		sample_rate=24000,
		response_format="wav",
		timeout_s=60,
	)


class TestVoiceSelect:
	def test_narration_uses_narrator(self):
		cfg = _make_cfg()
		assert select_voice("narration", "male", cfg) == "narrator"
		assert select_voice("narration", "female", cfg) == "narrator"
		assert select_voice("narration", "unknown", cfg) == "narrator"

	def test_quote_male_uses_male(self):
		cfg = _make_cfg()
		assert select_voice("quote", "male", cfg) == "male"

	def test_quote_female_uses_female(self):
		cfg = _make_cfg()
		assert select_voice("quote", "female", cfg) == "female"

	def test_quote_unknown_uses_narrator(self):
		cfg = _make_cfg()
		assert select_voice("quote", "unknown", cfg) == "narrator"
