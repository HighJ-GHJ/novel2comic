# -*- coding: utf-8 -*-
"""
scripts/smoke_tts_cosyvoice2.py

CosyVoice2 TTS 冒烟测试：对 ChapterPack 跑 tts 阶段，验证 wav 产出。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from novel2comic.core.audio_utils import wav_duration_ms


def main() -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--chapter_dir", required=True, help="ChapterPack 路径")
	ap.add_argument("--limit_shots", type=int, default=10, help="仅处理前 N 个 shots")
	args = ap.parse_args()

	chapter_dir = Path(args.chapter_dir)
	if not chapter_dir.exists():
		sys.exit(f"chapter_dir not found: {chapter_dir}")

	# 临时截断 shotscript
	shotscript_path = chapter_dir / "shotscript.json"
	if not shotscript_path.exists():
		sys.exit("shotscript.json not found")

	import json
	data = json.loads(shotscript_path.read_text(encoding="utf-8"))
	shots = data.get("shots", [])
	if len(shots) > args.limit_shots:
		backup = chapter_dir / "shotscript.json.bak"
		backup.write_text(shotscript_path.read_text(encoding="utf-8"), encoding="utf-8")
		data["shots"] = shots[: args.limit_shots]
		shotscript_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
		print(f"[smoke] limited to {args.limit_shots} shots")

	# 跑 tts
	import subprocess
	r = subprocess.run(
		[sys.executable, "-m", "novel2comic", "run", "--chapter_dir", str(chapter_dir), "--until", "tts"],
		cwd=Path(__file__).resolve().parent.parent,
		capture_output=True,
		text=True,
	)
	if r.returncode != 0:
		print(f"[FAIL] pipeline exit {r.returncode}")
		print(r.stderr)
		# 恢复 shotscript
		backup = chapter_dir / "shotscript.json.bak"
		if backup.exists():
			backup.rename(shotscript_path)
		return 1

	# 检查产物
	chapter_wav = chapter_dir / "audio" / "chapter.wav"
	if not chapter_wav.exists():
		print("[FAIL] chapter.wav not found")
		return 1

	duration_ms = wav_duration_ms(chapter_wav.read_bytes())
	print(f"[OK] chapter.wav exists, duration={duration_ms}ms ({duration_ms/1000:.1f}s)")

	# 恢复 shotscript
	backup = chapter_dir / "shotscript.json.bak"
	if backup.exists():
		backup.rename(shotscript_path)
		print("[smoke] restored shotscript")

	print("[OK] smoke_tts_cosyvoice2 passed")
	return 0


if __name__ == "__main__":
	sys.exit(main())
