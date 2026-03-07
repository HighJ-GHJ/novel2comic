# -*- coding: utf-8 -*-
"""
providers/image/image_qwen.py

硅基流动 Qwen/Qwen-Image（文生图）与 Qwen/Qwen-Image-Edit（图生图）。
- T2I: image_size=1664x928, steps=50, cfg=4.0（文档推荐，中文更稳）
- Edit: 不传 image_size，输出跟随 ref 尺寸
- 429/503/504 指数退避重试
- URL 1 小时有效，必须立刻下载落盘
"""

from __future__ import annotations

import base64
import io
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

try:
	from dotenv import load_dotenv
except Exception:
	load_dotenv = None

from PIL import Image

from novel2comic.core.image_prompt import QWEN_NEGATIVE
from novel2comic.core.io import find_env_file, find_project_root

MODEL_T2I = "Qwen/Qwen-Image"
MODEL_EDIT = "Qwen/Qwen-Image-Edit"
DEFAULT_IMAGE_SIZE = "1664x928"
DEFAULT_STEPS = 50
DEFAULT_CFG = 4.0
MAX_RETRIES = 3
DOWNLOAD_TIMEOUT_S = 60
RETRY_BACKOFF_BASE = 2
ERR_BODY_MAX_LEN = 500
DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_TIMEOUT_S = 120


@dataclass
class QwenImageConfig:
	api_key: str
	base_url: str
	timeout_s: float


def _load_dotenv_if_present(project_root: Path) -> None:
	if load_dotenv is None:
		return
	env_path = find_env_file(project_root)
	if env_path.exists():
		load_dotenv(dotenv_path=str(env_path), override=False)


def load_qwen_config(
	project_root: Optional[str | Path] = None,
	api_key: Optional[str] = None,
	base_url: Optional[str] = None,
	timeout_s: Optional[float] = None,
) -> QwenImageConfig:
	root = find_project_root(project_root or __file__)
	_load_dotenv_if_present(root)

	key = (api_key or os.environ.get("SILICONFLOW_API_KEY", "")).strip()
	if not key:
		raise ValueError("Missing SILICONFLOW_API_KEY")

	try:
		from novel2comic.core.config_loader import get_siliconflow
		sf = get_siliconflow()
		url = (base_url or os.environ.get("SILICONFLOW_BASE_URL", "") or sf.get("base_url", "") or "") or DEFAULT_BASE_URL
		t = float(timeout_s or os.environ.get("SILICONFLOW_TIMEOUT_S", "") or sf.get("timeout_s", "") or DEFAULT_TIMEOUT_S)
	except Exception:
		url = (base_url or os.environ.get("SILICONFLOW_BASE_URL", "")).strip() or DEFAULT_BASE_URL
		t = float(timeout_s or os.environ.get("SILICONFLOW_TIMEOUT_S", "") or DEFAULT_TIMEOUT_S)

	return QwenImageConfig(api_key=key, base_url=url, timeout_s=t)


def _download_url(url: str) -> bytes:
	"""立刻下载 URL（1 小时有效），返回 png bytes。"""
	headers = {"User-Agent": "Mozilla/5.0 (compatible; novel2comic/1.0)"}
	with httpx.Client(timeout=DOWNLOAD_TIMEOUT_S, follow_redirects=True) as dl_client:
		r = dl_client.get(url, headers=headers)
	r.raise_for_status()
	return r.content


