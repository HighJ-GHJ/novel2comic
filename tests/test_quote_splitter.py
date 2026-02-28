# -*- coding: utf-8 -*-
"""Quote segment splitter 单元测试。"""

from __future__ import annotations

import pytest

from novel2comic.core.quote_splitter import split_quote_segments, QuoteSegment


def test_no_quotes():
	text = "纯叙述文字，没有引号。"
	segs = split_quote_segments(text)
	assert len(segs) == 1
	assert segs[0].kind == "narration"
	assert segs[0].raw_text == text


def test_single_quote():
	# 使用中文双引号 U+201C U+201D
	text = "他说：\u201c你好世界\u201d。然后走了。"
	segs = split_quote_segments(text)
	assert len(segs) == 3
	assert segs[0].kind == "narration"
	assert "他说" in segs[0].raw_text
	assert segs[1].kind == "quote"
	assert "你好世界" in segs[1].raw_text
	assert segs[1].raw_text.startswith("\u201c")
	assert segs[2].kind == "narration"


def test_multiple_quotes():
	text = "甲说：\u201c第一句\u201d。乙说：\u201c第二句\u201d。"
	segs = split_quote_segments(text)
	assert len(segs) >= 3
	quotes = [s for s in segs if s.kind == "quote"]
	assert len(quotes) == 2


def test_quote_preserves_quotes():
	text = "他说：\u201c保留引号\u201d。"
	segs = split_quote_segments(text)
	quote_seg = next(s for s in segs if s.kind == "quote")
	assert "保留引号" in quote_seg.raw_text
	assert quote_seg.raw_text.startswith("\u201c")
	assert quote_seg.raw_text.endswith("\u201d")
