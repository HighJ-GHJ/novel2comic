# -*- coding: utf-8 -*-
"""
providers/vlm/siliconflow_vlm.py

SiliconFlow VLM 评审：/chat/completions + 多图 image_url + JSON mode。
用于 Strict Image QA：角色一致性、画面符合度、画风一致性。
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

try:
	from dotenv import load_dotenv
except Exception:
	load_dotenv = None

from novel2comic.core.config_loader import get_siliconflow
from novel2comic.core.io import find_env_file, find_project_root
from novel2comic.core.image_review_schema import (
	DEFAULT_ALIGNMENT_THRESHOLD,
	DEFAULT_IDENTITY_THRESHOLD,
	DEFAULT_STYLE_THRESHOLD,
	ReviewResult,
	parse_review_json,
)
from novel2comic.providers.vlm.prompts.recheck_prompts import (
	RECHECK_SYSTEM_PROMPT,
	recheck_user_text,
)

DEFAULT_VLM_MODEL = "Qwen/Qwen2.5-VL-32B-Instruct"
DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_TIMEOUT_S = 120
DEFAULT_DETAIL = "high"

# System prompt（严格版，任务书 1)
VLM_SYSTEM_PROMPT = """你是"导演质检官（Director QA）"，负责审核动态漫画分镜的单张画面是否合格。
你必须严格执行以下规则：

【任务】
对"当前镜头画面（SHOT）"进行评审，重点检查：
1) 画面符合度（alignment）：是否准确呈现镜头描述中的关键对象、动作、场景氛围与镜头语言；
2) 角色一致性（identity）：如果提供了角色锚点（CHAR_ANCHOR），SHOT 中主角是否与锚点为同一角色（脸型/五官/发型/服装/体态标志物/配饰等），不得"换人/换衣/换风格导致像另一个人"；
3) 画风一致性（style）：如果提供了风格锚点（STYLE_ANCHOR），SHOT 是否与锚点保持同一画风（线条、上色、质感、光影、色调倾向、构图语言），不得明显漂移为写实摄影/油画/3D等。

【严格判定】
- 任何"明显不符"都必须判 FAIL（宁可误杀，不可漏放）。
- 若 identity 不一致：必须 hard_fail.identity=true。
- 若出现大量不相关元素、关键元素缺失、主体错误：必须 hard_fail.alignment=true。
- 若画风明显漂移或风格断裂：必须 hard_fail.style=true。

【输出格式】
你只能输出一个 JSON 对象（不要 Markdown，不要解释性文字）。
JSON 必须包含并仅包含下列字段（不得新增字段）：
{
  "pass": boolean,
  "scores": {"alignment": number, "identity": number, "style": number},
  "hard_fail": {"alignment": boolean, "identity": boolean, "style": boolean},
  "issues": [{"type": string, "severity": "low"|"mid"|"high", "detail": string}],
  "must_have": [string],
  "missing": [string],
  "suggested_patch": {
    "prompt_add": [string],
    "prompt_remove": [string],
    "negative_add": [string],
    "rebase": "prev_shot"|"char_anchor"|"style_anchor"|"none"
  }
}

【打分规则】
- scores 范围 0.0~1.0，越高越好。
- alignment：关键要素与镜头意图匹配程度。
- identity：与角色锚点一致程度；若未提供角色锚点或未指定主角，则将 identity 设为 1.0 且 hard_fail.identity=false，但仍需给出 issues（如"未提供锚点，无法核验"）。
- style：与风格锚点一致程度；若未提供风格锚点，则将 style 设为 1.0 且 hard_fail.style=false。

【通过条件（用于你内部判断）】
默认严格阈值：
- alignment >= 0.85
- identity >= 0.90（当提供角色锚点且指定主角时）
- style >= 0.85（当提供风格锚点时）
且 hard_fail 任一为 true 则必须 pass=false。

