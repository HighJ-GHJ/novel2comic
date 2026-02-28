# -*- coding: utf-8 -*-
"""
novel2comic/core/manifest.py

目的：
- 定义 manifest.json 的数据结构与读写方法。
- 维护 ChapterPack 的“状态机”：每个 stage 跑完更新一次。
- 支持断点续跑：失败了也能从上次成功的 stage 继续。

manifest 的核心字段：
- status.stage      : 当前阶段（empty/ingested/segmented/...）
- status.done       : 已完成阶段的标记（便于审计/调试）
- status.failed     : 失败阶段标记（便于 UI/脚本处理）
- status.last_error : 最近一次错误信息（便于定位）

注意：
- 这里是“最小可用”版本，字段会随着项目推进逐步扩充。
- 但 stage 的理念不会变：一个阶段一个落盘状态。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


STAGES = [
	"empty",
	"ingested",
	"segmented",
	"planned",
	"tts_done",
	"aligned",
	"images_done",
	"rendered",
	"exported",
]


@dataclass
class Manifest:
	"""
	Manifest 是一个“可读写的结构体”，对应 manifest.json。
	"""
	schema_version: str
	meta: Dict[str, Any]
	status: Dict[str, Any]
	durations: Dict[str, Any]
	providers: Dict[str, Any]
	artifacts: Dict[str, Any]
	shots_index: Dict[str, Any]

	@property
	def stage(self) -> str:
		return self.status.get("stage", "empty")

	def set_stage(self, stage: str) -> None:
		if stage not in STAGES:
			raise ValueError(f"invalid stage: {stage}")

		self.status["stage"] = stage

	def mark_done(self, key: str) -> None:
		done = self.status.setdefault("done", [])
		if key in done:
			return

		done.append(key)

	def mark_failed(self, key: str, err: str) -> None:
		failed = self.status.setdefault("failed", [])
		if key not in failed:
			failed.append(key)

		self.status["last_error"] = err


def new_manifest(novel_id: str, chapter_id: str) -> Manifest:
	"""
	创建一个新的 Manifest（对应 ChapterPack v0.1 的最小字段集合）。
	"""
	return Manifest(
		schema_version="chapterpack.v0.1",
		meta={
			"project_id": "novel2comic",
			"novel_id": novel_id,
			"chapter_id": chapter_id,
			"created_at": "",
		},
		status={
			"stage": "empty",
			"done": [],
			"failed": [],
			"last_error": "",
		},
		durations={
			"audio_ms": 0,
			"video_ms": 0,
			"num_shots": 0,
		},
		providers={
			"llm": {},
			"tts": {"provider": "qwen-tts"},
			"image": {"provider": "comfyui"},
			"align": {"provider": "whisperx"},
		},
		artifacts={
			"shotscript": "shotscript.json",
			"audio_chapter_wav": "audio/chapter.wav",
			"subtitles_ass": "subtitles/chapter.ass",
			"subtitles_srt": "subtitles/chapter.srt",
			"draft_dir": "draft/jianying/",
			"final_mp4": "video/final.mp4",
		},
		shots_index={},
	)


def load_manifest(path: Path) -> Manifest:
	"""
	从 manifest.json 加载 Manifest。

	原则：
	- 容错：缺字段就用空 dict，避免轻易崩。
	- 但 schema_version 不匹配时，我们后面会加入升级策略（暂未做）。
	"""
	data = json.loads(path.read_text(encoding="utf-8"))

	return Manifest(
		schema_version=data.get("schema_version", ""),
		meta=data.get("meta", {}),
		status=data.get("status", {}),
		durations=data.get("durations", {}),
		providers=data.get("providers", {}),
		artifacts=data.get("artifacts", {}),
		shots_index=data.get("shots_index", {}),
	)


def save_manifest(path: Path, m: Manifest) -> None:
	"""
	把 Manifest 落盘到 manifest.json（可读的 indent=2）。
	"""
	data = {
		"schema_version": m.schema_version,
		"meta": m.meta,
		"status": m.status,
		"durations": m.durations,
		"providers": m.providers,
		"artifacts": m.artifacts,
		"shots_index": m.shots_index,
	}

	path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
