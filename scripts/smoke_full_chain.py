#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/smoke_full_chain.py

全链路冒烟测试：ingest → segment → plan → director_review → anchors → image → tts → align → render。
- 可选 --limit_shots 仅处理前 N 个 shot（快速验证）
- 可选 --reset_image 重置 image+anchors 阶段后重跑
- 需要 .env 配置 SILICONFLOW_API_KEY
- 验证：images/anchors/*、images/shots/*.png、audio/chapter.wav、subtitles/*、video/preview.mp4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from novel2comic.core.io import find_project_root


def main() -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--chapter_dir", required=True, help="ChapterPack 路径")
	ap.add_argument("--limit_shots", type=int, default=5, help="仅处理前 N 个 shots（0=不限制）")
	ap.add_argument("--reset_image", action="store_true", help="重置 image 阶段后重跑（清空 images、manifest 回退到 directed）")
	args = ap.parse_args()

	chapter_dir = Path(args.chapter_dir).resolve()
	if not chapter_dir.exists():
		print(f"[FAIL] chapter_dir not found: {chapter_dir}")
		return 1

	project_root = find_project_root(chapter_dir)

	# 若缺 chapter_clean.txt，尝试 prepare
	text_clean = chapter_dir / "text" / "chapter_clean.txt"
	if not text_clean.exists():
		chapters_dir = chapter_dir.parent / "chapters"
		ch_name = chapter_dir.name
		if (chapters_dir / f"{ch_name}.txt").exists():
			subprocess.run(
				[sys.executable, "-m", "novel2comic", "prepare", "--chapters_dir", str(chapters_dir), "--chapter", ch_name],
				cwd=project_root,
				text=True,
				check=False,
			)
			print(f"[smoke] ran prepare for {ch_name}")
		if not text_clean.exists():
			print(f"[FAIL] missing {text_clean}，请先 run: novel2comic prepare --chapters_dir ... --chapter {ch_name}")
			return 1

	shotscript_path = chapter_dir / "shotscript.json"
	backup_path = chapter_dir / "shotscript.json.bak"
	manifest_path = chapter_dir / "manifest.json"
	images_dir = chapter_dir / "images" / "shots"
	anchors_dir = chapter_dir / "images" / "anchors"

	# 可选：重置 image+anchors 阶段（回退到 directed，清空 images、anchors）
	if args.reset_image and manifest_path.exists():
		m = json.loads(manifest_path.read_text(encoding="utf-8"))
		m["status"]["stage"] = "directed"
		done = m["status"].get("done", [])
		if "image" in done:
			m["status"]["done"] = [d for d in done if d != "image"]
		m["images_index"] = {}
		manifest_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
		if images_dir.exists():
			for f in images_dir.glob("shot_*"):
				f.unlink()
			for f in images_dir.glob("*.meta.json"):
				f.unlink()
		if anchors_dir.exists():
			for d in anchors_dir.glob("characters/*"):
				if d.is_dir():
					for f in d.glob("*.png"):
						f.unlink()
			meta = anchors_dir / "anchors_meta.json"
			if meta.exists():
				meta.unlink()
		print("[smoke] reset image + anchors stage")

	# 可选：截断 shotscript（segment 会覆盖，故需先跑 segment 再截断）
	if args.limit_shots > 0:
		# 1) 先跑到 segment
		r_seg = subprocess.run(
			[sys.executable, "-m", "novel2comic", "run", "--chapter_dir", str(chapter_dir), "--until", "segment"],
			cwd=project_root,
			text=True,
			capture_output=True,
		)
		if r_seg.returncode != 0:
			print(f"[FAIL] segment exit {r_seg.returncode}: {(r_seg.stderr or '')[:500]}")
			return 1
		# 2) 截断
		if shotscript_path.exists():
			data = json.loads(shotscript_path.read_text(encoding="utf-8"))
			shots = data.get("shots", [])
			if len(shots) > args.limit_shots:
				backup_path.write_text(shotscript_path.read_text(encoding="utf-8"), encoding="utf-8")
				data["shots"] = shots[: args.limit_shots]
				shotscript_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
				print(f"[smoke] limited to {args.limit_shots} shots (after segment)")

	# 运行 pipeline（若已截断，从 plan 开始避免 segment 覆盖）
	run_args = [sys.executable, "-m", "novel2comic", "run", "--chapter_dir", str(chapter_dir), "--until", "render"]
	if backup_path.exists():
		run_args.extend(["--from_stage", "plan"])
		print("[RUN] novel2comic run --from_stage plan --until render ...")
	else:
		print("[RUN] novel2comic run --until render ...")
	r = subprocess.run(run_args, cwd=project_root, text=True)
	if r.returncode != 0:
		print(f"[FAIL] pipeline exit {r.returncode}")
		if r.stderr:
			print(r.stderr)
		return 1

	# 验证产物
	checks = [
		chapter_dir / "audio" / "chapter.wav",
		chapter_dir / "subtitles" / "chapter.ass",
		chapter_dir / "subtitles" / "chapter.srt",
		chapter_dir / "video" / "preview.mp4",
	]
	missing = [p for p in checks if not p.exists()]
	if missing:
		print(f"[FAIL] missing: {missing}")
		return 1

	# 检查图片与 anchors
	images = list(images_dir.glob("shot_*.png")) if images_dir.exists() else []
	anchor_chars = list((anchors_dir / "characters").glob("*/anchor.png")) if (anchors_dir / "characters").exists() else []
	if not images:
		print("[WARN] no images in images/shots/ (image stage may have failed)")
	if not anchor_chars and args.limit_shots > 0:
		print("[WARN] no anchors (anchors stage may have skipped if no primary_char_id)")

	print("[OK] smoke passed: chapter.wav, chapter.ass, chapter.srt, preview.mp4 exist")
	if images:
		print(f"      images: {len(images)} shots")
	if anchor_chars:
		print(f"      anchors: {len(anchor_chars)} chars")

	# 恢复 shotscript
	if backup_path.exists():
		backup_path.rename(shotscript_path)
		print("[smoke] restored shotscript")

	return 0


if __name__ == "__main__":
	sys.exit(main())