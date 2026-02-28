# -*- coding: utf-8 -*-
"""
providers/tts/siliconflow_tts.py

SiliconFlow TTS：调用 /audio/speech 生成 wav。
支持 CosyVoice2-0.5B（默认）、IndexTTS-2。per-call voice 覆盖。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

try:
	from dotenv import load_dotenv
except Exception:
	load_dotenv = None

# CosyVoice2 默认
DEFAULT_MODEL = "FunAudioLLM/CosyVoice2-0.5B"
DEFAULT_VOICE_NARRATOR = "FunAudioLLM/CosyVoice2-0.5B:claire"
DEFAULT_VOICE_MALE = "FunAudioLLM/CosyVoice2-0.5B:benjamin"
DEFAULT_VOICE_FEMALE = "FunAudioLLM/CosyVoice2-0.5B:anna"

# CosyVoice2 风格分隔符
TTS_STYLE_ENDOPROMPT = "<|endofprompt|>"

# instruction 长度安全阈值，超长强制 endofprompt
INSTRUCTION_MAX_LEN = int(os.environ.get("TTS_INSTRUCTION_MAX_LEN", "12"))


def _is_cosyvoice2_model(model: str) -> bool:
	"""检测是否为 CosyVoice2 模型（prefix 会念出 instruction，必须用 endofprompt）。"""
	return bool(model and "cosyvoice2" in model.lower())


def build_input_text(
	text: str,
	instruction: str | None,
	mode: str,
	*,
	model: str = "",
	instruction_max_len: int = INSTRUCTION_MAX_LEN,
) -> tuple[str, str]:
	"""
	构建 TTS input 字符串。
	Returns: (input_text, effective_mode)
	CosyVoice2 强制 endofprompt，不允许 prefix。
	"""
	inst = (instruction or "").strip().replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
	mode = (mode or "endofprompt").strip().lower()
	force_endofprompt = _is_cosyvoice2_model(model)

	if mode == "none" or not inst:
		return text, "none"

	# CosyVoice2：prefix 会念出 instruction，必须禁用
	if mode == "prefix" and force_endofprompt:
		print("[WARN] CosyVoice2 不支持 prefix 模式，已降级为 endofprompt，避免风格提示词被读出")
		mode = "endofprompt"

	# instruction 超长时强制 endofprompt
	if len(inst) > instruction_max_len:
		print(f"[WARN] instruction 长度 {len(inst)} > {instruction_max_len}，强制使用 endofprompt")
		mode = "endofprompt"

	if mode == "prefix":
		return f"{inst}\n{text}", mode
	return f"{inst}{TTS_STYLE_ENDOPROMPT}{text}", "endofprompt"


@dataclass
class SiliconFlowTTSConfig:
	api_key: str
	base_url: str
	model: str
	voice_narrator: str
	voice_male: str
	voice_female: str
	sample_rate: int
	response_format: str
	timeout_s: float


def _load_dotenv_if_present(project_root: Path) -> None:
	if load_dotenv is None:
		return
	env_path = project_root / ".env"
	if env_path.exists():
		load_dotenv(dotenv_path=str(env_path), override=False)


def load_siliconflow_tts(
	project_root: Optional[str] = None,
	api_key: Optional[str] = None,
	base_url: Optional[str] = None,
	model: Optional[str] = None,
	voice_narrator: Optional[str] = None,
	voice_male: Optional[str] = None,
	voice_female: Optional[str] = None,
	sample_rate: Optional[int] = None,
	response_format: Optional[str] = None,
	timeout_s: Optional[float] = None,
) -> "SiliconFlowTTSClient":
	root = Path(project_root or os.getcwd()).resolve()
	_load_dotenv_if_present(root)

	key = (api_key or os.environ.get("SILICONFLOW_API_KEY", "")).strip()
	if not key:
		raise ValueError("Missing SILICONFLOW_API_KEY")

	url = (base_url or os.environ.get("SILICONFLOW_BASE_URL", "")).strip() or "https://api.siliconflow.cn/v1"
	m = (model or os.environ.get("SILICONFLOW_TTS_MODEL", "")).strip() or DEFAULT_MODEL
	vn = (voice_narrator or os.environ.get("SILICONFLOW_TTS_VOICE_NARRATOR", "")).strip() or DEFAULT_VOICE_NARRATOR
	vm = (voice_male or os.environ.get("SILICONFLOW_TTS_VOICE_MALE", "")).strip() or DEFAULT_VOICE_MALE
	vf = (voice_female or os.environ.get("SILICONFLOW_TTS_VOICE_FEMALE", "")).strip() or DEFAULT_VOICE_FEMALE
	sr = int(sample_rate or os.environ.get("SILICONFLOW_TTS_SAMPLE_RATE", "24000"))
	fmt = (response_format or os.environ.get("SILICONFLOW_TTS_RESPONSE_FORMAT", "")).strip() or "wav"
	t = float(timeout_s or os.environ.get("SILICONFLOW_TIMEOUT_S", "120"))

	cfg = SiliconFlowTTSConfig(
		api_key=key, base_url=url, model=m,
		voice_narrator=vn, voice_male=vm, voice_female=vf,
		sample_rate=sr, response_format=fmt, timeout_s=t,
	)
	return SiliconFlowTTSClient(cfg)


def select_voice(kind: str, gender_hint: str, cfg: SiliconFlowTTSConfig) -> str:
	"""根据 segment kind 与 gender_hint 选择 voice。"""
	if kind == "narration":
		return cfg.voice_narrator
	if kind == "quote":
		if gender_hint == "male":
			return cfg.voice_male
		if gender_hint == "female":
			return cfg.voice_female
	return cfg.voice_narrator


class SiliconFlowTTSClient:
	def __init__(self, cfg: SiliconFlowTTSConfig):
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

	def synthesize(
		self,
		text: str,
		*,
		voice: Optional[str] = None,
		style_prompt: Optional[str] = None,
		speed: float = 1.0,
		gain: float = 0.0,
		sample_rate: Optional[int] = None,
		response_format: Optional[str] = None,
	) -> bytes:
		"""
		合成音频，返回 wav bytes。
		CosyVoice2：input = style_prompt + <|endofprompt|> + text。
		per-call voice 覆盖默认。
		"""
		use_style = (os.environ.get("TTS_USE_STYLE_PROMPT", "endofprompt") or "endofprompt").strip().lower()
		input_text, _ = build_input_text(
			text,
			style_prompt,
			use_style,
			model=self.cfg.model,
		)

		v = voice or self.cfg.voice_narrator
		sr = sample_rate or self.cfg.sample_rate
		fmt = response_format or self.cfg.response_format

		payload = {
			"model": self.cfg.model,
			"input": input_text,
			"voice": v,
			"response_format": fmt,
			"sample_rate": sr,
			"speed": speed,
			"gain": gain,
		}

		r = self._client.post("/audio/speech", json=payload)
		if r.status_code < 200 or r.status_code >= 300:
			body_snip = (r.text or "")[:1000]
			raise ValueError(f"SiliconFlow TTS HTTP {r.status_code}: {body_snip}")

		from novel2comic.core.audio_utils import _ensure_wav
		return _ensure_wav(r.content)
