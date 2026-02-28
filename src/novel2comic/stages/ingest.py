# -*- coding: utf-8 -*-
"""
novel2comic/stages/ingest.py

目的：
- “输入准备阶段”：确保 ChapterPack 基础文件存在，并把 manifest 置为 ingested。
- 当前最小实现只做校验：要求 text/chapter_clean.txt 必须已经存在。

为什么这样设计：
- ingest 的职责应当非常纯粹：准备输入、更新状态。
- 文本清洗/拆章的复杂逻辑我们后面会单独做（也可以成为另一个 stage 或脚本）。

输入：
- ChapterPack/text/chapter_clean.txt（必须存在）

输出：
- ChapterPack/manifest.json（如不存在则创建，并更新 stage=ingested）
"""

from __future__ import annotations

from novel2comic.core.io import ChapterPaths
from novel2comic.core.manifest import load_manifest, save_manifest, new_manifest
from novel2comic.stages.base import StageContext


class IngestStage:
	name = "ingest"

	def run(self, paths: ChapterPaths, ctx: StageContext) -> None:
		paths.ensure_dirs()

		# 没有 manifest 就创建一个最小 manifest。
		if not paths.manifest.exists():
			m = new_manifest(ctx.novel_id, ctx.chapter_id)
			save_manifest(paths.manifest, m)

		# 最小校验：clean 文本必须存在，否则后续 segment 根本没法跑。
		if not paths.text_clean.exists():
			raise FileNotFoundError(
				f"missing {paths.text_clean} "
				"(请先把清洗后的文本放到 ChapterPack/text/chapter_clean.txt)"
			)

		# 更新状态：ingested
		m = load_manifest(paths.manifest)
		m.set_stage("ingested")
		m.mark_done("ingest")
		save_manifest(paths.manifest, m)
