# -*- coding: utf-8 -*-
"""
core/split_baseline.py

这个文件做什么：
- 纯规则的 baseline 切分：把章节文本切成 base_shots（稳定、可复现）。
- 规则目标：先得到“还算合理”的候选，再交给 refine_shot_split skill 语义矫正。

切分策略（简化但够用）：
1) 先按行清洗：去掉多余空白，但保留内容
2) 识别 scene_break：形如 '————' 的分隔线，作为强边界 shot(kind=scene_break)
3) 段落聚合：以空行或全角缩进 '　　' 开头作为段落起点
4) 段落再按句界切：。！？； 作为句界
5) 句子合并为 shot：min_chars 保底、soft_target 平衡、hard_cut 封顶
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from novel2comic.core.schemas import Shot


_SCENE_BREAK_RE = re.compile(r"^\s*—{3,}\s*$", flags=re.UNICODE)
_CHAPTER_TITLE_RE = re.compile(r"^\s*第[零一二三四五六七八九十百千两0-9]+章", flags=re.UNICODE)


@dataclass
class SplitConfig:
	min_chars: int = 80
	soft_target: int = 140
	hard_cut: int = 220


def _is_scene_break(line: str) -> bool:
	return _SCENE_BREAK_RE.match(line) is not None


def _is_chapter_title(line: str) -> bool:
	return _CHAPTER_TITLE_RE.match(line) is not None


def _normalize_line(line: str) -> str:
	# 不要过度清洗：保留中文全角缩进、引号等，只去掉行尾杂空白
	return line.rstrip()


def _split_sentences(text: str) -> List[str]:
	"""
	按句末标点切句，保留标点。
	"""
	sents = []
	buf = ""
	for ch in text:
		buf += ch
		if ch in "。！？；":
			sents.append(buf)
			buf = ""
	if buf.strip():
		sents.append(buf)
	return [s.strip() for s in sents if s.strip()]


def _gather_paragraphs(lines: List[str]) -> List[Tuple[str, str]]:
	"""
	把行聚合成段落。

	返回列表元素：(kind, text)
	- kind = "scene_break" or "paragraph"
	"""
	out = []
	cur = []

	def flush_paragraph():
		nonlocal cur
		if not cur:
			return
		text = "\n".join(cur).strip("\n")
		if text.strip():
			out.append(("paragraph", text))
		cur = []

	for raw in lines:
		line = _normalize_line(raw)
		if not line.strip():
			flush_paragraph()
			continue

		if _is_chapter_title(line):
			# chapter_clean 通常不会再带标题，但为了稳妥：遇到就当强边界
			flush_paragraph()
			continue

		if _is_scene_break(line):
			flush_paragraph()
			out.append(("scene_break", line.strip()))
			continue

		# 常见电子书段落以全角缩进开头：新段落起点
		if line.startswith("　　") and cur:
			flush_paragraph()

		cur.append(line)

	flush_paragraph()
	return out


def split_baseline(chapter_text: str, cfg: SplitConfig) -> List[Shot]:
	"""
	章节文本 -> base_shots（稳定输出）
	"""
	lines = chapter_text.splitlines()
	blocks = _gather_paragraphs(lines)

	shots: List[Shot] = []
	idx = 0

	def emit(text: str, kind: str) -> None:
		nonlocal idx
		text = text.strip()
		if not text:
			return
		shots.append(Shot(idx=idx, kind=kind, text=text))
		idx += 1

	for kind, text in blocks:
		if kind == "scene_break":
			emit(text, "scene_break")
			continue

		# paragraph：先切句，再按长度阈值合并成 shot
		sents = _split_sentences(text)
		if not sents:
			emit(text, "narration")
			continue

		buf = ""
		for s in sents:
			if not buf:
				buf = s
			else:
				buf += s

			# 软目标：达到 soft_target 就倾向切一镜
			if len(buf) >= cfg.soft_target:
				emit(buf, "mixed")
				buf = ""
				continue

			# 硬上限：超过 hard_cut 强制切
			if len(buf) >= cfg.hard_cut:
				emit(buf, "mixed")
				buf = ""
				continue

		# 收尾：不足 min_chars 也先吐出来（后面交给 LLM merge 更聪明）
		if buf.strip():
			emit(buf, "mixed")

	return shots
