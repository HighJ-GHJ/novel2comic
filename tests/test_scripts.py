# -*- coding: utf-8 -*-
"""Scripts 集成测试。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_split_novel_to_chapters_novel_id(tmp_path: Path):
	"""split_novel_to_chapters 使用 --novel_id 输出到正确路径。"""
	in_file = tmp_path / "novel.txt"
	in_file.write_text(
		"第一章 初入\n\n　　正文第一段。\n\n第二章 李家\n\n　　正文第二段。",
		encoding="utf-8",
	)

	result = subprocess.run(
		[sys.executable, "scripts/split_novel_to_chapters.py", "--in_path", str(in_file), "--out_dir", str(tmp_path), "--novel_id", "test_novel"],
		cwd=Path(__file__).resolve().parent.parent,
		capture_output=True,
		text=True,
	)
	assert result.returncode == 0, result.stderr

	chapters_dir = tmp_path / "test_novel" / "chapters"
	assert chapters_dir.exists()
	assert (chapters_dir / "ch_0001.txt").exists()
	assert (chapters_dir / "ch_0002.txt").exists()
	assert (chapters_dir / "chapters_index.json").exists()
