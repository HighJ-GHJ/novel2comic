# -*- coding: utf-8 -*-
"""
novel2comic/director_review/client.py

LLM 调用：JSON mode + 重试。
"""

from __future__ import annotations

import time
from typing import Any, Dict

MAX_RETRIES = 2


def chat_director_review(llm_client: Any, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
	"""
	调用 LLM 获取导演审阅 JSON。支持重试。
	llm_client 需实现 chat_json(system_prompt, user_prompt) -> dict。
	"""
	last_err = None
	for attempt in range(MAX_RETRIES + 1):
		try:
			return llm_client.chat_json(system_prompt, user_prompt)
		except Exception as e:
			last_err = e
			if attempt < MAX_RETRIES:
				time.sleep(1.5 * (attempt + 1))
	raise last_err
