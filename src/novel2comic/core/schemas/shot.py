# -*- coding: utf-8 -*-
"""
novel2comic/core/schemas/shot.py

Shot：分镜单元的基础数据结构，baseline split 与 refine 的共享契约。
- core 定义，skills 使用。
- 不依赖任何业务层（LLM、TTS 等）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Shot:
	"""
	一个 shot 单元（动态漫画分镜单位）。

	idx：
	- baseline 阶段的稳定序号（0..N-1）
	- refine patch 里所有操作都用 idx 引用它

	kind：
	- baseline 阶段给的粗分类（narration/dialogue/scene_break/mixed）
	- 只是提示，后续可以由 LLM tag 覆盖

	text：
	- 原文片段（必须文本守恒）
	"""
	idx: int
	kind: str
	text: str
	tags: Optional[Dict[str, Any]] = None
