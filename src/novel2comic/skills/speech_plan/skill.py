# -*- coding: utf-8 -*-
"""
speech_plan/skill.py

SpeechPlanSkill：patch-only，LLM 只输出标签不改写原文。
失败回退到默认有声书模板。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .prompt import SYSTEM_PROMPT, build_user_prompt
from .validator import validate_patch
from .applier import apply_patch
from novel2comic.core.speech_schema import default_speech, default_segment


@dataclass
class SpeechPlanResult:
	shots: List[Dict[str, Any]]
	used_fallback: bool
	error: str


class SpeechPlanSkill:
	def __init__(self, llm_client: Any):
		self.llm_client = llm_client

	def run(self, chapter_id: str, shots: List[Dict[str, Any]]) -> SpeechPlanResult:
		"""
		shots: 每个 shot 需含 shot_id, text.raw_text, speech.default, speech.segments。
		speech.segments 由 quote_splitter 生成（seg_id, kind, raw_text）。
		"""
		expected_ids = [s["shot_id"] for s in shots]

		try:
			user_prompt = build_user_prompt(chapter_id, shots)
			patch = self.llm_client.chat_json(SYSTEM_PROMPT, user_prompt)
			validate_patch(patch, expected_ids)
			result_shots = apply_patch(shots, patch)
			return SpeechPlanResult(shots=result_shots, used_fallback=False, error="")
		except Exception as e:
			# 回退：用默认模板填充
			result_shots = []
			for shot in shots:
				new_shot = dict(shot)
				segments = shot.get("speech", {}).get("segments", [])
				default = default_speech()["default"].copy()
				seg_out = [
					default_segment(seg.get("seg_id", f"{shot['shot_id']}_seg_{i}"), seg.get("kind", "narration"), seg.get("raw_text", ""))
					for i, seg in enumerate(segments)
				]
				new_shot["speech"] = {"default": default, "segments": seg_out}
				result_shots.append(new_shot)
			return SpeechPlanResult(shots=result_shots, used_fallback=True, error=str(e))