【suggested_patch 指导】
- prompt_add：补充缺失的关键对象/动作/场景氛围/镜头语言（短词/短句）。
- prompt_remove：删掉导致发散或错误元素的词。
- negative_add：添加需要明确禁止的元素（如"不要出现文字水印/多余字幕/霓虹招牌字"）。
- rebase：若 identity 或 style 失败，优先建议 "char_anchor" 或 "style_anchor"；若一切正常且连续镜头可沿用，可建议 "prev_shot"；若必须重启且无参考，则 "none"。

务必保持 JSON 可被严格解析。"""


def _resize_image_if_large(png_bytes: bytes, max_edge: int = 1024) -> bytes:
	"""大图缩小以规避 API 校验（如 151652 is not in list）。"""
	try:
		from PIL import Image
		import io
		img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
		w, h = img.size
		if max(w, h) <= max_edge:
			return png_bytes
		ratio = max_edge / max(w, h)
		nw, nh = int(w * ratio), int(h * ratio)
		nw = max(28, (nw // 28) * 28)
		nh = max(28, (nh // 28) * 28)
		resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
		img = img.resize((nw, nh), resample)
		buf = io.BytesIO()
		img.save(buf, format="PNG")
		return buf.getvalue()
	except Exception:
		return png_bytes


def _bytes_to_data_url(png_bytes: bytes, resize: bool = True) -> str:
	if resize:
		png_bytes = _resize_image_if_large(png_bytes)
	return f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"


def _extract_json_from_response(text: str) -> str:
	"""从模型输出提取 JSON（部分模型不支持 json_object，可能返回 ```json ... ``` 或纯 JSON）。"""
	import re
	text = (text or "").strip()
	# ```json ... ``` 或 ``` ... ```
	m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
	if m:
		return m.group(1).strip()
	# 尝试直接解析整段
	if text.startswith("{"):
		return text
	return text


def _build_user_content(
	shot_png_bytes: bytes,
	char_anchor_bytes: Optional[bytes],
	style_anchor_bytes: Optional[bytes],
	user_text: str,
	detail: str = "high",
) -> List[Dict[str, Any]]:
	"""构建 user message 的 content 数组：多图 + 文本。"""
	parts = []
	# 部分模型对 detail 敏感，仅传合法值；省略时 API 用默认
	img_opts: Dict[str, Any] = {"url": _bytes_to_data_url(shot_png_bytes)}
	if detail in ("low", "high", "auto"):
		img_opts["detail"] = detail
	parts.append({"type": "image_url", "image_url": img_opts})
	if char_anchor_bytes:
		co = {"url": _bytes_to_data_url(char_anchor_bytes)}
		if detail in ("low", "high", "auto"):
			co["detail"] = detail
		parts.append({"type": "image_url", "image_url": co})
	if style_anchor_bytes:
		so = {"url": _bytes_to_data_url(style_anchor_bytes)}
		if detail in ("low", "high", "auto"):
			so["detail"] = detail
		parts.append({"type": "image_url", "image_url": so})
	parts.append({"type": "text", "text": user_text})
	return parts


def _build_user_text(
	shot_id: str,
	scene_id: str,
	primary_char_id: str,
	shot_description_cn: str,
	must_have_list_cn: List[str],
) -> str:
	must_str = "、".join(must_have_list_cn) if must_have_list_cn else "（无）"
	return f"""请审核以下分镜画面是否合格。严格模式：宁可判失败也不要放过不一致。

【镜头信息】
shot_id: {shot_id}
scene_id: {scene_id}
primary_char_id: {primary_char_id or "（无）"}

【镜头画面描述（必须呈现的内容）】
{shot_description_cn}

【必须包含的关键要素 must_have（请你也写回到输出 JSON.must_have）】
{must_str}

【允许的弹性】
- 允许细节略有差异，但不得改变主体身份、核心动作与场景属性。
- 不得出现大段文字水印/无关字幕；除非 must_have 明确要求出现文字（本例没有）。

【评审说明】
你将看到：
- 第1张图：SHOT（当前镜头画面）
- 若提供：角色锚点图 CHAR_ANCHOR（主角的参考外观）
- 若提供：风格锚点图 STYLE_ANCHOR（本章统一画风）

