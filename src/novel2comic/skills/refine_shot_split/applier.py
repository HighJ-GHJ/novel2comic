# -*- coding: utf-8 -*-
"""
refine_shot_split/applier.py

这个文件做什么：
- 把 patch ops 应用到 base_shots 上，得到 refined_shots。
- 这是纯函数：输入 -> 输出，不读写文件、不调用模型。

实现原则：
- 先支持 merge / move_tail / split / tag 四种操作。
- 任何非法操作直接 raise，让上层回退 baseline。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .schema import Shot, Constraints


_SENT_SPLIT_RE = re.compile(r"(?<=[。！？；])|(?<=[”])", flags=re.UNICODE)


def split_sentences(text: str) -> List[str]:
	"""
	非常粗的句子切分：
	- 用中文句末标点与引号闭合作为边界
	- 目标是给 move_tail 用：把末尾 k 句挪走
	"""
	parts = []
	buf = ""

	for ch in text:
		buf += ch
		if _SENT_SPLIT_RE.search(ch):
			if buf.strip():
				parts.append(buf)
			buf = ""

	if buf.strip():
		parts.append(buf)

	return parts


def apply_patch(base_shots: List[Shot], patch: Dict[str, Any], c: Constraints) -> List[Shot]:
	shots = [Shot(idx=s.idx, kind=s.kind, text=s.text, tags=(s.tags or None)) for s in base_shots]

	for op in patch.get("ops", []):
		t = op["op"]

		if t == "merge":
			shots = _op_merge(shots, op, c)
			continue

		if t == "move_tail":
			shots = _op_move_tail(shots, op, c)
			continue

		if t == "split":
			shots = _op_split(shots, op)
			continue

		if t == "tag":
			shots = _op_tag(shots, op)
			continue

		raise ValueError(f"unknown op: {t}")

	# 重新编号 idx（refined idx），但保留原 baseline idx 的信息可以另存 tags。
	for i, s in enumerate(shots):
		s.idx = i

	return shots


def _find_by_idx(shots: List[Shot], idx: int) -> int:
	for i, s in enumerate(shots):
		if s.idx == idx:
			return i
	raise ValueError(f"idx not found: {idx}")


def _op_merge(shots: List[Shot], op: Dict[str, Any], c: Constraints) -> List[Shot]:
	start_idx = op["start_idx"]
	end_idx = op["end_idx"]
	if start_idx > end_idx:
		raise ValueError("merge: start_idx > end_idx")

	i0 = _find_by_idx(shots, start_idx)
	i1 = _find_by_idx(shots, end_idx)
	if i1 < i0:
		raise ValueError("merge: invalid range")

	# 必须是连续范围
	if (i1 - i0) != (end_idx - start_idx):
		raise ValueError("merge: range must be contiguous")

	if c.forbid_cross_scene_break:
		for s in shots[i0:i1 + 1]:
			if s.kind == "scene_break":
				raise ValueError("merge: cannot include scene_break")

	text = "".join(s.text for s in shots[i0:i1 + 1])
	kind = "mixed"
	merged = Shot(idx=start_idx, kind=kind, text=text, tags=None)

	return shots[:i0] + [merged] + shots[i1 + 1:]


def _op_move_tail(shots: List[Shot], op: Dict[str, Any], c: Constraints) -> List[Shot]:
	from_idx = op["from_idx"]
	to_idx = op["to_idx"]
	k = int(op["sentences"])

	if to_idx != from_idx + 1:
		raise ValueError("move_tail: to_idx must be from_idx+1")

	i = _find_by_idx(shots, from_idx)
	j = _find_by_idx(shots, to_idx)

	if j != i + 1:
		raise ValueError("move_tail: shots must be adjacent after prior ops")

	if c.forbid_cross_scene_break:
		if shots[i].kind == "scene_break" or shots[j].kind == "scene_break":
			raise ValueError("move_tail: cannot touch scene_break")

	sents = split_sentences(shots[i].text)
	if k <= 0 or k >= len(sents):
		raise ValueError("move_tail: invalid sentences count")

	tail = "".join(sents[-k:])
	head = "".join(sents[:-k])

	if not head.strip() or not tail.strip():
		raise ValueError("move_tail: would create empty shot")

	shots[i].text = head
	shots[j].text = tail + shots[j].text
	return shots


def _op_split(shots: List[Shot], op: Dict[str, Any]) -> List[Shot]:
	idx = op["idx"]
	at = op["at"]

	i = _find_by_idx(shots, idx)
	text = shots[i].text

	pos = text.find(at)
	if pos < 0:
		raise ValueError("split: 'at' not found in shot text")

	cut = pos + len(at)
	left = text[:cut]
	right = text[cut:]

	if not left.strip() or not right.strip():
		raise ValueError("split: would create empty shot")

	left_shot = Shot(idx=idx, kind=shots[i].kind, text=left, tags=shots[i].tags)
	right_shot = Shot(idx=idx + 1, kind=shots[i].kind, text=right, tags=shots[i].tags)

	return shots[:i] + [left_shot, right_shot] + shots[i + 1:]


def _op_tag(shots: List[Shot], op: Dict[str, Any]) -> List[Shot]:
	idx = op["idx"]
	tags = op.get("tags", {})

	i = _find_by_idx(shots, idx)
	old = shots[i].tags or {}
	old.update(tags)
	shots[i].tags = old
	return shots
