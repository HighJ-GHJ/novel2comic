# -*- coding: utf-8 -*-
"""
speech_plan/prompt.py

SpeechPlan LLM prompt。严格 JSON 输出，patch-only，不改写原文。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


SYSTEM_PROMPT = (
	"你是「有声书朗读规划器」。你只能输出一个 JSON 对象，不要解释，不要 Markdown。\n"
	"你绝对不能改写、删减、添加任何原文字符。只输出标签（emotion/intensity/pace/pause_ms/speaker/tone 等）。\n"
	"intensity 必须是 0.15/0.35/0.55/0.75 之一。\n"
	"pace 必须是 slow/normal/fast 之一。\n"
	"pause_ms 必须是 0/80/150/250 之一。\n"
	"tone 必须是 stern/gentle/playful/anxious/angry/weak/authoritative/neutral 之一。\n"
	"gender_hint 必须是 male/female/unknown 之一。\n"
)


def build_user_prompt(chapter_id: str, shots_with_segments: List[Dict[str, Any]]) -> str:
	"""
	shots_with_segments: 每个 shot 含 shot_id, raw_text, segments (seg_id, kind, raw_text)
	"""
	payload = {
		"chapter_id": chapter_id,
		"schema_version": "speech_plan_patch.v0.1",
		"shots": [
			{
				"shot_id": s["shot_id"],
				"raw_text": s.get("text", {}).get("raw_text", ""),
				"segments": [
					{"seg_id": seg["seg_id"], "kind": seg["kind"], "raw_text": seg["raw_text"]}
					for seg in s.get("speech", {}).get("segments", [])
				],
			}
			for s in shots_with_segments
		],
	}

	rules = (
		"任务：为每个 shot 的 default 和 quote segments 输出朗读标签。\n"
		"输出格式：\n"
		'{\n'
		'  "schema_version": "speech_plan_patch.v0.1",\n'
		'  "chapter_id": "...",\n'
		'  "shots": [\n'
		'    {\n'
		'      "shot_id": "...",\n'
		'      "default": {"emotion":"neutral","intensity":0.35,"pace":"normal","pause_ms":80,"mode":"narration"},\n'
		'      "segments": [{"seg_id":"...","speaker":"...","gender_hint":"...","tone":"...","intensity":null,"pace":null}]\n'
		'    }\n'
		'  ]\n'
		'}\n'
		"raw_text 不可改。segments 的 intensity/pace 可选覆盖，为 null 则用 default。\n"
	)

	return rules + "\n输入数据(JSON)：\n" + json.dumps(payload, ensure_ascii=False)
