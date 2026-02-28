# -*- coding: utf-8 -*-
"""
tests/test_tts_utils.py

TTS 输入清洗与停顿策略单元测试。
"""

from __future__ import annotations

import pytest

from novel2comic.core.tts_utils import (
	get_tail_pause_ms,
	normalize_tts_input,
	quote_inner_text,
	SHOT_BOUNDARY_PAUSE_MS,
)


class TestNormalizeTtsInputEllipsis:
	def test_ellipsis_removed_and_extra_pause(self):
		clean, extra = normalize_tts_input("你好……世界", is_quote=False)
		assert "……" not in clean
		assert "…" not in clean
		assert extra > 0

	def test_english_ellipsis(self):
		clean, extra = normalize_tts_input("wait...", is_quote=False)
		assert "..." not in clean
		assert extra > 0

	def test_unicode_ellipsis(self):
		clean, extra = normalize_tts_input("结束…", is_quote=False)
		assert "…" not in clean
		assert extra > 0


class TestNormalizeTtsInputQuotes:
	def test_quote_strips_outer_quotes(self):
		# \u201c \u201d = ""
		clean, _ = normalize_tts_input("\u201c你好……\u201d", is_quote=True)
		assert not clean.startswith("\u201c")
		assert not clean.endswith("\u201d")
		assert "……" not in clean

	def test_narration_keeps_content(self):
		clean, _ = normalize_tts_input("旁白内容。", is_quote=False)
		assert "旁白内容" in clean
		assert clean.endswith("。")


class TestPunctuationPauseMap:
	def test_sentence_end_260ms(self):
		assert get_tail_pause_ms("结束。") == 260
		assert get_tail_pause_ms("真的！") == 260
		assert get_tail_pause_ms("是吗？") == 260

	def test_comma_120ms(self):
		assert get_tail_pause_ms("然后，") == 120

	def test_empty_fallback(self):
		assert get_tail_pause_ms("") == SHOT_BOUNDARY_PAUSE_MS


class TestQuoteInnerText:
	def test_strips_outer_quotes(self):
		assert quote_inner_text("\u201c你好\u201d") == "你好"
		assert quote_inner_text("\u300c你好\u300d") == "你好"
