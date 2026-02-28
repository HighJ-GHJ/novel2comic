# -*- coding: utf-8 -*-
"""Align-lite 时间轴单元测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_srt_time_format():
	from novel2comic.stages.align import _ms_to_srt_time
	assert _ms_to_srt_time(0) == "00:00:00,000"
	assert _ms_to_srt_time(65000) == "00:01:05,000"


def test_ass_time_format():
	from novel2comic.stages.align import _ms_to_srt_time, _write_srt, _write_ass
	entries = [(0, 1000, "第一句"), (1000, 2500, "第二句")]
	with tempfile.TemporaryDirectory() as d:
		srt_path = Path(d) / "test.srt"
		ass_path = Path(d) / "test.ass"
		_write_srt(entries, srt_path)
		_write_ass(entries, ass_path)
		assert srt_path.exists()
		assert ass_path.exists()
		content = srt_path.read_text(encoding="utf-8")
		assert "00:00:00,000" in content
		assert "00:00:01,000" in content
		assert "第一句" in content
