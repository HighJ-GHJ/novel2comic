# -*- coding: utf-8 -*-
"""
novel2comic/core/config_loader.py

从 configs/*.yaml 加载配置，支持 env 覆盖。
- 密钥（API_KEY）必须放 .env，不参与 YAML
- 可变参数按阶段/服务分类到独立 YAML
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:
	import yaml
except ImportError:
	yaml = None

try:
	from dotenv import load_dotenv
except ImportError:
	load_dotenv = None

from novel2comic.core.io import find_env_file, find_project_root


def _ensure_dotenv_loaded() -> None:
	if load_dotenv:
		env_path = find_env_file(__file__)
		if env_path.exists():
			load_dotenv(dotenv_path=str(env_path), override=False)


_CONFIGS_DIR = "configs"
_CACHE: Dict[str, Dict[str, Any]] = {}


def _configs_path() -> Path:
	root = find_project_root(__file__)
	return root / _CONFIGS_DIR


def _load_yaml(name: str) -> Dict[str, Any]:
	"""加载单个 YAML 文件，返回 dict。"""
	if yaml is None:
		raise ImportError("PyYAML required for config_loader. pip install PyYAML")
	path = _configs_path() / f"{name}.yaml"
	if not path.exists():
		return {}
	with open(path, encoding="utf-8") as f:
		data = yaml.safe_load(f)
	return data if isinstance(data, dict) else {}


# 配置路径 -> env 变量名（向后兼容，env 优先于 YAML）
_CFG_PATH_TO_ENV: Dict[str, str] = {
	"stage_image.image_size": "IMAGE_SIZE",
	"stage_image.steps": "IMAGE_STEPS",
	"stage_image.cfg": "IMAGE_CFG",
	"stage_image.mode": "IMAGE_MODE",
	"stage_image.max_attempts": "IMAGE_MAX_ATTEMPTS",
	"stage_image.chain_max_hops": "IMAGE_CHAIN_MAX_HOPS",
	"stage_image.use_vlm_review": "IMAGE_USE_VLM_REVIEW",
	"stage_image.review_max_attempts": "IMAGE_REVIEW_MAX_ATTEMPTS",
	"stage_image.use_llm_prompt": "IMAGE_USE_LLM_PROMPT",
	"stage_image.provider": "IMAGE_PROVIDER",
	"siliconflow.base_url": "SILICONFLOW_BASE_URL",
	"siliconflow.timeout_s": "SILICONFLOW_TIMEOUT_S",
	"stage_director_review.enabled": "DIRECTOR_REVIEW_ENABLED",
	"stage_director_review.apply_patch": "DIRECTOR_REVIEW_APPLY_PATCH",
	"stage_director_review.model": "DIRECTOR_REVIEW_MODEL",
	"stage_director_review.temperature": "DIRECTOR_REVIEW_TEMPERATURE",
	"stage_tts.instruction_max_len": "TTS_INSTRUCTION_MAX_LEN",
	"stage_tts.use_style_prompt": "TTS_USE_STYLE_PROMPT",
	"stage_anchors.enabled": "ANCHORS_ENABLED",
	"stage_anchors.topk_chars": "ANCHORS_TOPK",
	"stage_anchors.auto_build_on_missing": "ANCHORS_AUTO_BUILD",
	"stage_anchors.default_gender": "ANCHORS_DEFAULT_GENDER",
	"stage_image.review.strict": "IMAGE_REVIEW_STRICT",
	"stage_image.review.require_char_anchor": "IMAGE_REVIEW_REQUIRE_CHAR_ANCHOR",
	"stage_image.review.require_style_anchor": "IMAGE_REVIEW_REQUIRE_STYLE_ANCHOR",
	"stage_image.review.enable_recheck": "IMAGE_REVIEW_ENABLE_RECHECK",
}


def _coerce_value(env_val: str, default: Any) -> Any:
	if isinstance(default, bool):
		return env_val.strip().lower() in ("1", "true", "yes")
	if isinstance(default, int):
		try:
			return int(env_val.strip() or default)
		except ValueError:
			return default
	if isinstance(default, float):
		try:
			return float(env_val.strip() or default)
		except ValueError:
			return default
	return env_val.strip()


def _deep_merge_env(data: Dict[str, Any], config_name: str, path: str = "") -> Dict[str, Any]:
	"""递归遍历，对叶子应用 env 覆盖。path 如 stage_image.image_size。"""
	out = {}
	for k, v in data.items():
		p = f"{path}.{k}" if path else k
		full_key = f"{config_name}.{p}" if p else config_name
		if isinstance(v, dict) and v and not _is_leaf_dict(v):
			out[k] = _deep_merge_env(v, config_name, p)
		else:
			# 先查已知映射，再 fallback 全路径
			env_key = _CFG_PATH_TO_ENV.get(full_key)
			env_val = os.environ.get(env_key) if env_key else None
			if env_val is None:
				env_key = full_key.upper().replace(".", "_").replace("-", "_")
				env_val = os.environ.get(env_key)
			if env_val is not None and env_val != "":
				out[k] = _coerce_value(env_val, v)
			else:
				out[k] = v
	return out


def _is_leaf_dict(d: dict) -> bool:
	"""是否全为标量的 dict（视为叶子）。"""
	for v in d.values():
		if isinstance(v, dict):
			return False
	return True


def load_config(name: str, use_cache: bool = True) -> Dict[str, Any]:
	"""
	加载 configs/<name>.yaml，并应用 env 覆盖。
	name: "siliconflow" | "stage_segment" | "stage_director_review" | "stage_tts" | "stage_image"
	"""
	_ensure_dotenv_loaded()
	if use_cache and name in _CACHE:
		return _CACHE[name]
	data = _load_yaml(name)
	if data:
		data = _deep_merge_env(data, name)
		_CACHE[name] = data
	return data


def get_siliconflow() -> Dict[str, Any]:
	"""硅基流动共用配置。"""
	return load_config("siliconflow")


def get_stage_config(stage: str) -> Dict[str, Any]:
	"""加载 stage 配置：stage 为 segment/director_review/tts/image。"""
	return load_config(f"stage_{stage}")


def clear_cache() -> None:
	"""清空缓存（测试用）。"""
	_CACHE.clear()