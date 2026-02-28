# -*- coding: utf-8 -*-
"""
novel2comic/core/speech_schema.py

Speech 相关常量与默认模板。deterministic，代码内固定。
"""

from __future__ import annotations

# 离散集合（任务书约定）
INTENSITY_VALUES = (0.15, 0.35, 0.55, 0.75)
PACE_VALUES = ("slow", "normal", "fast")
PAUSE_MS_VALUES = (0, 80, 150, 250)
MODE_VALUES = ("narration", "quoted_dialogue", "inner_thought")
TONE_VALUES = ("stern", "gentle", "playful", "anxious", "angry", "weak", "authoritative", "neutral")
GENDER_HINT_VALUES = ("male", "female", "unknown")

# 速度映射（扩大差异：slow 更慢，fast 略快）
PACE_TO_SPEED = {"slow": 0.88, "normal": 1.0, "fast": 1.10}

# 有声书 narrator 基础模板
NARRATOR_BASE = "有声书朗读风格，清晰克制。疑问句尾轻微上扬，感叹句更有力，句末收音，关键处放慢并留白。"

# emotion + intensity 注入（短句，~30 字内）
EMOTION_INTENSITY_TEMPLATES = {
	("suspense", "high"): "语气压低，留白更明显。",
	("suspense", "mid"): "语气略沉，留白。",
	("warm", "mid"): "语气温和，节奏舒缓。",
	("warm", "high"): "语气温暖，略慢。",
	("tense", "high"): "语速略快，语气紧绷但克制。",
	("tense", "mid"): "语气略紧。",
	("sad", "mid"): "语速略慢，语气低沉。",
	("sad", "high"): "语速慢，语气低沉，留白。",
	("angry", "high"): "语气略重，短促，不嘶吼。",
	("angry", "mid"): "语气略沉。",
	("playful", "mid"): "语气略轻快，带笑意，不夸张。",
	("anxious", "mid"): "语速略快，呼吸更急。",
	("neutral", "mid"): "",
	("neutral", "high"): "关键处放慢。",
	("default",): "",
}

# quote 轻区分模板（保留兼容）
QUOTE_TEMPLATES = {
	("male", "stern"): "语气更沉、短促克制，句尾收紧，不夸张。",
	("female", "gentle"): "语气更柔和，略慢，带温度但不娇嗲。",
	("male", "gentle"): "语气温和，略慢，沉稳。",
	("female", "stern"): "语气更沉、克制，不夸张。",
	("unknown", "anxious"): "语速略快，呼吸更急，短暂停顿更多。",
	("unknown", "angry"): "语气略重，短促，不嘶吼。",
	("unknown", "playful"): "语气略轻快，带笑意，不夸张。",
	("unknown", "weak"): "语气略虚，稍慢，不夸张。",
	("unknown", "authoritative"): "语气沉稳有力，略慢，不吼。",
	("default",): NARRATOR_BASE,
}

# 兼容旧引用
NARRATOR_TEMPLATE = NARRATOR_BASE

# CosyVoice2 短指令（2~6 字标签式，无换行/引号/括号，避免被当正文读出）
COSYVOICE2_SHORT_INSTRUCTIONS = {
	"suspense": "悬疑",
	"warm": "温暖",
	"tense": "紧张",
	"sad": "悲伤",
	"angry": "愤怒",
	"playful": "轻快",
	"anxious": "焦虑",
	"neutral": "",
	"default": "",
}


def _intensity_bucket(v: float | None) -> str:
	"""将 intensity 0.15~0.75 映射为 high/mid。"""
	if v is None:
		return "mid"
	if v >= 0.55:
		return "high"
	return "mid"


def build_style_prompt(
	kind: str,
	emotion: str | None = None,
	intensity: float | None = None,
	tone: str | None = None,
	gender_hint: str | None = None,
) -> str:
	"""
	Deterministic 生成短 style_prompt（~30 字内）。
	kind: narration | quote
	"""
	base = NARRATOR_BASE
	emotion = emotion or "neutral"
	intensity_b = _intensity_bucket(intensity)
	key = (emotion, intensity_b)
	suffix = EMOTION_INTENSITY_TEMPLATES.get(key) or EMOTION_INTENSITY_TEMPLATES.get(("default",), "")
	if kind == "quote" and (tone or gender_hint):
		quote_suffix = get_quote_style_prompt(gender_hint or "unknown", tone or "neutral")
		if quote_suffix and quote_suffix != base:
			suffix = quote_suffix if not suffix else f"{suffix}{quote_suffix}"
	parts = [base]
	if suffix:
		parts.append(suffix)
	return "".join(parts)


def cosyvoice2_short_instruction(emotion: str | None = None) -> str:
	"""
	CosyVoice2 短指令，符合硅基流动文档示例格式。
	文档：instruction + <|endofprompt|> + 正文，instruction 需简短（~10 字）。
	"""
	e = emotion or "neutral"
	return COSYVOICE2_SHORT_INSTRUCTIONS.get(e) or COSYVOICE2_SHORT_INSTRUCTIONS["default"]


def get_quote_style_prompt(gender_hint: str, tone: str) -> str:
	"""根据 gender_hint + tone 返回 style_prompt。"""
	key = (gender_hint, tone)
	if key in QUOTE_TEMPLATES:
		return QUOTE_TEMPLATES[key]
	key2 = ("unknown", tone)
	if key2 in QUOTE_TEMPLATES:
		return QUOTE_TEMPLATES[key2]
	return QUOTE_TEMPLATES[("default",)]


def default_speech() -> dict:
	"""Shot 级默认 speech，fallback 用。"""
	return {
		"default": {
			"emotion": "neutral",
			"intensity": 0.35,
			"pace": "normal",
			"pause_ms": 80,
			"mode": "narration",
		},
		"segments": [],
	}


def default_segment(seg_id: str, kind: str, raw_text: str) -> dict:
	"""单个 segment 默认结构。"""
	return {
		"seg_id": seg_id,
		"kind": kind,
		"raw_text": raw_text,
		"speaker": "unknown",
		"gender_hint": "unknown",
		"tone": "neutral",
		"intensity": None,
		"pace": None,
	}
