# -*- coding: utf-8 -*-
"""
冒烟测试：Director Review 阶段。
构造最小 shotscript（含句末、反转、场景跳转），跑 director_review，验收 gap 与工件。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# 项目根
ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
	# 找一个已有 shotscript 的 chapter（planned 或更晚）
	candidates = list(ROOT.glob("output/*/ch_*/manifest.json"))
	planned = []
	for p in candidates:
		try:
			m = json.loads(p.read_text(encoding="utf-8"))
			st = m.get("status", {}).get("stage", "")
			if st in ("planned", "directed", "tts_done", "aligned", "rendered") and (p.parent / "shotscript.json").exists():
				planned.append(p.parent)
		except Exception:
			pass

	if not planned:
		# 创建临时 chapter
		tmp = ROOT / "output" / "_smoke_director" / "ch_0001"
		tmp.mkdir(parents=True, exist_ok=True)
		(ROOT / "output" / "_smoke_director").mkdir(parents=True, exist_ok=True)

		# 最小 shotscript
		shotscript = {
			"schema_version": "shotscript.v0.1",
			"shots": [
				{
					"shot_id": "ch_0001_shot_0000",
					"block_id": 0,
					"order": 0,
					"text": {"raw_text": "他愣住了。"},
					"speech": {"default": {"emotion": "neutral", "pace": "normal"}, "segments": [{"seg_id": "s0", "kind": "narration", "raw_text": "他愣住了。"}]},
				},
				{
					"shot_id": "ch_0001_shot_0001",
					"block_id": 0,
					"order": 1,
					"text": {"raw_text": "次日清晨。"},
					"speech": {"default": {"emotion": "neutral", "pace": "normal"}, "segments": [{"seg_id": "s1", "kind": "narration", "raw_text": "次日清晨。"}]},
				},
				{
					"shot_id": "ch_0001_shot_0002",
					"block_id": 1,
					"order": 2,
					"text": {"raw_text": "他愣住了……"},
					"speech": {"default": {"emotion": "sad", "pace": "slow"}, "segments": [{"seg_id": "s2", "kind": "narration", "raw_text": "他愣住了……"}]},
				},
			],
		}
		tmp.joinpath("shotscript.json").write_text(json.dumps(shotscript, ensure_ascii=False, indent=2), encoding="utf-8")

		manifest = {
			"schema_version": "chapterpack.v0.1",
			"meta": {"novel_id": "_smoke_director", "chapter_id": "ch_0001"},
			"status": {"stage": "planned", "done": ["ingest", "segment", "plan"]},
			"durations": {},
			"providers": {},
			"artifacts": {},
			"shots_index": {},
		}
		tmp.joinpath("manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

		chapter_dir = str(tmp)
	else:
		chapter_dir = str(planned[0])

	# 禁用 LLM，用 fallback
	env = os.environ.copy()
	env["DIRECTOR_REVIEW_ENABLED"] = "0"

	env["PYTHONPATH"] = str(ROOT / "src")
	r = subprocess.run(
		[sys.executable, "-m", "novel2comic.cli", "run", "--chapter_dir", chapter_dir, "--until", "director_review"],
		cwd=str(ROOT),
		env=env,
		capture_output=True,
		text=True,
	)

	if r.returncode != 0:
		print(f"[FAIL] director_review exit {r.returncode}")
		print(r.stderr or r.stdout)
		return 1

	# 验收
	pack = Path(chapter_dir)
	directed_path = pack / "shotscript.directed.json"
	review_path = pack / "director" / "director_review.json"

	if not directed_path.exists():
		print("[FAIL] shotscript.directed.json not created")
		return 1
	if not review_path.exists():
		print("[FAIL] director/director_review.json not created")
		return 1

	directed = json.loads(directed_path.read_text(encoding="utf-8"))
	shots = directed.get("shots", [])

	# 至少有一个 shot 的 gap_after_ms 明显大于默认（句末 250、省略号 600、block 边界 1200）
	large_gaps = [s.get("gap_after_ms", 0) for s in shots if s.get("gap_after_ms", 0) >= 250]
	if not large_gaps:
		print("[FAIL] no shot has gap_after_ms >= 250")
		return 1

	# text 完全不变
	orig = json.loads((pack / "shotscript.json").read_text(encoding="utf-8"))
	for i, (o, d) in enumerate(zip(orig.get("shots", []), directed.get("shots", []))):
		if o.get("text") != d.get("text"):
			print(f"[FAIL] text changed in shot {i}")
			return 1

	print("[OK] director_review smoke passed")
	return 0


if __name__ == "__main__":
	sys.exit(main())
