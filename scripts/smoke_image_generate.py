#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/smoke_image_generate.py

冒烟测试：读取某章 shotscript 前 N 个 shot，跑 Draft 出图。
默认用 Qwen/Qwen-Image（IMAGE_PROVIDER=qwen），输出 images/shots/*。
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from novel2comic.core.image_prompt import CAMERA_ZH, QWEN_NEGATIVE, build_prompt_qwen_draft
from novel2comic.core.image_qc import parse_size, qc_image
from novel2comic.core.io import chapter_paths, find_project_root
from novel2comic.providers.image.image_qwen import (
	DEFAULT_CFG,
	DEFAULT_IMAGE_SIZE,
	DEFAULT_STEPS,
	generate_t2i as qwen_t2i,
	load_qwen_config,
)


def _camera(shot: dict) -> str:
	cam = (shot.get("image", {}) or {}).get("camera") or "medium shot"
	return CAMERA_ZH.get(cam.lower(), "中景")


def main() -> int:
	import argparse
	p = argparse.ArgumentParser()
	p.add_argument("--chapter_dir", default="output/xuanjianxianzu/ch_0001", help="ChapterPack 路径")
	p.add_argument("--limit", type=int, default=5, help="只处理前 N 个 shot")
	args = p.parse_args()

	paths = chapter_paths(args.chapter_dir)
	shotscript_path = paths.effective_shotscript()
	if not shotscript_path.exists():
		print(f"[FAIL] missing {shotscript_path}")
		return 1

	data = json.loads(shotscript_path.read_text(encoding="utf-8"))
	shots = data.get("shots", [])[: args.limit]
	if not shots:
		print("[FAIL] no shots")
		return 1

	paths.images_shots_dir.mkdir(parents=True, exist_ok=True)
	cfg = load_qwen_config(project_root=str(find_project_root()))
	expected_w, expected_h = parse_size(DEFAULT_IMAGE_SIZE)

	print(f"[INFO] size={DEFAULT_IMAGE_SIZE} steps={DEFAULT_STEPS} cfg={DEFAULT_CFG}")

	for shot in shots:
		shot_id = shot.get("shot_id", "")
		prompt = build_prompt_qwen_draft(shot, _camera(shot))
		seed = random.randint(0, 999_999_999)
		try:
			img, meta = qwen_t2i(
				prompt,
				negative_prompt=QWEN_NEGATIVE,
				image_size=DEFAULT_IMAGE_SIZE,
				steps=DEFAULT_STEPS,
				cfg=DEFAULT_CFG,
				seed=seed,
				config=cfg,
			)
		except Exception as e:
			print(f"[FAIL] {shot_id} error={e}")
			continue

		png_path = paths.images_shots_dir / f"shot_{shot_id}.png"
		img.save(png_path, "PNG")
		ok, reason = qc_image(png_path, expected_w, expected_h)
		print(f"[OK] {shot_id} ref_used=none seed={meta.get('seed')} qc_pass={ok} path={png_path}")
		print(f"      prompt: {prompt[:100]}...")
		if not ok:
			print(f"      qc_reason={reason}")

	return 0


if __name__ == "__main__":
	sys.exit(main())
