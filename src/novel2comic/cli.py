# -*- coding: utf-8 -*-
"""
novel2comic/cli.py

目的：
- 提供项目的命令行入口。
- init：创建 ChapterPack 目录骨架（只建目录，不写业务数据）。
- run：调用 pipeline/orchestrator.py 运行若干 stage（支持 --until）。

注意：
- CLI 不做业务细节：不解析小说、不调用模型。
- CLI 只负责参数解析 + 把任务交给 orchestrator。

当前状态：
- run 已接入 orchestrator.run_until()。
- 目前 orchestrator 只实现 ingest/segment（plan 等以后补）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

STAGES = [
	"ingest",
	"segment",
	"plan",
	"tts",
	"align",
	"image",
	"render",
	"export",
]


def build_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(
		prog="novel2comic",
		description="Novel -> motion comic pipeline (ShotScript + ChapterPack)",
	)

	sub = p.add_subparsers(dest="cmd", required=True)

	initp = sub.add_parser("init", help="Create an empty ChapterPack directory skeleton")
	initp.add_argument("--chapter_dir", required=True, help="e.g. output/novel_001/ch_0001")

	prepp = sub.add_parser("prepare", help="从 chapters 目录批量创建 ChapterPack 并填充 chapter_clean.txt")
	prepp.add_argument("--chapters_dir", required=True, help="e.g. output/xuanjianxianzu/chapters")
	prepp.add_argument("--novel_id", default=None, help="小说 ID，缺省时从 chapters_dir 父目录名推断")
	prepp.add_argument("--chapter", default=None, help="仅处理指定章节，如 ch_0001；缺省则处理全部")

	runp = sub.add_parser("run", help="Run pipeline for an existing ChapterPack")
	runp.add_argument("--chapter_dir", required=True)
	runp.add_argument("--novel_id", default=None, help="小说 ID，缺省时从 chapter_dir 父目录名推断")
	runp.add_argument("--until", default="plan", choices=STAGES)

	return p


def cmd_init(chapter_dir: str) -> None:
	root = Path(chapter_dir)

	# ChapterPack 目录骨架：只保证路径约定存在。
	# 不在这里创建 manifest/shotscript，这些属于 stage 的工作。
	dirs = [
		root / "text",
		root / "audio" / "shots",
		root / "subtitles" / "align",
		root / "images" / "layers",
		root / "video",
		root / "draft" / "jianying",
		root / "logs",
	]

	for d in dirs:
		d.mkdir(parents=True, exist_ok=True)

	print(f"[OK] ChapterPack skeleton created: {root}")


def cmd_prepare(chapters_dir: str, novel_id: str | None = None, chapter: str | None = None) -> None:
	"""从 split_novel_to_chapters 输出创建 ChapterPack，复制 chapter_clean.txt。"""
	from novel2comic.core.io import chapter_paths

	ch_root = Path(chapters_dir)
	if not ch_root.exists():
		raise FileNotFoundError(f"chapters_dir not found: {ch_root}")

	resolved_novel_id = novel_id or (ch_root.parent.name if ch_root.parent else "novel_001")
	out_root = ch_root.parent  # output/<novel_id>/

	# 收集 ch_*.txt
	chapter_files = sorted(f for f in ch_root.glob("ch_*.txt"))
	if chapter:
		chapter_files = [f for f in chapter_files if f.stem == chapter]
		if not chapter_files:
			raise FileNotFoundError(f"chapter not found: {chapter}")

	for cf in chapter_files:
		chapter_name = cf.stem  # ch_0001
		pack_dir = out_root / chapter_name
		paths = chapter_paths(pack_dir)
		paths.ensure_dirs()
		dest = paths.text_clean
		dest.write_text(cf.read_text(encoding="utf-8"), encoding="utf-8")
		print(f"[OK] {chapter_name} -> {dest}")

	print(f"[OK] prepared {len(chapter_files)} chapter(s), novel_id={resolved_novel_id}")


def cmd_run(chapter_dir: str, until: str, novel_id: str | None = None) -> None:
	from novel2comic.pipeline.orchestrator import run_until
	from novel2comic.stages.base import StageContext

	chapter_path = Path(chapter_dir)
	chapter_name = chapter_path.name
	# novel_id：显式传入 > 从 chapter_dir 父目录推断（如 output/xuanjianxianzu/ch_0001 -> xuanjianxianzu）
	resolved_novel_id = novel_id or (chapter_path.parent.name if chapter_path.parent else "novel_001")

	ctx = StageContext(
		novel_id=resolved_novel_id,
		chapter_id=chapter_name,
	)

	run_until(chapter_dir=chapter_dir, ctx=ctx, until=until)


def main(argv=None) -> None:
	args = build_parser().parse_args(argv)

	if args.cmd == "init":
		cmd_init(args.chapter_dir)
		return

	if args.cmd == "prepare":
		cmd_prepare(args.chapters_dir, novel_id=args.novel_id, chapter=args.chapter)
		return

	if args.cmd == "run":
		cmd_run(args.chapter_dir, args.until, novel_id=args.novel_id)
		return
