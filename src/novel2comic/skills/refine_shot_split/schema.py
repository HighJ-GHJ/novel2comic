# -*- coding: utf-8 -*-
"""
refine_shot_split/schema.py

- Shot：从 core.schemas 导入（共享契约）。
- Constraints、Patch：refine 专用，定义于此。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from novel2comic.core.schemas import Shot


# Re-export Shot for backward compatibility within skills
__all__ = ["Shot", "Constraints", "Patch"]


@dataclass
class Constraints:
	"""
	refine 的硬约束。

	min_shots/max_shots：
	- 目标范围（默认 60-120）
	- 短章会动态放宽 min_shots

	forbid_cross_scene_break：
	- 不允许跨 scene_break 合并/移动（建议默认 True）
	"""
	min_shots: int = 60
	max_shots: int = 120
	forbid_cross_scene_break: bool = True


@dataclass
class Patch:
	"""
	LLM 输出 patch 的容器。
	"""
	schema_version: str
	chapter_id: str
	constraints: Constraints
	ops: List[Dict[str, Any]]
