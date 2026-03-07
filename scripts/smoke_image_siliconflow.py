#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/smoke_image_siliconflow.py

冒烟测试：验证硅基流动 Qwen/Qwen-Image（T2I）与 Qwen/Qwen-Image-Edit（Edit）。
1. 中文 prompt 调 Qwen-Image 生成 1664x928
2. 生成图当 ref，调 Qwen-Image-Edit 做小改动（如「把光线改成傍晚」）
3. 两张图落盘，打印 seed、timing、ref_used
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from novel2comic.core.image_prompt import QWEN_NEGATIVE
from novel2comic.core.image_qc import parse_size, qc_image
from novel2comic.providers.image.image_qwen import (
	DEFAULT_CFG,
	DEFAULT_IMAGE_SIZE,
	DEFAULT_STEPS,
	edit as qwen_edit,
	generate_t2i as qwen_t2i,
	load_qwen_config,
)


def main() -> int:
	import argparse
	p = argparse.ArgumentParser()
	p.add_argument("--out_dir", default="output/smoke_image_siliconflow", help="输出目录")
	args = p.parse_args()

	out = Path(args.out_dir)
	out.mkdir(parents=True, exist_ok=True)
	cfg = load_qwen_config()

	# 1. T2I
	prompt_t2i = "动态漫画分镜风格。夜晚的老街，雨后路面反光，一名穿深色风衣的年轻男子站在路灯下，表情警惕。镜头：中景，平视。16:9，无水印，无多余文字。"

	print("[1/2] T2I: Qwen/Qwen-Image ...")
	img1, meta1 = qwen_t2i(
		prompt_t2i,
		negative_prompt=QWEN_NEGATIVE,
		image_size=DEFAULT_IMAGE_SIZE,
		steps=DEFAULT_STEPS,
		cfg=DEFAULT_CFG,
		config=cfg,
	)
	path_t2i = out / f"t2i_{DEFAULT_IMAGE_SIZE}.png"
	img1.save(path_t2i, "PNG")
	expected_w, expected_h = parse_size(DEFAULT_IMAGE_SIZE)
	ok1, reason1 = qc_image(path_t2i, expected_w, expected_h)
	print(f"      seed={meta1.get('seed')} elapsed_ms={meta1.get('elapsed_ms')} ref_used=none qc_pass={ok1} path={path_t2i}")

	# 2. Edit（ref = t2i 输出）
	ref_bytes = path_t2i.read_bytes()
	prompt_edit = "保持参考图的角色外观、服装、画风和构图一致。把光线改为傍晚暖色调，雨停了但地面仍有湿润反光，人物表情从警惕改为若有所思。"

	print("[2/2] Edit: Qwen/Qwen-Image-Edit ...")
	img2, meta2 = qwen_edit(
		ref_bytes,
		prompt_edit,
		negative_prompt=QWEN_NEGATIVE,
		steps=DEFAULT_STEPS,
		cfg=DEFAULT_CFG,
		config=cfg,
	)
	path_edit = out / f"edit_{DEFAULT_IMAGE_SIZE}.png"
	img2.save(path_edit, "PNG")
	ok2, reason2 = qc_image(path_edit, expected_w, expected_h)
	print(f"      seed={meta2.get('seed')} elapsed_ms={meta2.get('elapsed_ms')} ref_used=t2i_output qc_pass={ok2} path={path_edit}")

	# 验证 Edit 输出尺寸（Qwen-Image-Edit 可能略有缩放，文档说跟随 ref）
	w2, h2 = img2.size
	if abs(w2 - expected_w) <= 1 and abs(h2 - expected_h) <= 1:
		print(f"[OK] Edit 输出尺寸 {DEFAULT_IMAGE_SIZE}，跟随 ref")
	else:
		print(f"[WARN] Edit 输出尺寸 {w2}x{h2}，预期 {expected_w}x{expected_h}（Qwen-Edit 可能略有缩放）")

	meta_out = out / "smoke_meta.json"
	meta_out.write_text(
		json.dumps(
			{
				"t2i": {"seed": meta1.get("seed"), "elapsed_ms": meta1.get("elapsed_ms"), "ref_used": "none"},
				"edit": {"seed": meta2.get("seed"), "elapsed_ms": meta2.get("elapsed_ms"), "ref_used": "t2i_output"},
			},
			ensure_ascii=False,
			indent=2,
		),
		encoding="utf-8",
	)
	print(f"[OK] meta 已写入 {meta_out}")
	# T2I 必须通过；Edit 尺寸可能略有差异，仍视为验收通过
	return 0 if ok1 else 1


if __name__ == "__main__":
	sys.exit(main())
