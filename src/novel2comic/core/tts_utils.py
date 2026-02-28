# -*- coding: utf-8 -*-
"""
novel2comic/core/tts_utils.py

TTS 输入清洗与停顿策略。字幕保留原 raw_text，TTS 输入必须干净可朗读。
"""

from __future__ import annotations

import re
from typing import Tuple

# 标点驱动的停顿（ms）
PUNCTUATION_PAUSE_MS = {
	"，": 120,
	"、": 120,
	"；": 120,
	"：": 120,
	"。": 260,
	"！": 260,
	"？": 260,
	"…": 450,  # 单省略号
}
# 句中省略号（……/...）替换后额外停顿
ELLIPSIS_EXTRA_PAUSE_MS = 350
# 句末省略号额外停顿
ELLIPSIS_END_EXTRA_PAUSE_MS = 450
# shot 边界
SHOT_BOUNDARY_PAUSE_MS = 120
# scene_break（预留）
SCENE_BREAK_PAUSE_MS = 550

# 省略号模式（用于移除并计停顿）
_ELLIPSIS_PATTERNS = [
	(r"……", ELLIPSIS_END_EXTRA_PAUSE_MS),  # 中文省略号
	(r"\.\.\.", ELLIPSIS_EXTRA_PAUSE_MS),   # 英文三点
	(r"…", ELLIPSIS_EXTRA_PAUSE_MS),        # Unicode 省略号
]

# 中文引号（用于 quote 段去外层）
_QUOTE_OPEN = "\u201c"  # "
_QUOTE_CLOSE = "\u201d"  # "
_QUOTE_OPEN_ALT = "\u300c"  # 「
_QUOTE_CLOSE_ALT = "\u300d"  # 」


def normalize_tts_input(text: str, is_quote: bool = False) -> Tuple[str, int]:
	"""
	TTS 输入清洗。字幕仍用 raw_text，TTS 用此返回值。

	Returns:
		(clean_text, extra_pause_ms)
	"""
	if not text or not text.strip():
		return "", 0

	s = text.strip()
	# 1) quote 段：先去外层引号（避免引号参与后续处理）
	if is_quote:
		s = _strip_outer_quotes(s)
	# 2) 去掉段首缩进
	s = re.sub(r"^[\s\u3000\t]+", "", s)
	# 3) 换行归一：\n -> ，
	s = s.replace("\n", "，")
	s = s.replace("\r", "")
	# 4) 省略号：移除并累计 extra_pause_ms
	extra_pause_ms = 0
	for pat, pause in _ELLIPSIS_PATTERNS:
		matches = list(re.finditer(pat, s))
		for _ in matches:
			extra_pause_ms += pause
		s = re.sub(pat, "，", s)
	s = s.strip()
	if not s:
		return "", extra_pause_ms
	return s, extra_pause_ms


def _strip_outer_quotes(text: str) -> str:
	"""去掉 quote 段外层 "" 或 「」。"""
	s = text.strip()
	if s.startswith(_QUOTE_OPEN) and s.endswith(_QUOTE_CLOSE):
		return s[1:-1].strip()
	if s.startswith(_QUOTE_OPEN_ALT) and s.endswith(_QUOTE_CLOSE_ALT):
		return s[1:-1].strip()
	return s


def get_tail_pause_ms(text: str) -> int:
	"""
	根据末尾标点返回 tail_pause_ms。
	用于 segment 拼接时的静音时长。
	"""
	s = text.strip()
	if not s:
		return SHOT_BOUNDARY_PAUSE_MS
	last = s[-1]
	return PUNCTUATION_PAUSE_MS.get(last, SHOT_BOUNDARY_PAUSE_MS)


def quote_inner_text(raw_text: str) -> str:
	"""
	quote 段去掉外层引号后的内容（供 TTS 用）。
	字幕仍用 raw_text。
	"""
	return _strip_outer_quotes(raw_text)
