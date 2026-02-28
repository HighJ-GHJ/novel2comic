# -*- coding: utf-8 -*-
"""
novel2comic/stages/base.py

目的：
- 定义 Stage 的“接口形状”和运行上下文 StageContext。
- 让每个阶段都遵循同一种调用方式：run(paths, ctx)。

为什么需要：
- pipeline/orchestrator 只负责按顺序调度 stage，
  它不应该知道 stage 的内部细节。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from novel2comic.core.io import ChapterPaths


@dataclass
class StageContext:
	"""
	运行上下文：
	- novel_id/chapter_id：用于写 manifest/meta、shotscript/meta 等
	- chapter_title：可选（后续从 ingest/LLM 提取）
	- llm_provider_name/llm_model：记录生成计划时的模型信息（便于复现）
	"""
	novel_id: str
	chapter_id: str
	chapter_title: str = ""
	llm_provider_name: str = ""
	llm_model: str = ""


class Stage(Protocol):
	"""
	Stage 接口（协议）：
	- name：阶段名
	- run：执行该阶段，负责读写 ChapterPack 内的文件
	"""
	name: str

	def run(self, paths: ChapterPaths, ctx: StageContext) -> None:
		...
