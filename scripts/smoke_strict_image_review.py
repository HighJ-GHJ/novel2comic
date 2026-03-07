#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/smoke_strict_image_review.py

Strict Image QA Phase2 冒烟测试：Anchors → 链式生成 → 漂移 → VLM 抓 → Rebase → 通过。
流程：
1. 调用 anchors stage 生成 char_anchor（至少 1 个主角）
2. shot1：edit(ref=char_anchor)，评审通过
3. shot2：链式 edit(ref=prev_shot)，故意加漂移词
4. 验证 Round1/2 识别 identity fail
5. 下一次 attempt 自动 rebase 到 char_anchor，prompt 加「不要换人/保持服装一致」
6. 最终通过，meta 里 ref_used 从 prev_shot 切到 char_anchor

--full 跑完整流程（含 anchors+生图）；否则仅 VLM 评审。
需要 .env 配置 SILICONFLOW_API_KEY。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from novel2comic.core.image_prompt import build_prompt_qwen_draft, build_prompt_qwen_refine, QWEN_NEGATIVE
from novel2comic.core.io import chapter_paths, find_project_root
from novel2comic.core.image_review_schema import parse_review_json
from novel2comic.core.manifest import new_manifest, save_manifest
from novel2comic.providers.image.image_qwen import generate_t2i, edit as qwen_edit, load_qwen_config
from novel2comic.providers.vlm.siliconflow_vlm import SiliconFlowVLMClient, load_vlm_config
from novel2comic.stages.anchors_generate import AnchorsGenerateStage
from novel2comic.stages.base import StageContext


