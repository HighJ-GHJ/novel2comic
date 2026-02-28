# -*- coding: utf-8 -*-
"""Pipeline 集成测试：prepare + run segment（无 LLM）。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


def test_prepare_and_run_segment(tmp_path: Path):
	"""prepare 创建 ChapterPack，run 执行 ingest+segment。"""
	# 创建模拟 chapters 目录
	chapters_dir = tmp_path / "book1" / "chapters"
	chapters_dir.mkdir(parents=True)
	ch_file = chapters_dir / "ch_0001.txt"
	ch_file.write_text(
		"　　陆江仙做了一个很长很长的梦，梦见田间种稻，梦见刀光剑影。\n"
		"　　\"将《太阴吐纳练气诀》交出。\"\n"
		"　　一道悦耳又冰冷的女声在耳边响起。\n",
		encoding="utf-8",
	)

	# novel2comic prepare
	from novel2comic.cli import cmd_prepare
	cmd_prepare(str(chapters_dir), novel_id="book1")

	# 验证 chapter_clean.txt 已创建
	pack_dir = tmp_path / "book1" / "ch_0001"
	assert (pack_dir / "text" / "chapter_clean.txt").exists()
	assert (pack_dir / "text" / "chapter_clean.txt").read_text(encoding="utf-8") == ch_file.read_text(encoding="utf-8")

	# novel2comic init 创建 manifest（prepare 只复制了 text，需要 init 或 run 会 ensure_dirs）
	# run 会先 ensure_dirs，但 ingest 需要 manifest。run 的 orchestrator 会 ensure_dirs，ingest 会创建 manifest 如果不存在。
	# 等等 - ingest 检查 text_clean 存在，然后创建/更新 manifest。所以我们需要先 init 来创建目录骨架。prepare 已经调用了 paths.ensure_dirs()，所以 text/ 等目录存在。但 manifest 不存在。ingest 的代码：if not paths.manifest.exists(): m = new_manifest(...); save_manifest(...)。所以 ingest 会创建 manifest。好。
	# 但 ingest 还需要 manifest 存在才能 load？不，ingest 是：如果没有 manifest 就创建。然后 load，更新 stage，save。所以第一次 run 时 manifest 不存在，ingest 会创建。好。

	# novel2comic run --until segment
	from novel2comic.pipeline.orchestrator import run_until
	from novel2comic.stages.base import StageContext

	ctx = StageContext(novel_id="book1", chapter_id="ch_0001")
	run_until(chapter_dir=str(pack_dir), ctx=ctx, until="segment")

	# 验证 shotscript.json 有 shots
	shotscript_path = pack_dir / "shotscript.json"
	assert shotscript_path.exists()
	data = json.loads(shotscript_path.read_text(encoding="utf-8"))
	assert "shots" in data
	assert len(data["shots"]) > 0
	assert data["meta"]["novel_id"] == "book1"
	assert data["meta"]["chapter_id"] == "ch_0001"

	# 验证 manifest
	manifest_path = pack_dir / "manifest.json"
	assert manifest_path.exists()
	m = json.loads(manifest_path.read_text(encoding="utf-8"))
	assert m["status"]["stage"] == "segmented"
	assert m["durations"]["num_shots"] == len(data["shots"])
