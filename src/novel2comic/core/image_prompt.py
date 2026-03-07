# -*- coding: utf-8 -*-
"""
novel2comic/core/image_prompt.py

将镜头文本转为绘图 prompt。
- Qwen 模式（IMAGE_PROVIDER=qwen）：中文优先、模板化
- FLUX 模式：可选 LLM 转英文
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from novel2comic.core.image_review_schema import SuggestedPatch


def extract_must_have(shot: dict, max_items: int = 8) -> List[str]:
	"""
	从 shot 文本提取 must_have 关键词（用于 VLM 评审）。
	简单启发式：按标点切分，取 2~6 字片段，去重，最多 max_items 个。
	"""
	text = (shot.get("text", {}).get("subtitle_text") or shot.get("text", {}).get("raw_text") or "").strip()
	if not text:
		return []
	# 去掉引号内对话，保留旁白/场景描述
	text = re.sub(r'["""「」].*?["""「」]', "", text)
	parts = re.split(r'[，。！？、；\s]+', text)
	seen = set()
	result = []
	for p in parts:
		p = p.strip()
		if 2 <= len(p) <= 6 and p not in seen:
			seen.add(p)
			result.append(p)
			if len(result) >= max_items:
				break
	return result[:max_items]


def _image_prompt_flags() -> tuple[bool, str]:
	"""从 configs/stage_image.yaml 读取 use_llm_prompt、provider。"""
	try:
		from novel2comic.core.config_loader import get_stage_config
		cfg = get_stage_config("image")
		use_llm = cfg.get("use_llm_prompt", False)
		provider = (cfg.get("provider") or "qwen").strip().lower()
		return bool(use_llm), provider
	except Exception:
		return False, "qwen"


IMAGE_USE_LLM_PROMPT, IMAGE_PROVIDER = _image_prompt_flags()

# Qwen 中文 prompt 模板（任务书：动态漫画分镜、16:9、无水印）
QWEN_STYLE = "动态漫画分镜风格，统一画风，干净线条。16:9，无水印，无多余文字。"
QWEN_NEGATIVE = "水印,logo,低清,模糊,乱码文字,多余字幕,畸形手指,畸形脸"

# 镜头词映射
CAMERA_ZH = {"close-up": "近景", "medium shot": "中景", "wide shot": "远景"}


def build_prompt_qwen_draft(shot: dict, camera: str = "中景") -> str:
	"""
	Qwen Draft（T2I）中文 prompt。
	一句画面主述 + 镜头 + 风格约束。
	"""
	text = (shot.get("text", {}).get("subtitle_text") or shot.get("text", {}).get("raw_text") or "").strip()
	if not text:
		return f"一个场景。镜头：{camera}，平视。{QWEN_STYLE}"
	if len(text) > 180:
		text = text[:180]
	return f"{text}。镜头：{camera}，平视。{QWEN_STYLE}"


def apply_prompt_patch(
	base_prompt: str,
	base_negative: str,
	suggested_patch: SuggestedPatch,
) -> Tuple[str, str]:
	"""
	应用 VLM suggested_patch 到 prompt/negative。
	- prompt_add：追加到末尾（去重）
	- prompt_remove：从 prompt 做子串删除（保守：仅删完整词/短语）
	- negative_add：追加 negative（去重）
	"""
	prompt = base_prompt.strip()
	negative = base_negative.strip()

	for add in suggested_patch.prompt_add or []:
		add = (add or "").strip()
		if add and add not in prompt:
			prompt = f"{prompt}，{add}" if prompt else add

	for rm in suggested_patch.prompt_remove or []:
		rm = (rm or "").strip()
		if rm and rm in prompt:
			prompt = prompt.replace(rm, "").strip()
			prompt = re.sub(r"\s*，\s*，", "，", prompt).strip(",")

	neg_parts = [p.strip() for p in (negative.split(",") if negative else []) if p]
	for add in suggested_patch.negative_add or []:
		add = (add or "").strip()
		if add and add not in neg_parts:
			neg_parts.append(add)
	negative = ",".join(neg_parts)

	return prompt, negative


def build_prompt_qwen_refine(shot: dict, prev_text: Optional[str] = None) -> str:
	"""
	Qwen Refine（Edit）中文 prompt。
	开头固定：保持参考图一致；后面只写本镜头变化。
	"""
	prefix = "保持参考图的角色外观、服装、画风和构图一致。"
	text = (shot.get("text", {}).get("subtitle_text") or shot.get("text", {}).get("raw_text") or "").strip()
	if not text:
		return f"{prefix}微调光线或表情。"
	if len(text) > 100:
		text = text[:100]
	return f"{prefix}本镜头变化：{text}"


IMAGE_PROMPT_SYSTEM = """You are an image prompt generator for AI illustration (FLUX model).
Given a Chinese novel shot description, output a SHORT English visual description for image generation.

Rules:
- Output ONLY a JSON object: {"prompt": "your English visual description"}
- Focus on: scene, characters, actions, atmosphere, lighting
- No dialogue or quoted speech
- One sentence, 30-60 words
- Style: xianxia/Chinese fantasy, cinematic, detailed
- Be concrete: "a man dreaming of rice fields, sword fights, immortal sect, a woman by a lake" not "someone had a dream"
"""


def build_image_prompt_raw(shot: dict, style_tags: str, camera: str = "medium shot") -> str:
	"""直通模式：直接用 shot 文本 + 风格 + 镜头（FLUX 用）。"""
	text = (shot.get("text", {}).get("subtitle_text") or shot.get("text", {}).get("raw_text") or "").strip()
	if not text:
		return f"a scene, {camera}, {style_tags}"
	if len(text) > 200:
		text = text[:200]
	return f"{text}, {camera}, {style_tags}"


def build_image_prompt_llm(shot: dict, llm_client, style_tags: str, camera: str = "medium shot") -> str:
	"""
	LLM 模式：调用 LLM 将镜头文本转为英文视觉描述（FLUX 用）。
	失败时回退到直通。
	"""
	text = (shot.get("text", {}).get("subtitle_text") or shot.get("text", {}).get("raw_text") or "").strip()
	if not text:
		return build_image_prompt_raw(shot, style_tags, camera)

	try:
		out = llm_client.chat_json(IMAGE_PROMPT_SYSTEM, f"镜头文本：\n{text}")
		prompt = (out.get("prompt") or "").strip()
		if prompt and len(prompt) > 10:
			return f"{prompt}, {camera}, {style_tags}"
	except Exception:
		pass
	return build_image_prompt_raw(shot, style_tags, camera)
