# -*- coding: utf-8 -*-
"""
providers/llm/siliconflow_client.py

这个文件做什么：
- 提供一个极薄的 SiliconFlow LLM Client，供 skill 层调用。
- 支持从项目根目录的 .env 读取配置（推荐），避免你在 shell 里 export。
- 对外只暴露一个方法：chat_json(system_prompt, user_prompt) -> dict

配置来源优先级（从高到低）：
1) 显式传参（model/base_url/api_key）
2) .env 文件
3) 系统环境变量（兜底，不要求你用）

安全约定：
- .env 必须写进 .gitignore
- 不要把 key 写进任何代码文件
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

try:
	# python-dotenv：从 .env 加载到 os.environ
	from dotenv import load_dotenv
except Exception:  # pragma: no cover
	load_dotenv = None


@dataclass
class SiliconFlowConfig:
	api_key: str
	base_url: str
	model: str
	timeout_s: float = 60.0


class SiliconFlowLLMClient:
	def __init__(self, cfg: SiliconFlowConfig):
		self.cfg = cfg
		self._client = httpx.Client(
			base_url=cfg.base_url,
			timeout=httpx.Timeout(cfg.timeout_s),
			headers={
				"Authorization": f"Bearer {cfg.api_key}",
				"Content-Type": "application/json",
			},
		)

	def close(self) -> None:
		self._client.close()

	def chat_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
		payload: Dict[str, Any] = {
			"model": self.cfg.model,
			"messages": [
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt},
			],
			"temperature": 0.2,
			"top_p": 0.9,
		}

		# 尽量启用 JSON mode：能显著减少 Markdown/废话
		# 如果你的网关不支持，会返回 4xx；到时候你注释掉这一行即可。
		payload["response_format"] = {"type": "json_object"}

		r = self._client.post("/chat/completions", json=payload)

		if r.status_code < 200 or r.status_code >= 300:
			body = r.text
			if len(body) > 1000:
				body = body[:1000] + "...(truncated)"
			raise ValueError(f"SiliconFlow HTTP {r.status_code}: {body}")

		data = r.json()

		try:
			content = data["choices"][0]["message"]["content"]
		except Exception:
			raise ValueError(f"Unexpected response shape: {json.dumps(data, ensure_ascii=False)[:1000]}")

		try:
			return json.loads(content)
		except Exception:
			snip = content
			if len(snip) > 1000:
				snip = snip[:1000] + "...(truncated)"
			raise ValueError(f"LLM output is not valid JSON. content_snip={snip}")


def _load_dotenv_if_present(project_root: Path) -> None:
	"""
	如果项目根目录存在 .env，则加载到 os.environ。
	"""
	if load_dotenv is None:
		return

	env_path = project_root / ".env"
	if env_path.exists():
		load_dotenv(dotenv_path=str(env_path), override=False)


def load_siliconflow_client(
	project_root: Optional[str] = None,
	api_key: Optional[str] = None,
	base_url: Optional[str] = None,
	model: Optional[str] = None,
	timeout_s: Optional[float] = None,
) -> SiliconFlowLLMClient:
	"""
	加载 SiliconFlow client。

	你现在的诉求：不要用 export 环境变量，而是用项目内 .env 存储。
	所以我们默认会从 project_root/.env 读取（project_root 缺省为当前工作目录）。
	"""
	root = Path(project_root or os.getcwd()).resolve()
	_load_dotenv_if_present(root)

	key = (api_key or os.environ.get("SILICONFLOW_API_KEY", "")).strip()
	if not key:
		raise ValueError("Missing SILICONFLOW_API_KEY (from .env or env)")

	url = (base_url or os.environ.get("SILICONFLOW_BASE_URL", "")).strip() or "https://api.siliconflow.cn/v1"
	m = (model or os.environ.get("SILICONFLOW_MODEL", "")).strip() or "deepseek-ai/DeepSeek-V3.2"
	t = float(timeout_s or os.environ.get("SILICONFLOW_TIMEOUT_S", "60").strip() or 60)

	cfg = SiliconFlowConfig(api_key=key, base_url=url, model=m, timeout_s=t)
	return SiliconFlowLLMClient(cfg)
