# -*- coding: utf-8 -*-
"""
tests/test_extract_must_have.py

extract_must_have 关键词提取单元测试。
"""

from __future__ import annotations

from novel2comic.core.image_prompt import extract_must_have


def test_extract_basic():
	shot = {"text": {"subtitle_text": "他站在路灯下，表情警惕。雨后路面反光。"}}
	r = extract_must_have(shot, 8)
	assert len(r) <= 8
	assert len(r) >= 1
	# 应包含从文本切分出的片段（2~6 字）
	joined = "".join(r)
	assert "路灯" in joined or "表情" in joined or "路面" in joined

def test_extract_empty():
	shot = {"text": {}}
	assert extract_must_have(shot) == []

def test_extract_max_items():
	shot = {"text": {"raw_text": "一、二、三、四、五、六、七、八、九、十"}}
	r = extract_must_have(shot, 5)
	assert len(r) <= 5