def _do_request(client: httpx.Client, payload: dict) -> tuple[bytes, dict]:
	"""
	POST /images/generations，解析 images[0].url，立刻 GET 下载，返回 (png_bytes, meta)。
	429/503/504 指数退避重试最多 3 次。
	"""
	last_err = None
	for attempt in range(MAX_RETRIES):
		try:
			t0 = time.perf_counter()
			r = client.post("/images/generations", json=payload)
			elapsed_ms = (time.perf_counter() - t0) * 1000

			if r.status_code in (429, 503, 504):
				if attempt < MAX_RETRIES - 1:
					time.sleep(RETRY_BACKOFF_BASE ** attempt)
					continue
				body = (r.text or "")[:ERR_BODY_MAX_LEN]
				trace = r.headers.get("x-siliconcloud-trace-id", "")
				raise ValueError(f"SiliconFlow HTTP {r.status_code} (trace={trace}): {body}")

			if r.status_code < 200 or r.status_code >= 300:
				body = (r.text or "")[:ERR_BODY_MAX_LEN]
				trace = r.headers.get("x-siliconcloud-trace-id", "")
				raise ValueError(f"SiliconFlow HTTP {r.status_code} (trace={trace}): {body}")

			data = r.json()
			images = data.get("images", [])
			if not images:
				raise ValueError("SiliconFlow returned no images")

			img_url = images[0].get("url", "")
			if not img_url:
				raise ValueError("SiliconFlow image URL empty")

			png_bytes = _download_url(img_url)
			meta = {
				"seed": data.get("seed"),
				"elapsed_ms": round(elapsed_ms, 2),
				"timing_inference": data.get("timings", {}).get("inference"),
				"trace_id": r.headers.get("x-siliconcloud-trace-id"),
			}
			return png_bytes, meta

		except ValueError:
			raise
		except Exception as e:
			last_err = e
			if attempt < MAX_RETRIES - 1:
				time.sleep(RETRY_BACKOFF_BASE ** attempt)
				continue
			raise last_err

	raise last_err or ValueError("request failed")


def generate_t2i(
	prompt: str,
	negative_prompt: Optional[str] = None,
	image_size: str = DEFAULT_IMAGE_SIZE,
	steps: int = DEFAULT_STEPS,
	cfg: float = DEFAULT_CFG,
	seed: Optional[int] = None,
	*,
	config: Optional[QwenImageConfig] = None,
) -> tuple[Image.Image, dict]:
	"""
	文生图：Qwen/Qwen-Image。
	返回 (PIL.Image, meta)，meta 含 seed、elapsed_ms、model。
	"""
	api_cfg = config or load_qwen_config()
	neg = (negative_prompt or "").strip() or QWEN_NEGATIVE

	payload = {
		"model": MODEL_T2I,
		"prompt": prompt,
		"negative_prompt": neg,
		"image_size": image_size,
		"num_inference_steps": steps,
		"cfg": cfg,
		"batch_size": 1,
	}
	if seed is not None:
		payload["seed"] = seed

	with httpx.Client(
		base_url=api_cfg.base_url,
		timeout=httpx.Timeout(api_cfg.timeout_s),
		headers={
			"Authorization": f"Bearer {api_cfg.api_key}",
			"Content-Type": "application/json",
		},
	) as client:
		png_bytes, meta = _do_request(client, payload)

	meta["model"] = MODEL_T2I
	meta["image_size"] = image_size
	img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
	return img, meta


def edit(
	image_ref_png_bytes: bytes,
	prompt: str,
	negative_prompt: Optional[str] = None,
	steps: int = DEFAULT_STEPS,
	cfg: float = DEFAULT_CFG,
	seed: Optional[int] = None,
	*,
	config: Optional[QwenImageConfig] = None,
) -> tuple[Image.Image, dict]:
	"""
	图生图：Qwen/Qwen-Image-Edit。
	不传 image_size，输出尺寸跟随 ref。
	image_ref_png_bytes：参考图 PNG 二进制。
	"""
	api_cfg = config or load_qwen_config()
	neg = (negative_prompt or "").strip() or QWEN_NEGATIVE

	b64 = base64.b64encode(image_ref_png_bytes).decode("ascii")
	data_url = f"data:image/png;base64,{b64}"

	payload = {
		"model": MODEL_EDIT,
		"prompt": prompt,
		"negative_prompt": neg,
		"image": data_url,
		"num_inference_steps": steps,
		"cfg": cfg,
		"batch_size": 1,
	}
	if seed is not None:
		payload["seed"] = seed

	with httpx.Client(
		base_url=api_cfg.base_url,
		timeout=httpx.Timeout(api_cfg.timeout_s),
		headers={
			"Authorization": f"Bearer {api_cfg.api_key}",
			"Content-Type": "application/json",
		},
	) as client:
		png_bytes, meta = _do_request(client, payload)

	meta["model"] = MODEL_EDIT
	img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
	return img, meta