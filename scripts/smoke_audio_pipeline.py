# -*- coding: utf-8 -*-
"""
scripts/smoke_audio_pipeline.py

冒烟测试：对一个小 ChapterPack 跑 --until render。
需要 .env 配置 SILICONFLOW_API_KEY 等。
检查：chapter.wav / chapter.ass / preview.mp4 存在。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> argparse.Namespace:
	ap = argparse.ArgumentParser()
	ap.add_argument("--chapter_dir", required=True, help="ChapterPack 路径，如 output/xuanjianxianzu/ch_0001")
	ap.add_argument("--limit_shots", type=int, default=3, help="仅处理前 N 个 shots（用于快速冒烟）")
	args = ap.parse_args()

	chapter_dir = Path(args.chapter_dir)
	if not chapter_dir.exists():
		sys.exit(f"chapter_dir not found: {chapter_dir}")

	# 若 limit_shots < 全部，则临时修改 shotscript 只保留前 N 个 shots
	shotscript_path = chapter_dir / "shotscript.json"
	if shotscript_path.exists() and args.limit_shots > 0:
		data = json.loads(shotscript_path.read_text(encoding="utf-8"))
		shots = data.get("shots", [])
		if len(shots) > args.limit_shots:
			# 备份并截断
			backup = chapter_dir / "shotscript.json.bak"
			backup.write_text(shotscript_path.read_text(encoding="utf-8"), encoding="utf-8")
			data["shots"] = shots[: args.limit_shots]
			shotscript_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
			print(f"[smoke] limited to {args.limit_shots} shots")

	# 运行 pipeline
	r = subprocess.run(
		[sys.executable, "-m", "novel2comic", "run", "--chapter_dir", str(chapter_dir), "--until", "render"],
		cwd=Path(__file__).resolve().parent.parent,
		capture_output=True,
		text=True,
	)
	if r.returncode != 0:
		print(f"[FAIL] pipeline exit {r.returncode}")
		print(r.stderr)
		sys.exit(1)

	# 检查产物
	checks = [
		chapter_dir / "audio" / "chapter.wav",
		chapter_dir / "subtitles" / "chapter.ass",
		chapter_dir / "subtitles" / "chapter.srt",
		chapter_dir / "video" / "preview.mp4",
	]
	missing = [p for p in checks if not p.exists()]
	if missing:
		print(f"[FAIL] missing: {missing}")
		sys.exit(1)

	# 恢复 shotscript（若备份存在）
	backup = chapter_dir / "shotscript.json.bak"
	if backup.exists():
		backup.rename(shotscript_path)
		print("[smoke] restored shotscript")

	print("[OK] smoke passed: chapter.wav, chapter.ass, chapter.srt, preview.mp4 exist")
	return args


if __name__ == "__main__":
	main()
