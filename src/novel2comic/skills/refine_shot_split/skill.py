# -*- coding: utf-8 -*-
"""
refine_shot_split/skill.py

这个文件做什么：
- 把 refine 的完整流程封装成一个“skill”：
  1) build prompt
  2) 调用 LLM 得到 patch
  3) validate patch 形状/语法
  4) apply patch 得到 refined_shots
  5) 校验（文本守恒、shot 数范围、约束）
  6) 失败则回退 baseline

注意：
- 这里不关心你用 DeepSeek 还是 SiliconFlow，只依赖一个 llm_client 接口：
  llm_client.chat_json(system_prompt: str, user_prompt: str) -> dict
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .schema import Shot, Constraints
from .prompt import SYSTEM_PROMPT, build_user_prompt
from .validator import (
	validate_patch_shape,
	validate_ops_syntax,
	validate_constraints,
	validate_text_conservation,
	validate_count_range,
)
from .applier import apply_patch


@dataclass
class RefineResult:
	refined_shots: List[Shot]
	patch: Optional[Dict[str, Any]]
	used_fallback: bool
	error: str


class RefineShotSplitSkill:
	def __init__(self, llm_client: Any):
		self.llm_client = llm_client

	def run(self, chapter_id: str, base_shots: List[Shot], c: Constraints) -> RefineResult:
		user_prompt = build_user_prompt(chapter_id, base_shots, c)

		# 短章放宽 min/max：baseline 不足 min_shots 时，接受 baseline 数量
		effective_min = min(c.min_shots, len(base_shots))
		effective_max = max(c.max_shots, len(base_shots))

		try:
			patch = self.llm_client.chat_json(SYSTEM_PROMPT, user_prompt)

			validate_patch_shape(patch)
			validate_ops_syntax(patch["ops"])
			validate_constraints(patch["constraints"], c)

			refined = apply_patch(base_shots, patch, c)

			# 这两条是“绝对硬约束”
			validate_text_conservation(base_shots, refined)
			validate_count_range(refined, c, effective_min=effective_min, effective_max=effective_max)

			return RefineResult(refined_shots=refined, patch=patch, used_fallback=False, error="")

		except Exception as e:
			# 失败就回退 baseline，保证流水线不中断
			return RefineResult(refined_shots=base_shots, patch=None, used_fallback=True, error=str(e))
