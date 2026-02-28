# -*- coding: utf-8 -*-
"""
tests/test_tts_style_prompt.py

CosyVoice2 风格提示词冒烟测试：确保 prefix 模式下不会把 instruction 当正文读出。
"""

from __future__ import annotations

import os

import pytest

from novel2comic.providers.tts.siliconflow_tts import (
	TTS_STYLE_ENDOPROMPT,
	build_input_text,
	_is_cosyvoice2_model,
)


class TestBuildInputText:
	"""build_input_text 字符串级防线：input 不以 instruction+\\n 开头，含 endofprompt。"""

	def test_cosyvoice2_prefix_downgrades_to_endofprompt(self):
		"""TTS_USE_STYLE_PROMPT=prefix 时，CosyVoice2 强制 endofprompt。"""
		os.environ["TTS_USE_STYLE_PROMPT"] = "prefix"
		try:
			input_text, effective_mode = build_input_text(
				"你好。",
				"兴奋",
				"prefix",
				model="FunAudioLLM/CosyVoice2-0.5B",
			)
			assert effective_mode == "endofprompt"
			assert not input_text.startswith("兴奋\n")
			assert TTS_STYLE_ENDOPROMPT in input_text
			assert input_text == f"兴奋{TTS_STYLE_ENDOPROMPT}你好。"
		finally:
			os.environ.pop("TTS_USE_STYLE_PROMPT", None)

	def test_input_contains_endofprompt_when_instruction_nonempty(self):
		"""instruction 非空时，input 必须含 <|endofprompt|>。"""
		input_text, _ = build_input_text("你好。", "兴奋", "endofprompt", model="FunAudioLLM/CosyVoice2-0.5B")
		assert TTS_STYLE_ENDOPROMPT in input_text
		assert "兴奋" in input_text
		assert input_text.endswith("你好。")

	def test_empty_instruction_returns_plain_text(self):
		"""instruction 为空时返回纯正文。"""
		input_text, mode = build_input_text("你好。", "", "endofprompt", model="FunAudioLLM/CosyVoice2-0.5B")
		assert input_text == "你好。"
		assert mode == "none"

	def test_neutral_empty_instruction(self):
		"""neutral 对应空 instruction 时也不传。"""
		input_text, mode = build_input_text("你好。", "", "endofprompt", model="FunAudioLLM/CosyVoice2-0.5B")
		assert input_text == "你好。"
		assert mode == "none"


class TestIsCosyVoice2:
	def test_detects_cosyvoice2(self):
		assert _is_cosyvoice2_model("FunAudioLLM/CosyVoice2-0.5B") is True
		assert _is_cosyvoice2_model("cosyvoice2") is True

	def test_rejects_other_models(self):
		assert _is_cosyvoice2_model("IndexTeam/IndexTTS-2") is False
		assert _is_cosyvoice2_model("") is False
