# -*- coding: utf-8 -*-
"""
scripts/split_novel_to_chapters.py

这个脚本做什么：
- 把“整本小说 txt”按章节标题切分成多个文件。
- 章节输出命名规则：
  - ch_<chapter_no>.txt：chapter_no 来自标题中的“第...章/回/节”
  - 例如：第一章 -> ch_0001.txt；第一千零九十七章 -> ch_1097.txt
- 如果开头存在“前言/简介/广告”等不属于任何章节的文本，会输出为 front_matter.txt
- 同时生成 chapters_index.json（按 chapter_no 排序）

为什么要这样做：
- 你的 txt 可能乱序（先出现 1097 再出现 1），不能用出现顺序当章节号。
- 以章节号为主键才能让后续 pipeline（ChapterPack、断点续跑、复现）稳定可靠。
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# 章节标题：第X章/回/节，X 支持中文数字与阿拉伯数字
# 例：第一章 初入；第12章；第一千零九十七章 大璺在身
_CHAPTER_RE = re.compile(
	r"^\s*第\s*([0-9]+|[零一二三四五六七八九十百千万两〇○]+)\s*(章|回|节)\s*(.*)\s*$",
	flags=re.UNICODE,
)

_SCENE_BREAK_RE = re.compile(r"^\s*—{3,}\s*$", flags=re.UNICODE)


@dataclass
class ChapterSeg:
	no: int
	title: str
	lines: List[str]


def _looks_like_ad_line(line: str) -> bool:
	s = line.strip()
	if not s:
		return False

	low = s.lower()
	if "http://" in low or "https://" in low:
		return True
	if "e-mail:" in low or "email:" in low:
		return True
	if "更多电子书" in s or ("电子书" in s and "访问" in s):
		return True
	if "下载" in s and ("访问" in s or "分享" in s):
		return True

	return False


def _clean_line(line: str) -> str:
	line = unescape(line)
	return line.rstrip()


def _normalize_blank_lines(lines: List[str]) -> List[str]:
	out: List[str] = []
	blank = 0

	for line in lines:
		if not line.strip():
			blank += 1
			if blank <= 1:
				out.append("")
			continue

		blank = 0
		out.append(line)

	while out and not out[0].strip():
		out.pop(0)
	while out and not out[-1].strip():
		out.pop()

	return out


def _cn_num_to_int(s: str) -> int:
	"""
	把中文数字（到“万”级）转为 int。
	支持：零一二三四五六七八九十百千两〇○万
	也支持纯阿拉伯数字。
	"""
	s = s.strip()
	if not s:
		return 0

	# 阿拉伯数字
	if s.isdigit():
		return int(s)

	digit = {
		"零": 0, "〇": 0, "○": 0,
		"一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
		"五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
	}
	unit = {"十": 10, "百": 100, "千": 1000, "万": 10000}

	total = 0
	section = 0   # 万以内的一段
	number = 0

	for ch in s:
		if ch in digit:
			number = digit[ch]
			continue

		if ch in unit:
			u = unit[ch]
			if u == 10000:
				# 万：把当前 section 乘万并累加到 total
				section += number
				if section == 0:
					section = 1
				total += section * 10000
				section = 0
				number = 0
				continue

			# 十百千
			if number == 0:
				# 例如“十二”开头的“十” -> 10
				number = 1
			section += number * u
			number = 0
			continue

		# 遇到非数字/单位字符，直接忽略（更鲁棒）
		continue

	return total + section + number


def _detect_chapter(line: str) -> Optional[Tuple[int, str]]:
	m = _CHAPTER_RE.match(line)
	if not m:
		return None

	no_raw = m.group(1)
	kind = m.group(2)
	name = m.group(3).strip()

	no = _cn_num_to_int(no_raw)
	# 标题保留原“第X章/回/节”形式（用于展示）
	title = f"第{no_raw}{kind}" + ((" " + name) if name else "")
	return no, title


def split_novel_to_chapters(text: str) -> Tuple[List[str], List[ChapterSeg]]:
	"""
	返回：(front_matter_lines, chapter_segments)
	"""
	raw_lines = text.splitlines()

	lines: List[str] = []
	for raw in raw_lines:
		line = _clean_line(raw)
		if _looks_like_ad_line(line):
			continue
		lines.append(line)

	lines = _normalize_blank_lines(lines)

	front: List[str] = []
	segs: List[ChapterSeg] = []

	cur_lines: List[str] = []
	cur_no: Optional[int] = None
	cur_title: str = ""

	def flush_cur() -> None:
		nonlocal cur_lines, cur_no, cur_title
		if not cur_lines:
			return
		if cur_no is None:
			front.extend(cur_lines)
		else:
			segs.append(ChapterSeg(no=cur_no, title=cur_title, lines=cur_lines))
		cur_lines = []

	for line in lines:
		ch = _detect_chapter(line)
		if ch:
			flush_cur()
			cur_no, cur_title = ch
			cur_lines = []
			continue

		cur_lines.append(line)

	flush_cur()
	front = _normalize_blank_lines(front)

	return front, segs


def write_outputs(out_dir: Path, novel_id: str, front: List[str], segs: List[ChapterSeg]) -> None:
	base = out_dir / novel_id / "chapters"
	base.mkdir(parents=True, exist_ok=True)

	# 先按章节号排序输出（关键）
	segs_sorted = sorted(segs, key=lambda x: x.no)

	# 动态宽度：保证 1097 这种不截断
	max_no = max([s.no for s in segs_sorted], default=0)
	width = max(4, len(str(max_no)))

	index = []

	# front matter
	if front:
		front_path = base / "front_matter.txt"
		front_path.write_text("\n".join(front).strip() + "\n", encoding="utf-8")
		index.append(
			{
				"type": "front_matter",
				"title": "front_matter",
				"file": "chapters/front_matter.txt",
				"chars": front_path.stat().st_size,
			}
		)

	# chapters
	seen: Dict[int, int] = {}
	for s in segs_sorted:
		# 处理重复章节号：同一个 no 出现多次，则追加 _dupN
		dup = seen.get(s.no, 0)
		seen[s.no] = dup + 1

		suffix = ""
		if dup > 0:
			suffix = f"_dup{dup}"

		fn = f"ch_{s.no:0{width}d}{suffix}.txt"
		p = base / fn
		content = "\n".join(s.lines).strip() + "\n"
		p.write_text(content, encoding="utf-8")

		index.append(
			{
				"type": "chapter",
				"no": s.no,
				"title": s.title,
				"file": str(Path("chapters") / fn),
				"chars": len(content),
				"lines": len(s.lines),
				"dup": dup,
			}
		)

	(base / "chapters_index.json").write_text(
		json.dumps(index, ensure_ascii=False, indent=2) + "\n",
		encoding="utf-8",
	)


def main() -> None:
	ap = argparse.ArgumentParser()
	ap.add_argument("--in_path", required=True, help="输入：整本小说 txt（UTF-8）")
	ap.add_argument("--out_dir", default="output", help="输出根目录")
	ap.add_argument("--novel_id", default="novel_demo", help="小说 ID，输出到 output/<novel_id>/chapters/")
	args = ap.parse_args()

	in_path = Path(args.in_path)
	text = in_path.read_text(encoding="utf-8", errors="ignore")

	front, segs = split_novel_to_chapters(text)
	write_outputs(Path(args.out_dir), args.novel_id, front, segs)

	print(f"OK: chapters={len(segs)} front_lines={len(front)}")
	print(f"Index: {Path(args.out_dir) / args.novel_id / 'chapters' / 'chapters_index.json'}")


if __name__ == "__main__":
	main()
