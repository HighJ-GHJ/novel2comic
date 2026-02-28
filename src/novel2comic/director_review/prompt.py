# -*- coding: utf-8 -*-
"""
novel2comic/director_review/prompt.py

导演审阅 prompt：shot 摘要化、严格 JSON 输出约束。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

RAW_TEXT_TRUNCATE = 120

SYSTEM_PROMPT = (
	"你是「导演/剪辑指导」，关注节奏、落点、转场、情绪曲线、可制作性。\n"
	"你只能输出一个 JSON 对象，不要 Markdown、不要解释性散文。\n"
	"patch-only：不得改写任何台词（text.raw_text/tts_text/subtitle_text），不得增删镜头，不得重排 order。\n"
	"输出必须包含 patch.shots 数组，哪怕为空 []。\n"
	"建议为每条 patch 提供 reasons（可解释）。\n"
	"gap_after_ms 控制该 shot 结束后的停顿（ms），范围 80–1800。句末、反转落点、场景跳转处可适当加长。\n"
)

OUTPUT_SCHEMA = """
输出格式（严格）：
{
  "meta": { "policy": { "patch_only": true } },
  "global_notes": ["整体节奏建议..."],
  "risks": [{ "shot_id": "s024", "level": "high", "issue": "..." }],
  "patch": {
    "shots": [
      {
        "shot_id": "ch_0001_shot_0002",
        "gap_after_ms": 800,
        "subtitle_tail_hold_ms": 160,
        "pace": "slow",
        "emotion": "sad",
        "intensity": "mid",
        "reasons": ["反转落点，需要观众消化"]
      }
    ]
  }
}
"""


def _shot_summary(shot: Dict[str, Any], max_chars: int = RAW_TEXT_TRUNCATE) -> Dict[str, Any]:
	"""单个 shot 的摘要（供 LLM 输入）。"""
	raw = (shot.get("text") or {}).get("raw_text", "")
	if len(raw) > max_chars:
		raw = raw[: max_chars - 3].rstrip() + "…"
	speech = shot.get("speech") or {}
	default = speech.get("default") or {}
	return {
		"shot_id": shot.get("shot_id"),
		"order": shot.get("order"),
		"block_id": shot.get("block_id"),
		"kind": default.get("mode", "narration"),
		"raw_text": raw,
		"emotion": default.get("emotion"),
		"intensity": default.get("intensity"),
		"pace": default.get("pace"),
	}


def build_user_prompt(chapter_id: str, shots: List[Dict[str, Any]]) -> str:
	"""构造 User Prompt：shot 摘要化 JSON。"""
	payload = {
		"chapter_id": chapter_id,
		"schema_version": "director_review.v0.1",
		"shots": [_shot_summary(s) for s in shots],
	}
	return (
		"任务：对镜头脚本做导演视角审阅，输出节奏与转场补丁（patch-only）。\n\n"
		+ OUTPUT_SCHEMA
		+ "\n输入数据(JSON)：\n"
		+ json.dumps(payload, ensure_ascii=False)
	)
