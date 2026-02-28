# -*- coding: utf-8 -*-
"""
novel2comic/stages/segment.py

目的：
- "分镜切分阶段"：把 chapter_clean.txt 转成 shotscript.json（ShotScript v0.1）。
- baseline split + refine_shot_split（LLM 可用时）-> 稳定 shot_id + skeleton shots。

输入：
- ChapterPack/text/chapter_clean.txt

输出：
- ChapterPack/shotscript.json
- manifest.json：stage -> segmented, durations.num_shots
"""

from __future__ import annotations

import json
from pathlib import Path

from novel2comic.core.io import ChapterPaths
from novel2comic.core.manifest import load_manifest, save_manifest
from novel2comic.core.schemas import Shot
from novel2comic.core.split_baseline import SplitConfig, split_baseline
from novel2comic.stages.base import StageContext


def _shots_to_shotscript_entries(shots: list[Shot], chapter_id: str) -> list[dict]:
	"""将 refine/baseline 的 Shot 转为 ShotScript shots 格式。"""
	return [
		{
			"shot_id": f"{chapter_id}_shot_{i:04d}",
			"block_id": i,
			"order": i,
			"text": {
				"raw_text": s.text,
				"tts_text": s.text,
				"subtitle_text": s.text,
			},
			"image": {},
			"motion": {},
		}
		for i, s in enumerate(shots)
	]


class SegmentStage:
	name = "segment"

	def run(self, paths: ChapterPaths, ctx: StageContext) -> None:
		if not paths.text_clean.exists():
			raise FileNotFoundError(f"missing {paths.text_clean}")

		chapter_text = paths.text_clean.read_text(encoding="utf-8")

		# 1) baseline split
		cfg = SplitConfig(min_chars=80, soft_target=140, hard_cut=220)
		base_shots = split_baseline(chapter_text, cfg)

		# 2) refine（LLM 可用时）；失败则回退 baseline
		shots: list[Shot] = base_shots
		llm_provider = ""
		llm_model = ""

		try:
			from novel2comic.providers.llm.siliconflow_client import load_siliconflow_client
			from novel2comic.skills.refine_shot_split.skill import RefineShotSplitSkill
			from novel2comic.skills.refine_shot_split.schema import Constraints

			# 向上查找含 .env 的项目根目录
			project_root = Path.cwd()
			while project_root != project_root.parent:
				if (project_root / ".env").exists():
					break
				project_root = project_root.parent
			project_root = str(project_root)

			llm = load_siliconflow_client(project_root=project_root)
			try:
				skill = RefineShotSplitSkill(llm)
				c = Constraints(min_shots=60, max_shots=120, forbid_cross_scene_break=True)
				result = skill.run(ctx.chapter_id, base_shots, c)
				shots = result.refined_shots
				if not result.used_fallback:
					llm_provider = "siliconflow"
					llm_model = llm.cfg.model
			finally:
				llm.close()
		except Exception as e:
			# 无 API key 或 LLM 失败：使用 baseline
			pass

		# 3) 转为 ShotScript 格式并写入
		shot_entries = _shots_to_shotscript_entries(shots, ctx.chapter_id)

		shotscript = {
			"schema_version": "shotscript.v0.1",
			"meta": {
				"project_id": "novel2comic",
				"novel_id": ctx.novel_id,
				"chapter_id": ctx.chapter_id,
				"chapter_title": ctx.chapter_title or ctx.chapter_id,
				"language": "zh",
				"created_at": "",
				"llm": {
					"provider": llm_provider or ctx.llm_provider_name,
					"model": llm_model or ctx.llm_model,
				},
			},
			"render_profile": {
				"aspect_ratio": "16:9",
				"resolution": {"w": 1920, "h": 1080},
				"fps": 30,
				"timebase": "ms",
				"default_shot_duration_ms": 5000,
				"duration_policy": {
					"mode": "tts_driven",
					"min_shot_ms": 2500,
					"max_shot_ms": 12000,
					"hold_tail_ms": 200,
				},
			},
			"characters": [],
			"blocks": [],
			"shots": shot_entries,
			"assets_plan": {},
			"policy": {"content_rating": "teen"},
		}

		paths.shotscript.write_text(
			json.dumps(shotscript, ensure_ascii=False, indent=2),
			encoding="utf-8",
		)

		m = load_manifest(paths.manifest)
		m.durations["num_shots"] = len(shots)
		m.set_stage("segmented")
		m.mark_done("segment")
		save_manifest(paths.manifest, m)