请输出严格 JSON，按 system 约束字段，不要添加任何其它字段。"""


@dataclass
class VLMConfig:
	api_key: str
	base_url: str
	model: str
	timeout_s: float
	detail: str


def load_vlm_config(
	project_root: Optional[str | Path] = None,
	api_key: Optional[str] = None,
	base_url: Optional[str] = None,
	model: Optional[str] = None,
	timeout_s: Optional[float] = None,
	detail: Optional[str] = None,
) -> VLMConfig:
	root = find_project_root(project_root or __file__)
	if load_dotenv:
		env_path = find_env_file(root)
		if env_path.exists():
			load_dotenv(dotenv_path=str(env_path), override=False)

	key = (api_key or os.environ.get("SILICONFLOW_API_KEY", "")).strip()
	if not key:
		raise ValueError("Missing SILICONFLOW_API_KEY")

	try:
		sf = get_siliconflow()
		vlm_cfg = sf.get("vlm") or {}
		url = (base_url or os.environ.get("SILICONFLOW_BASE_URL", "") or sf.get("base_url", "") or "").strip() or DEFAULT_BASE_URL
		t = float(timeout_s or os.environ.get("SILICONFLOW_TIMEOUT_S", "") or sf.get("timeout_s", "") or DEFAULT_TIMEOUT_S)
		m = (model or os.environ.get("VLM_MODEL", "") or vlm_cfg.get("model", "") or "").strip() or DEFAULT_VLM_MODEL
		d = (detail or os.environ.get("VLM_DETAIL", "") or vlm_cfg.get("detail", "") or "").strip() or DEFAULT_DETAIL
	except Exception:
		url = (base_url or os.environ.get("SILICONFLOW_BASE_URL", "")).strip() or DEFAULT_BASE_URL
		t = float(timeout_s or os.environ.get("SILICONFLOW_TIMEOUT_S", "") or DEFAULT_TIMEOUT_S)
		m = (model or os.environ.get("VLM_MODEL", "")).strip() or DEFAULT_VLM_MODEL
		d = (detail or os.environ.get("VLM_DETAIL", "")).strip() or DEFAULT_DETAIL

	return VLMConfig(api_key=key, base_url=url, model=m, timeout_s=t, detail=d)


class SiliconFlowVLMClient:
	def __init__(self, cfg: VLMConfig):
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

	def review_shot_image(
		self,
		shot_png_bytes: bytes,
		shot_brief: Dict[str, Any],
		*,
		char_anchor_bytes: Optional[bytes] = None,
		style_anchor_bytes: Optional[bytes] = None,
		alignment_threshold: float = DEFAULT_ALIGNMENT_THRESHOLD,
		identity_threshold: float = DEFAULT_IDENTITY_THRESHOLD,
		style_threshold: float = DEFAULT_STYLE_THRESHOLD,
		require_char_anchor: bool = False,
		require_style_anchor: bool = False,
	) -> ReviewResult:
		"""
		评审单张 shot 图。
		shot_brief: shot_id, scene_id, primary_char_id, shot_description_cn, must_have_list_cn
		"""
		user_text = _build_user_text(
			shot_id=shot_brief.get("shot_id", ""),
			scene_id=shot_brief.get("scene_id", ""),
			primary_char_id=shot_brief.get("primary_char_id", ""),
			shot_description_cn=shot_brief.get("shot_description_cn", ""),
			must_have_list_cn=shot_brief.get("must_have_list_cn", []),
		)
		content = _build_user_content(
			shot_png_bytes,
			char_anchor_bytes,
			style_anchor_bytes,
			user_text,
			detail=self.cfg.detail,
		)

		payload = {
			"model": self.cfg.model,
			"messages": [
				{"role": "system", "content": VLM_SYSTEM_PROMPT},
				{"role": "user", "content": content},
			],
			"temperature": 0.1,
		}
		# 部分 VLM 不支持 json_object，先尝试带 json，失败则重试不带
		for use_json in (True, False):
			if use_json:
				payload["response_format"] = {"type": "json_object"}
			elif "response_format" in payload:
				del payload["response_format"]
			r = self._client.post("/chat/completions", json=payload)
			if r.status_code < 200 or r.status_code >= 300:
				body = (r.text or "")[:1000]
				if use_json and "json" in body.lower() and "not supported" in body.lower():
					continue
				raise ValueError(f"VLM HTTP {r.status_code}: {body}")
			break

		data = r.json()
		try:
			content_str = data["choices"][0]["message"]["content"]
		except (KeyError, IndexError, TypeError):
			raise ValueError(f"VLM unexpected response: {json.dumps(data, ensure_ascii=False)[:500]}")

		content_str = _extract_json_from_response(content_str)

		return parse_review_json(
			content_str,
			alignment_threshold=alignment_threshold,
			identity_threshold=identity_threshold,
			style_threshold=style_threshold,
			has_char_anchor=char_anchor_bytes is not None,
			has_style_anchor=style_anchor_bytes is not None,
			primary_char_id=shot_brief.get("primary_char_id", ""),
			require_char_anchor=require_char_anchor,
			require_style_anchor=require_style_anchor,
		)

	def review_shot_image_recheck(
		self,
		shot_png_bytes: bytes,
		shot_brief: Dict[str, Any],
		recheck_dims: List[str],
		round1_issues: List[str],
		*,
		char_anchor_bytes: Optional[bytes] = None,
		style_anchor_bytes: Optional[bytes] = None,
		alignment_threshold: float = DEFAULT_ALIGNMENT_THRESHOLD,
		identity_threshold: float = DEFAULT_IDENTITY_THRESHOLD,
		style_threshold: float = DEFAULT_STYLE_THRESHOLD,
	) -> ReviewResult:
		"""
		Round2 窄域复核。仅在 Round1 FAIL 后触发。
		recheck_dims: 如 ["identity"、"style"]，只复核这些维度。
		"""
		# 只塞必要的 anchor：identity 才塞 char_anchor，style 才塞 style_anchor
		send_char = "identity" in recheck_dims and char_anchor_bytes is not None
		send_style = "style" in recheck_dims and style_anchor_bytes is not None

		user_text = recheck_user_text(
			shot_id=shot_brief.get("shot_id", ""),
			primary_char_id=shot_brief.get("primary_char_id", ""),
			shot_description_cn=shot_brief.get("shot_description_cn", ""),
			recheck_dims=recheck_dims,
			round1_issues=round1_issues,
		)
		content = _build_user_content(
			shot_png_bytes,
			char_anchor_bytes if send_char else None,
			style_anchor_bytes if send_style else None,
			user_text,
			detail=self.cfg.detail,
		)

		payload = {
			"model": self.cfg.model,
			"messages": [
				{"role": "system", "content": RECHECK_SYSTEM_PROMPT},
				{"role": "user", "content": content},
			],
			"temperature": 0.05,
		}
		for use_json in (True, False):
			if use_json:
				payload["response_format"] = {"type": "json_object"}
			elif "response_format" in payload:
				del payload["response_format"]
			r = self._client.post("/chat/completions", json=payload)
			if r.status_code < 200 or r.status_code >= 300:
				body = (r.text or "")[:1000]
				if use_json and "json" in body.lower() and "not supported" in body.lower():
					continue
				raise ValueError(f"VLM Recheck HTTP {r.status_code}: {body}")
			break

		data = r.json()
		try:
			content_str = data["choices"][0]["message"]["content"]
		except (KeyError, IndexError, TypeError):
			raise ValueError(f"VLM Recheck unexpected response: {json.dumps(data, ensure_ascii=False)[:500]}")

		content_str = _extract_json_from_response(content_str)

		return parse_review_json(
			content_str,
			alignment_threshold=alignment_threshold,
			identity_threshold=identity_threshold,
			style_threshold=style_threshold,
			has_char_anchor=send_char,
			has_style_anchor=send_style,
			primary_char_id=shot_brief.get("primary_char_id", ""),
			require_char_anchor=False,
			require_style_anchor=False,
		)
