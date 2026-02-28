# -*- coding: utf-8 -*-
"""Core 模块单元测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from novel2comic.core.schemas import Shot
from novel2comic.core.split_baseline import SplitConfig, split_baseline
from novel2comic.core.io import chapter_paths
from novel2comic.core.manifest import new_manifest, load_manifest, save_manifest


class TestShot:
	"""Shot 来自 core，不依赖 skills。"""

	def test_shot_creation(self):
		s = Shot(idx=0, kind="narration", text="测试文本")
		assert s.idx == 0
		assert s.kind == "narration"
		assert s.text == "测试文本"
		assert s.tags is None


class TestSplitBaseline:
	def test_basic_split(self):
		text = "　　第一段。第二段！第三段？"
		cfg = SplitConfig(min_chars=10, soft_target=50, hard_cut=100)
		shots = split_baseline(text, cfg)
		assert len(shots) >= 1
		assert all(isinstance(s, Shot) for s in shots)
		concat = "".join(s.text for s in shots)
		assert "第一段" in concat and "第二段" in concat

	def test_scene_break(self):
		text = "　　前文。\n————\n　　后文。"
		cfg = SplitConfig(min_chars=2, soft_target=20, hard_cut=50)
		shots = split_baseline(text, cfg)
		kinds = [s.kind for s in shots]
		assert "scene_break" in kinds


class TestManifest:
	def test_new_and_save_load(self):
		with tempfile.TemporaryDirectory() as d:
			p = Path(d) / "manifest.json"
			m = new_manifest("novel_1", "ch_0001")
			save_manifest(p, m)
			loaded = load_manifest(p)
			assert loaded.meta["novel_id"] == "novel_1"
			assert loaded.meta["chapter_id"] == "ch_0001"
			assert loaded.stage == "empty"
