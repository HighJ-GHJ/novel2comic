# -*- coding: utf-8 -*-
"""
refine_shot_split/prompt.py

这个文件做什么：
- 负责把 base_shots + constraints 拼成一个“受约束的任务描述”，让 LLM 输出 patch JSON。
- 这里不调用模型，只做 prompt 组装。

关键点：
- 强调：只能输出 JSON，不能 Markdown。
- 强调：文本守恒，不准改写 base_shots 的文字，只能通过 ops 重排/合并/拆分。
"""

from __future__ import annotations

import json
from typing import List

from .schema import Shot, Constraints


SYSTEM_PROMPT = (
	"你是“小说分镜切分校正器”(shot split refiner)。\n"
	"你必须严格遵守：只输出一个 JSON 对象，不要解释，不要 Markdown，不要代码块。\n"
	"你只能输出 ops（merge/split/move_tail/tag）。\n"
	"你绝对不能改写、删减、添加任何原文字符；只能通过 ops 重排边界。\n"
)


def build_user_prompt(chapter_id: str, base_shots: List[Shot], c: Constraints) -> str:
	"""
	把输入序列化为 LLM 可读的 JSON，再加上规则说明。
	"""
	payload = {
		"chapter_id": chapter_id,
		"constraints": {
			"min_shots": c.min_shots,
			"max_shots": c.max_shots,
			"forbid_cross_scene_break": c.forbid_cross_scene_break,
		},
		"base_shots": [
			{
				"idx": s.idx,
				"kind": s.kind,
				"text": s.text,
			}
			for s in base_shots
		],
	}

	rules = (
		"任务：在不改变任何原文字符的前提下，让分镜边界更符合语义与叙事节奏。\n"
		"输出格式：\n"
		"{\n"
		'  "schema_version": "shotsplit_patch.v0.1",\n'
		'  "chapter_id": "...",\n'
		'  "constraints": {...},\n'
		'  "ops": [ ... ]\n'
		"}\n"
		"\n"
		"允许的 op：\n"
		'1) {"op":"merge","start_idx":i,"end_idx":j}\n'
		'2) {"op":"split","idx":i,"at":"某个子串"}  # at 必须出现在该 shot 文本中\n'
		'3) {"op":"move_tail","from_idx":i,"to_idx":i+1,"sentences":k}\n'
		'4) {"op":"tag","idx":i,"tags":{...}}\n'
		"\n"
		"硬性要求：\n"
		"- 只能输出 JSON\n"
		"- 不能跨 scene_break 合并/移动（如果 forbid_cross_scene_break=true）\n"
		"- 输出后 shot 数必须在 [min_shots,max_shots]\n"
	)

	return rules + "\n输入数据(JSON)：\n" + json.dumps(payload, ensure_ascii=False)
