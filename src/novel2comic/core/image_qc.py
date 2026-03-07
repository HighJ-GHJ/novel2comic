# -*- coding: utf-8 -*-
"""
novel2comic/core/image_qc.py

轻量 QC：文件存在、尺寸 16:9、亮度/方差阈值（避免全黑/全白/纯色）。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# 允许尺寸误差（px）
SIZE_TOLERANCE = 1
# 亮度均值：避免全黑(<10) 或全白(>245)
BRIGHTNESS_MIN = 10
BRIGHTNESS_MAX = 245
# 方差：避免纯色（方差过小）
VARIANCE_MIN = 100


def qc_image(path: Path, expected_w: int, expected_h: int) -> tuple[bool, str]:
	"""
	检查图片是否通过 QC。
	Returns: (pass, reason)
	"""
	if not path.exists():
		return False, "file_not_found"
	try:
		img = Image.open(path).convert("RGB")
	except Exception as e:
		return False, f"invalid_image:{e}"

	w, h = img.size
	if abs(w - expected_w) > SIZE_TOLERANCE or abs(h - expected_h) > SIZE_TOLERANCE:
		return False, f"size_mismatch:{w}x{h}_expected_{expected_w}x{expected_h}"

	pixels = list(img.getdata())
	if not pixels:
		return False, "empty_image"

	# 亮度均值
	mean = sum(sum(p) for p in pixels) / (len(pixels) * 3)
	if mean < BRIGHTNESS_MIN:
		return False, f"too_dark:mean={mean:.1f}"
	if mean > BRIGHTNESS_MAX:
		return False, f"too_bright:mean={mean:.1f}"

	# 方差（简化：用 R 通道方差代表）
	r_vals = [p[0] for p in pixels]
	variance = sum((x - mean) ** 2 for x in r_vals) / len(r_vals)
	if variance < VARIANCE_MIN:
		return False, f"too_flat:variance={variance:.1f}"

	return True, "ok"


def parse_size(size_str: str) -> tuple[int, int]:
	"""Parse '1024x576' -> (1024, 576)."""
	parts = size_str.strip().lower().split("x")
	if len(parts) != 2:
		raise ValueError(f"invalid size: {size_str}")
	return int(parts[0]), int(parts[1])
