# -*- coding: utf-8 -*-
"""
novel2comic/stages/director_review.py

Director Review 阶段：对 ShotScript 做导演视角审阅，输出 patch-only 补丁。
位置：plan 之后、TTS 之前。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from novel2comic.core.config_loader import get_stage_config
from novel2comic.core.io import ChapterPaths, find_project_root
from novel2comic.core.manifest import load_manifest, save_manifest
from novel2comic.director_review.apply import apply_director_patch
from novel2comic.director_review.client import chat_director_review
from novel2comic.director_review.fallback import apply_fallback_gaps
from novel2comic.director_review.prompt import SYSTEM_PROMPT, build_user_prompt
from novel2comic.stages.base import StageContext


def _director_config() -> dict:
	cfg = get_stage_config("director_review")
	return {
		"enabled": cfg.get("enabled", True),
		"apply_patch": cfg.get("apply_patch", True),
		"model": (cfg.get("model") or "").strip() or None,
		"temperature": float(cfg.get("temperature") or 0.2),
	}


class DirectorReviewStage:
	name = "director_review"

	def run(self, paths: ChapterPaths, ctx: StageContext) -> None:
		if not paths.shotscript.exists():
			raise FileNotFoundError(f"missing {paths.shotscript}")

		data = json.loads(paths.shotscript.read_text(encoding="utf-8"))
		shots = data.get("shots", [])
		if not shots:
			raise ValueError("shotscript has no shots")

		m = load_manifest(paths.manifest)
		if m.stage not in ("planned", "directed", "images_done", "tts_done", "aligned", "rendered"):
			raise ValueError(f"Director Review requires planned stage, got {m.stage}")

		# 若已 directed，跳过
		if m.stage == "directed" and paths.shotscript_directed.exists():
			print("[INFO] director_review already done, skip")
			return

		paths.director_dir.mkdir(parents=True, exist_ok=True)
		paths.logs_dir.mkdir(parents=True, exist_ok=True)

		dr_cfg = _director_config()
		t0 = time.perf_counter()
		director_review: dict
		used_fallback = False

		if dr_cfg["enabled"]:
			try:
				from novel2comic.providers.llm.siliconflow_client import load_siliconflow_client

				llm = load_siliconflow_client(project_root=str(find_project_root()))
				if dr_cfg["model"]:
					llm.cfg.model = dr_cfg["model"]
				temperature = dr_cfg["temperature"]
				# 临时覆盖 temperature（siliconflow_client 写死 0.2，此处不强制改）
				try:
					user_prompt = build_user_prompt(ctx.chapter_id, shots)
					director_review = chat_director_review(llm, SYSTEM_PROMPT, user_prompt)
					director_review.setdefault("meta", {})["model"] = llm.cfg.model
					director_review.setdefault("meta", {})["fallback"] = False
				finally:
					llm.close()
			except Exception as e:
				used_fallback = True
				director_review = {
					"meta": {
						"chapter_id": ctx.chapter_id,
						"model": "",
						"fallback": True,
						"error": str(e)[:500],
					},
					"global_notes": [],
					"risks": [],
					"patch": {"shots": []},
				}
				m.add_warning(f"Director Review LLM failed: {type(e).__name__}: {str(e)[:200]}")
		else:
			used_fallback = True
			director_review = {
				"meta": {"chapter_id": ctx.chapter_id, "model": "", "fallback": True},
				"global_notes": [],
				"risks": [],
				"patch": {"shots": []},
			}

		elapsed_ms = int((time.perf_counter() - t0) * 1000)
		director_review.setdefault("meta", {})["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
		director_review.setdefault("meta", {})["timings"] = {"director_review_ms": elapsed_ms}

		# 落盘 director_review.json
		paths.director_review_json.write_text(
			json.dumps(director_review, ensure_ascii=False, indent=2),
			encoding="utf-8",
		)

		# 可选：落盘 prompt/response 到 logs
		if paths.logs_dir.exists():
			# 简化：不落盘完整 response（已在 director_review.json）
			pass

		# 合并 patch 或 fallback
		if used_fallback or not director_review.get("patch", {}).get("shots"):
			directed_shots = apply_fallback_gaps(shots)
			directed_data = dict(data)
			directed_data["shots"] = directed_shots
		elif dr_cfg["apply_patch"]:
			directed_data, report = apply_director_patch(data, director_review)
			if report.get("invariant_violation"):
				directed_shots = apply_fallback_gaps(shots)
				directed_data = dict(data)
				directed_data["shots"] = directed_shots
				m.add_warning(f"Director patch apply failed: {report.get('invariant_violation')}")
		else:
			directed_shots = apply_fallback_gaps(shots)
			directed_data = dict(data)
			directed_data["shots"] = directed_shots

		# 确保每个 shot 有 gap_after_ms（合并为单次遍历）
		from novel2comic.director_review.fallback import fallback_gap_after_ms

		for i, s in enumerate(directed_data["shots"]):
			if "gap_after_ms" not in s:
				next_s = directed_data["shots"][i + 1] if i + 1 < len(directed_data["shots"]) else None
				directed_data["shots"][i]["gap_after_ms"] = fallback_gap_after_ms(s, next_s)

		paths.shotscript_directed.write_text(
			json.dumps(directed_data, ensure_ascii=False, indent=2),
			encoding="utf-8",
		)

		# 更新 manifest
		m.set_stage("directed")
		m.mark_done("director_review")
		m.durations["director_review_ms"] = elapsed_ms
		m.providers["director_review"] = {
			"model": director_review.get("meta", {}).get("model", ""),
			"fallback": used_fallback,
		}
		m.artifacts["director_review_json"] = "director/director_review.json"
		m.artifacts["shotscript_directed"] = "shotscript.directed.json"
		save_manifest(paths.manifest, m)
