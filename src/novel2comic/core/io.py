# -*- coding: utf-8 -*-
"""
novel2comic/core/io.py

目的：
- 统一管理 ChapterPack 的路径约定（哪些文件放哪里）。
- 统一创建 ChapterPack 的目录骨架（ensure_dirs）。

为什么要做这层：
- 避免各个 stage 到处手写路径字符串导致耦合和混乱。
- 一旦 ChapterPack 目录结构要调整，只改这里。

ChapterPack 约定（v0.1）核心路径：
- manifest.json           : 状态机与断点续跑信息
- shotscript.json         : ShotScript v0.1（镜头脚本）
- text/chapter_raw.txt    : 原始文本（可选）
- text/chapter_clean.txt  : 清洗后的文本（Segment/Plan 输入）
- logs/                   : 日志（例如 llm.jsonl）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_PROJECT_ROOT_ENV = "NOVEL2COMIC_PROJECT_ROOT"
_ENV_FILE_ENV = "NOVEL2COMIC_ENV_FILE"
_PROJECT_ROOT_MARKERS = (
	"pyproject.toml",
	".git",
)
_PACKAGE_MARKER = ("src", "novel2comic")


def _normalize_search_path(start: str | Path | None) -> Path:
	p = Path(start or Path.cwd()).expanduser().resolve()
	return p.parent if p.is_file() else p


def _looks_like_project_root(path: Path) -> bool:
	if any((path / marker).exists() for marker in _PROJECT_ROOT_MARKERS):
		return True
	return (path / _PACKAGE_MARKER[0] / _PACKAGE_MARKER[1]).is_dir()


def find_project_root(start: str | Path | None = None) -> Path:
	"""
	向上查找项目根目录。

	定位顺序：
	1. `NOVEL2COMIC_PROJECT_ROOT`
	2. 显式传入的 start
	3. 当前模块所在目录
	4. 当前工作目录

	项目根目录不再依赖 `.env` 是否存在，避免换机器或首次拉仓库时解析失败。
	"""
	env_root = os.environ.get(_PROJECT_ROOT_ENV, "").strip()
	if env_root:
		return _normalize_search_path(env_root)

	candidates: list[Path] = []
	if start is not None:
		candidates.append(_normalize_search_path(start))
	candidates.append(_normalize_search_path(__file__))
	candidates.append(_normalize_search_path(Path.cwd()))

	seen: set[Path] = set()
	for candidate in candidates:
		p = candidate
		while True:
			if p in seen:
				break
			seen.add(p)
			if _looks_like_project_root(p):
				return p
			if p == p.parent:
				break
			p = p.parent

	# 回退到当前文件的仓库结构推导结果：.../src/novel2comic/core/io.py -> repo root
	return Path(__file__).resolve().parents[3]


def find_env_file(start: str | Path | None = None) -> Path:
	"""
	返回应使用的 `.env` 路径。

	可通过 `NOVEL2COMIC_ENV_FILE` 显式覆盖，否则默认取 `<project_root>/.env`。
	"""
	env_file = os.environ.get(_ENV_FILE_ENV, "").strip()
	if env_file:
		return Path(env_file).expanduser().resolve()
	return find_project_root(start) / ".env"


@dataclass(frozen=True)
class ChapterPaths:
	"""
	把 ChapterPack 内部常用文件路径集中在一个结构体里。

	注意：
	- 只存路径，不做读写。
	- ensure_dirs() 负责创建目录骨架。
	"""
	root: Path
	manifest: Path
	shotscript: Path
	text_raw: Path
	text_clean: Path
	logs_dir: Path

	# 音频与字幕（TTS/Align 产出）
	audio_dir: Path
	audio_shots_dir: Path
	audio_chapter_wav: Path
	subtitles_dir: Path
	subtitles_srt: Path
	subtitles_ass: Path
	video_dir: Path
	video_preview_mp4: Path

	# Director Review 产出
	director_dir: Path
	director_review_json: Path
	shotscript_directed: Path

	# Image Stage 产出
	images_shots_dir: Path
	images_anchors_dir: Path

	def shot_image_rel_path(self, shot_id: str) -> str:
		"""manifest 中记录的 shot 图片相对路径。"""
		return f"images/shots/shot_{shot_id}.png"

	def char_anchor_path(self, char_id: str) -> Path:
		"""角色锚点路径：images/anchors/characters/<char_id>/anchor.png"""
		return self.images_anchors_dir / "characters" / char_id / "anchor.png"

	def style_anchor_path(self) -> Path:
		"""风格锚点路径：images/anchors/style_anchor.png"""
		return self.images_anchors_dir / "style_anchor.png"

	def effective_shotscript(self) -> Path:
		"""TTS/Align/Render 应读取的 shotscript：directed 存在则用，否则用原版。"""
		return self.shotscript_directed if self.shotscript_directed.exists() else self.shotscript

	def ensure_dirs(self) -> None:
		"""
		创建 ChapterPack 目录骨架。

		原则：
		- 只 mkdir，不写任何业务文件。
		- 重复执行必须安全（exist_ok=True）。
		"""
		dirs = [
			self.root / "text",
			self.root / "audio" / "shots",
			self.root / "subtitles" / "align",
			self.root / "images" / "layers",
			self.root / "images" / "shots",
			self.root / "images" / "anchors" / "characters",
			self.root / "images" / "anchors" / "scenes",
			self.root / "video",
			self.root / "draft" / "jianying",
			self.root / "logs",
			self.root / "director",
		]

		for d in dirs:
			d.mkdir(parents=True, exist_ok=True)


def chapter_paths(chapter_dir: str | Path) -> ChapterPaths:
	"""
	根据 chapter_dir 生成 ChapterPaths。

	注意：
	- 这里不创建目录；目录创建由 ensure_dirs() 做。
	"""
	root = Path(chapter_dir)

	return ChapterPaths(
		root=root,
		manifest=root / "manifest.json",
		shotscript=root / "shotscript.json",
		text_raw=root / "text" / "chapter_raw.txt",
		text_clean=root / "text" / "chapter_clean.txt",
		logs_dir=root / "logs",
		audio_dir=root / "audio",
		audio_shots_dir=root / "audio" / "shots",
		audio_chapter_wav=root / "audio" / "chapter.wav",
		subtitles_dir=root / "subtitles",
		subtitles_srt=root / "subtitles" / "chapter.srt",
		subtitles_ass=root / "subtitles" / "chapter.ass",
		video_dir=root / "video",
		video_preview_mp4=root / "video" / "preview.mp4",
		director_dir=root / "director",
		director_review_json=root / "director" / "director_review.json",
		shotscript_directed=root / "shotscript.directed.json",
		images_shots_dir=root / "images" / "shots",
		images_anchors_dir=root / "images" / "anchors",
	)