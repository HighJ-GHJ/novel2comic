# -*- coding: utf-8 -*-
"""
tests/test_apply_prompt_patch.py

apply_prompt_patch 单元测试。
"""

from __future__ import annotations

import pytest

from novel2comic.core.image_prompt import apply_prompt_patch
from novel2comic.core.image_review_schema import SuggestedPatch


def test_apply_prompt_add():
	sp = SuggestedPatch(prompt_add=["保持服装一致"], prompt_remove=[], negative_add=[], rebase="none")
	p, n = apply_prompt_patch("夜晚路灯下男子站立。", "水印,模糊", sp)
	assert "保持服装一致" in p
	assert "水印" in n


def test_apply_prompt_remove():
	sp = SuggestedPatch(prompt_add=[], prompt_remove=["换发型"], negative_add=[], rebase="none")
	p, n = apply_prompt_patch("男子换发型，侧身。", "水印", sp)
	assert "换发型" not in p
	assert "侧身" in p


def test_apply_negative_add():
	sp = SuggestedPatch(prompt_add=[], prompt_remove=[], negative_add=["多人"], rebase="none")
	p, n = apply_prompt_patch("男子站立", "水印,模糊", sp)
	assert "多人" in n