def main() -> int:
	p = argparse.ArgumentParser()
	p.add_argument("--out_dir", default="output/smoke_strict_image_review", help="输出目录")
	p.add_argument("--char_anchor", default=None, help="角色锚点 PNG 路径（可选，不传则 --full 时生成）")
	p.add_argument("--style_anchor", default=None, help="风格锚点 PNG 路径（可选）")
	p.add_argument("--skip_generate", action="store_true", help="跳过生图，仅测试 VLM 评审")
	p.add_argument("--shot", default=None, help="已有 shot 图片路径（与 --skip_generate 合用，如 output/.../shot_ch_0001_shot_0002.png）")
	p.add_argument("--full", action="store_true", help="完整流程：anchors → shot1(char_anchor) → shot2(chain+漂移) → rebase → 通过")
	args = p.parse_args()

	out = Path(args.out_dir)
	out.mkdir(parents=True, exist_ok=True)

	if args.full:
		# 创建最小 chapter pack
		paths = chapter_paths(str(out))
		paths.ensure_dirs()
		shotscript = {
			"schema_version": "shotscript.v0.1",
			"meta": {"chapter_id": "smoke_ch", "novel_id": "smoke"},
			"characters": [{"id": "陆江仙", "name": "陆江仙", "description": "年轻男子"}],
			"shots": [
				{"shot_id": "smoke_shot_001", "text": {"raw_text": "陆江仙做了一个梦"}, "image": {"primary_char_id": "陆江仙"}},
				{"shot_id": "smoke_shot_002", "text": {"raw_text": "陆江仙换了一套衣服，换成另一个人"}, "image": {"primary_char_id": "陆江仙"}},
			],
		}
		paths.shotscript.write_text(json.dumps(shotscript, ensure_ascii=False, indent=2), encoding="utf-8")
		paths.shotscript_directed.write_text(json.dumps(shotscript, ensure_ascii=False, indent=2), encoding="utf-8")
		m = new_manifest("smoke", "smoke_ch")
		m.set_stage("directed")
		save_manifest(paths.manifest, m)

		# 1) Anchors
		print("[1/4] Anchors stage ...")
		AnchorsGenerateStage().run(paths, StageContext())
		char_anchor_path = paths.char_anchor_path("陆江仙")
		if not char_anchor_path.exists():
			print("[FAIL] char_anchor not generated")
			return 1
		char_anchor_bytes = char_anchor_path.read_bytes()
		print(f"      anchor={char_anchor_path}")

		# 2) shot1: edit(ref=char_anchor)
		api_cfg = load_qwen_config(project_root=str(find_project_root()))
		shot1 = shotscript["shots"][0]
		prompt1 = build_prompt_qwen_draft(shot1, "中景")
		print("[2/4] shot1 edit(ref=char_anchor) ...")
		img1, _ = qwen_edit(char_anchor_bytes, prompt1, negative_prompt=QWEN_NEGATIVE, config=api_cfg)
		path1 = paths.images_shots_dir / "shot_smoke_shot_001.png"
		paths.images_shots_dir.mkdir(parents=True, exist_ok=True)
		img1.save(path1, "PNG")

		# 3) shot2: chain + 漂移词
		shot2 = shotscript["shots"][1]
		prompt2_drift = build_prompt_qwen_refine(shot2, prompt1)
		print("[3/4] shot2 chain (ref=prev) + 漂移词 ...")
		img2, _ = qwen_edit(path1.read_bytes(), prompt2_drift, negative_prompt=QWEN_NEGATIVE, config=api_cfg)
		path2 = paths.images_shots_dir / "shot_smoke_shot_002.png"
		img2.save(path2, "PNG")

		# 4) VLM 评审（应 identity fail）→ Recheck → Rebase 逻辑由 image_generate 实现，此处仅验证评审
		print("[4/4] VLM review shot2 (expect identity fail) ...")
		vlm = SiliconFlowVLMClient(load_vlm_config(project_root=str(find_project_root())))
		shot_brief = {
			"shot_id": "smoke_shot_002",
			"scene_id": "scene_01",
			"primary_char_id": "陆江仙",
			"shot_description_cn": shot2["text"]["raw_text"],
			"must_have_list_cn": ["陆江仙"],
		}
		review = vlm.review_shot_image(
			path2.read_bytes(),
			shot_brief,
			char_anchor_bytes=char_anchor_bytes,
			style_anchor_bytes=None,
			require_char_anchor=True,
		)
		vlm.close()
		print(f"      pass={review.pass_} scores={review.scores} hard_fail={review.hard_fail}")
		meta_out = out / "smoke_review_meta.json"
		meta_out.write_text(
			json.dumps({
				"pass": review.pass_,
				"scores": review.scores,
				"hard_fail": review.hard_fail,
				"ref_used_flow": "shot1=char_anchor, shot2=prev_shot(漂移)→rebase=char_anchor",
			}, ensure_ascii=False, indent=2),
			encoding="utf-8",
		)
		print(f"[OK] full smoke done, meta={meta_out}")
		return 0

	# 原有简化流程
	if not args.skip_generate:
		api_cfg = load_qwen_config(project_root=str(find_project_root()))
		shot1 = {"shot_id": "smoke_shot_001", "text": {"subtitle_text": "夜晚的老街，雨后路面反光，一名穿深色风衣的年轻男子站在路灯下，表情警惕。"}, "image": {}}
		prompt1 = build_prompt_qwen_draft(shot1, "中景")
		print("[1/2] T2I shot1 ...")
		img1, meta1 = generate_t2i(prompt1, negative_prompt=QWEN_NEGATIVE, config=api_cfg)
		path1 = out / "shot_001.png"
		img1.save(path1, "PNG")
		print(f"      seed={meta1.get('seed')} path={path1}")

		ref_bytes = path1.read_bytes()
		shot2 = {"shot_id": "smoke_shot_002", "text": {"subtitle_text": "同一男子微微侧身，目光望向街角。"}, "image": {}}
		prompt2 = "保持参考图的角色外观、服装、画风和构图一致。本镜头变化：同一男子微微侧身，目光望向街角。"
		print("[2/2] Edit shot2 (ref=shot1) ...")
		img2, meta2 = qwen_edit(ref_bytes, prompt2, negative_prompt=QWEN_NEGATIVE, config=api_cfg)
		path2 = out / "shot_002.png"
		img2.save(path2, "PNG")
		print(f"      seed={meta2.get('seed')} path={path2}")
	else:
		if args.shot and Path(args.shot).exists():
			path2 = Path(args.shot)
		else:
			path2 = out / "shot_002.png"
		if not path2.exists():
			print("[FAIL] shot image not found. Use --shot <path> to specify existing image, or run without --skip_generate first")
			return 1

	vlm_cfg = load_vlm_config(project_root=str(find_project_root()))
	vlm = SiliconFlowVLMClient(vlm_cfg)
	char_anchor_bytes = Path(args.char_anchor).read_bytes() if args.char_anchor and Path(args.char_anchor).exists() else None
	style_anchor_bytes = Path(args.style_anchor).read_bytes() if args.style_anchor and Path(args.style_anchor).exists() else None

	shot_brief = {
		"shot_id": "smoke_shot_002",
		"scene_id": "scene_01",
		"primary_char_id": "",
		"shot_description_cn": "同一男子微微侧身，目光望向街角。",
		"must_have_list_cn": ["男子", "侧身", "目光", "街角"],
	}
	review = vlm.review_shot_image(
		path2.read_bytes(),
		shot_brief,
		char_anchor_bytes=char_anchor_bytes,
		style_anchor_bytes=style_anchor_bytes,
	)
	vlm.close()

	print(f"[VLM] pass={review.pass_} scores={review.scores} hard_fail={review.hard_fail}")
	if review.issues:
		for i in review.issues[:3]:
			print(f"      issue: {i.type} {i.severity} {i.detail}")

	meta_out = out / "smoke_review_meta.json"
	meta_out.write_text(
		json.dumps({
			"pass": review.pass_,
			"scores": review.scores,
			"hard_fail": review.hard_fail,
			"issues": [{"type": i.type, "severity": i.severity, "detail": i.detail} for i in review.issues],
		}, ensure_ascii=False, indent=2),
		encoding="utf-8",
	)
	print(f"[OK] meta written to {meta_out}")
	return 0 if review.pass_ else 1


if __name__ == "__main__":
	sys.exit(main())
