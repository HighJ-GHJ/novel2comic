# -*- coding: utf-8 -*-
"""
novel2comic/pipeline/orchestrator.py

目的：
- 作为“阶段调度器”：按固定顺序执行各个 stage。
- 支持 `run_until(..., until="segment")`：跑到指定阶段停止。
- 这是“低耦合”的关键：CLI 不直接调用 stage，统一走 orchestrator。

当前状态：
- 仅实现 ingest/segment 两个 stage 的接入。
- plan/tts/... 等阶段未实现时，遇到会停止并提示。

注意：
- orchestrator 不关心任何具体业务（如何切分、如何调用模型）。
- orchestrator 只负责：创建 paths、按顺序调用 stage、打印状态。
"""

from __future__ import annotations

from novel2comic.core.io import chapter_paths
from novel2comic.core.manifest import load_manifest
from novel2comic.stages.ingest import IngestStage
from novel2comic.stages.segment import SegmentStage
from novel2comic.stages.plan import PlanStage
from novel2comic.stages.director_review import DirectorReviewStage
from novel2comic.stages.tts import TTSStage
from novel2comic.stages.align import AlignStage
from novel2comic.stages.render import RenderStage
from novel2comic.stages.anchors_generate import AnchorsGenerateStage
from novel2comic.stages.image_generate import ImageGenerateStage
from novel2comic.stages.base import StageContext


STAGE_ORDER = [
	"ingest",
	"segment",
	"plan",
	"director_review",
	"anchors",
	"image",
	"tts",
	"align",
	"render",
	"export",
]


def run_until(chapter_dir: str, ctx: StageContext, until: str, from_stage: str | None = None) -> None:
	paths = chapter_paths(chapter_dir)
	paths.ensure_dirs()

	stages = {
		"ingest": IngestStage(),
		"segment": SegmentStage(),
		"plan": PlanStage(),
		"director_review": DirectorReviewStage(),
		"anchors": AnchorsGenerateStage(),
		"image": ImageGenerateStage(),
		"tts": TTSStage(),
		"align": AlignStage(),
		"render": RenderStage(),
	}

	skip_until = from_stage
	for name in STAGE_ORDER:
		if skip_until and name != skip_until:
			continue
		if skip_until and name == skip_until:
			skip_until = None
		if name == "export" and until == name:
			print(f"[INFO] {name} stage not implemented yet; stop here.")
			break

		stage = stages.get(name)
		if stage is not None:
			print(f"[RUN] stage={name}", flush=True)
			stage.run(paths, ctx)

		if name == until:
			break

	# 打印当前 stage，便于确认断点续跑的“锚点”。
	if paths.manifest.exists():
		m = load_manifest(paths.manifest)
		print(f"[OK] current stage = {m.stage}", flush=True)
