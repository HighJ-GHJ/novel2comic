# -*- coding: utf-8 -*-
"""
providers/image/image_flux.py

FLUX.1-schnell / FLUX.1 text2img via SiliconFlow /images/generations。
支持 16:9（1024x576）、seed、prompt。
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

try:
	from dotenv import load_dotenv
except Exception:
	load_dotenv = None

from PIL import Image

from novel2comic.core.io import find_env_file, find_project_root

DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"
# FLUX.1-schnell 支持的 16:9 尺寸
DEFAULT_IMAGE_SIZE = "1024x576"


@dataclass
class FluxConfig:
	api_key: str
	base_url: str
	model: str
	image_size: str
	timeout_s: float


def _load_dotenv_if_present(project_root: Path) -> None:
	if load_dotenv is None:
		return
	env_path = find_env_file(project_root)
	if env_path.exists():
		load_dotenv(dotenv_path=str(env_path), override=False)


def load_flux_config(
	project_root: Optional[str | Path] = None,
	api_key: Optional[str] = None,
	base_url: Optional[str] = None,
	model: Optional[str] = None,
	image_size: Optional[str] = None,
	timeout_s: Optional[float] = None,
) -> FluxConfig:
	root = find_project_root(project_root or __file__)
	_load_dotenv_if_present(root)

	key = (api_key or os.environ.get("SILICONFLOW_API_KEY", "")).strip()
	if not key:
		raise ValueError("Missing SILICONFLOW_API_KEY")

	url = (base_url or os.environ.get("SILICONFLOW_BASE_URL", "")).strip() or "https://api.siliconflow.cn/v1"
	m = (model or os.environ.get("FLUX_MODEL", "")).strip() or DEFAULT_MODEL
	sz = (image_size or os.environ.get("IMAGE_SIZE", "")).strip() or DEFAULT_IMAGE_SIZE
	# 若 IMAGE_SIZE 为 1344x768 等，FLUX.1-schnell 不支持则回退
	if sz not in ("1024x1024", "512x1024", "768x512", "768x1024", "1024x576", "576x1024"):
		sz = DEFAULT_IMAGE_SIZE
	t = float(timeout_s or os.environ.get("SILICONFLOW_TIMEOUT_S", "120"))

	return FluxConfig(api_key=key, base_url=url, model=m, image_size=sz, timeout_s=t)


def text2img(
	prompt: str,
	negative_prompt: Optional[str] = None,
	size: Optional[str] = None,
	seed: Optional[int] = None,
	*,
	config: Optional[FluxConfig] = None,
) -> tuple[Image.Image, dict]:
	"""
	调用 FLUX.1-schnell text2img，返回 (PIL.Image, meta)。
	meta 含: seed, elapsed_ms, model。
	"""
	cfg = config or load_flux_config()
	sz = size or cfg.image_size

	payload = {
		"model": cfg.model,
		"prompt": prompt,
		"image_size": sz,
	}
	if seed is not None:
		payload["seed"] = seed

	# FLUX.1-schnell 不支持 negative_prompt（文档中无此字段），忽略

	with httpx.Client(
		base_url=cfg.base_url,
		timeout=httpx.Timeout(cfg.timeout_s),
		headers={
			"Authorization": f"Bearer {cfg.api_key}",
			"Content-Type": "application/json",
		},
	) as client:
		import time
		t0 = time.perf_counter()
		r = client.post("/images/generations", json=payload)
		elapsed_ms = (time.perf_counter() - t0) * 1000

	if r.status_code < 200 or r.status_code >= 300:
		body_snip = (r.text or "")[:500]
		raise ValueError(f"FLUX HTTP {r.status_code}: {body_snip}")

	data = r.json()
	images = data.get("images", [])
	if not images:
		raise ValueError("FLUX returned no images")

	url = images[0].get("url", "")
	if not url:
		raise ValueError("FLUX image URL empty")

	# 下载图片
	img_r = httpx.get(url, timeout=30)
	img_r.raise_for_status()
	img = Image.open(io.BytesIO(img_r.content)).convert("RGB")

	meta = {
		"seed": data.get("seed"),
		"elapsed_ms": round(elapsed_ms, 2),
		"model": cfg.model,
		"image_size": sz,
	}
	return img, meta