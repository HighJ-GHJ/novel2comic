# -*- coding: utf-8 -*-
"""Core 模块单元测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from novel2comic.core.schemas import Shot
from novel2comic.core.split_baseline import SplitConfig, split_baseline
from novel2comic.core.io import chapter_paths, find_env_file, find_project_root
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

class TestPathResolution:
	def test_find_project_root_without_dotenv(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
		root = tmp_path / "portable_repo"
		(root / "src" / "novel2comic").mkdir(parents=True)
		(root / "pyproject.toml").write_text("[project]\nname = \"portable\"\n", encoding="utf-8")
		nested = root / "output" / "demo" / "ch_0001"
		nested.mkdir(parents=True)

		monkeypatch.delenv("NOVEL2COMIC_PROJECT_ROOT", raising=False)
		monkeypatch.delenv("NOVEL2COMIC_ENV_FILE", raising=False)

		assert find_project_root(nested) == root.resolve()
		assert find_env_file(nested) == (root / ".env").resolve()

	def test_env_override_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
		override_root = tmp_path / "server_checkout"
		override_root.mkdir()
		override_env = tmp_path / "shared" / "novel2comic.local.env"
		override_env.parent.mkdir(parents=True)

		monkeypatch.setenv("NOVEL2COMIC_PROJECT_ROOT", str(override_root))
		monkeypatch.setenv("NOVEL2COMIC_ENV_FILE", str(override_env))

		assert find_project_root(tmp_path / "elsewhere") == override_root.resolve()
		assert find_env_file(tmp_path / "elsewhere") == override_env.resolve()
