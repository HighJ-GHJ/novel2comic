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

from dataclasses import dataclass
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
	"""向上查找含 .env 的项目根目录，供 LLM/TTS 等加载配置。"""
	p = Path(start or Path.cwd()).resolve()
	while p != p.parent:
		if (p / ".env").exists():
			return p
		p = p.parent
	return p


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
	)
