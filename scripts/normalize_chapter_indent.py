# -*- coding: utf-8 -*-
"""
scripts/normalize_chapter_indent.py

这个脚本做什么：
- 修复章节 txt 的“段首缩进不一致”问题：
  1) 移除行首 TAB
  2) 归一化行首空白（普通空格/全角空格）
  3) 正文段落统一用两个全角空格（\u3000\u3000）缩进
  4) 章节标题行不缩进（如“第一章初入”“第十二章”）

使用：
python scripts/normalize_chapter_indent.py --dir output/xuanjianxianzu/chapters --inplace
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


CH_TITLE_RE = re.compile(r"^\s*第\s*([0-9]+|[零一二三四五六七八九十百千万两〇○]+)\s*(章|回|节)\b", re.UNICODE)


def is_chapter_title(line: str) -> bool:
	return bool(CH_TITLE_RE.match(line))


def normalize_lines(lines: list[str]) -> list[str]:
	out: list[str] = []
	for raw in lines:
		line = raw.rstrip("\n")

		# 空行直接保留
		if not line.strip():
			out.append("")
			continue

		# 去掉行首 TAB（TAB 是缩进不一致的头号元凶）
		line = re.sub(r"^\t+", "", line)

		# 如果是章节标题行，不做段首缩进
		if is_chapter_title(line):
			out.append(line.strip())
			continue

		# 统计行首空白（普通空格 + 全角空格）
		m = re.match(r"^([ \u3000]+)(.*)$", line)
		if m:
			body = m.group(2)
		else:
			body = line

		# 正文统一：两个全角空格缩进
		out.append("\u3000\u3000" + body.lstrip())

	return out


def main() -> None:
	ap = argparse.ArgumentParser()
	ap.add_argument("--dir", required=True, help="章节目录（包含 ch_*.txt）")
	ap.add_argument("--inplace", action="store_true", help="原地覆盖写回")
	args = ap.parse_args()

	base = Path(args.dir)
	files = sorted(base.glob("ch_*.txt"))

	if not files:
		raise SystemExit(f"no chapter files found in {base}")

	for p in files:
		lines = p.read_text(encoding="utf-8").splitlines()
		out_lines = normalize_lines(lines)
		text = "\n".join(out_lines).rstrip() + "\n"

		if args.inplace:
			p.write_text(text, encoding="utf-8")
		else:
			(p.parent / (p.stem + ".norm.txt")).write_text(text, encoding="utf-8")

	print(f"OK: normalized {len(files)} chapter files in {base}")


if __name__ == "__main__":
	main()
