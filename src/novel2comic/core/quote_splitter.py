# -*- coding: utf-8 -*-
"""
novel2comic/core/quote_splitter.py

Deterministic 按中文引号 "" 切分 raw_text 为 segments。
- narration：引号外
- quote：引号内（字幕保留引号）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


# 中文引号对：(open, close)
_QUOTE_PAIRS = [
	("\u201c", "\u201d"),  # ""
	("\u300c", "\u300d"),  # 「」
]


@dataclass
class QuoteSegment:
	"""单个 segment：narration 或 quote。"""
	kind: str  # "narration" | "quote"
	raw_text: str  # quote 段含引号
	seg_idx: int  # shot 内序号


def split_quote_segments(raw_text: str) -> List[QuoteSegment]:
	"""
	按中文引号 "" 或 「」 切分 raw_text。
	多段引号产生多个 quote segment，顺序保持原文。
	"""
	segments: List[QuoteSegment] = []
	seg_idx = 0
	pos = 0
	text = raw_text

	while pos < len(text):
		# 找下一个引号开始（取最早出现的）
		open_pos = -1
		open_ch = ""
		close_ch = ""
		for o, c in _QUOTE_PAIRS:
			i = text.find(o, pos)
			if i >= 0 and (open_pos < 0 or i < open_pos):
				open_pos = i
				open_ch = o
				close_ch = c

		if open_pos < 0:
			# 无更多引号，剩余全是 narration
			tail = text[pos:].strip()
			if tail:
				segments.append(QuoteSegment(kind="narration", raw_text=tail, seg_idx=seg_idx))
				seg_idx += 1
			break

		# 引号前的 narration
		if open_pos > pos:
			narration = text[pos:open_pos].strip()
			if narration:
				segments.append(QuoteSegment(kind="narration", raw_text=narration, seg_idx=seg_idx))
				seg_idx += 1

		# 找匹配的闭合引号
		close_pos = text.find(close_ch, open_pos + 1)
		if close_pos < 0:
			# 未闭合，当作 narration 处理
			segments.append(QuoteSegment(kind="narration", raw_text=text[open_pos:].strip(), seg_idx=seg_idx))
			seg_idx += 1
			break

		# quote 段：含引号
		quote_text = text[open_pos : close_pos + 1]
		segments.append(QuoteSegment(kind="quote", raw_text=quote_text, seg_idx=seg_idx))
		seg_idx += 1
		pos = close_pos + 1

	return segments
