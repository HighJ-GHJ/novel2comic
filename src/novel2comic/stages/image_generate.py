# -*- coding: utf-8 -*-
"""
novel2comic/stages/image_generate.py

Image Stage：为每个 shot 生成 16:9 全幅静帧。
- Draft：Qwen/Qwen-Image 文生图（1664x928, steps=50, cfg=4）
- Refine：同场景连续镜头用 Qwen/Qwen-Image-Edit，ref=prev_shot
- 断链回退：连续失败 >=2 次或 attempt3 强制回退 T2I
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path

from novel2comic.core.config_loader import get_siliconflow, get_stage_config
from novel2comic.core.image_prompt import (
	CAMERA_ZH,
	QWEN_NEGATIVE,
	apply_prompt_patch,
	build_prompt_qwen_draft,
	build_prompt_qwen_refine,
	extract_must_have,
)
from novel2comic.core.image_qc import parse_size, qc_image
from novel2comic.core.io import ChapterPaths, find_project_root
from novel2comic.core.manifest import load_manifest, save_manifest
from novel2comic.providers.image.image_qwen import (
	DEFAULT_CFG,
	DEFAULT_IMAGE_SIZE as QWEN_IMAGE_SIZE,
	DEFAULT_STEPS,
	edit as qwen_edit,
	generate_t2i as qwen_t2i,
	load_qwen_config,
)

ERR_MSG_META_LEN = 300
ERR_MSG_MANIFEST_LEN = 200


def _image_config() -> dict:
	cfg = get_stage_config("image")
	sf = get_siliconflow().get("image", {})
	review = cfg.get("review") or {}
	return {
		"image_size": cfg.get("image_size") or sf.get("image_size") or QWEN_IMAGE_SIZE,
		"steps": cfg.get("steps") or sf.get("steps") or DEFAULT_STEPS,
		"cfg": cfg.get("cfg") or sf.get("cfg") or DEFAULT_CFG,
		"max_attempts": cfg.get("max_attempts") or 3,
		"mode": (cfg.get("mode") or "draft").strip().lower(),
		"chain_max_hops": cfg.get("chain_max_hops") or 8,
		"use_vlm_review": bool(cfg.get("use_vlm_review", False)),
		"review_max_attempts": int(cfg.get("review_max_attempts") or 8),
		"require_char_anchor": bool(review.get("require_char_anchor", False)),
		"require_style_anchor": bool(review.get("require_style_anchor", False)),
		"enable_recheck": bool(review.get("enable_recheck", False)),
	}


def _camera_from_shot(shot: dict) -> str:
	cam = (shot.get("image", {}) or {}).get("camera") or "medium shot"
	return CAMERA_ZH.get(cam.lower(), "中景")


def _prompt_hash(prompt: str) -> str:
	return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


def _infer_char_from_text(text: str) -> str:
	"""简单启发式：从文本提取可能的人名。"""
	import re
	if not (text or "").strip():
		return ""
	m = re.search(r"([\u4e00-\u9fff]{2,4})[说道问]", text)
	if m:
		return m.group(1)
	m = re.search(r"^([\u4e00-\u9fff]{2,4})[做有是]", text)
	if m:
		return m.group(1)
	return ""


def _get_primary_char_id(shot: dict) -> str:
	"""从 shot 提取 primary_char_id。"""
	cid = (shot.get("image") or {}).get("primary_char_id") or ""
	if not cid and (shot.get("speech") or {}).get("segments"):
		seg0 = (shot.get("speech", {}).get("segments") or [{}])[0] or {}
		cid = seg0.get("speaker_char_id", "") or ""
	if not cid:
		cid = _infer_char_from_text((shot.get("text") or {}).get("raw_text", ""))
	return (cid or "").strip()


def _build_shot_brief(shot: dict, scene_id: str = "") -> dict:
	"""构建 VLM 评审用的 shot_brief。"""
	text = (shot.get("text", {}).get("subtitle_text") or shot.get("text", {}).get("raw_text") or "").strip()
	primary_char_id = _get_primary_char_id(shot)
	return {
		"shot_id": shot.get("shot_id", ""),
		"scene_id": scene_id,
		"primary_char_id": primary_char_id or "",
		"shot_description_cn": text[:200] if text else "（无描述）",
		"must_have_list_cn": extract_must_have(shot, 8),
	}


def _generate_one_shot(
	shot: dict,
	paths: ChapterPaths,
	prev_shot_png_path: Path | None,
	prev_shot_meta: dict | None,
	chain_hops: int,
	consecutive_edit_fails: int,
	img_cfg: dict,
	api_cfg,
	char_anchor_bytes: bytes | None = None,
	style_anchor_bytes: bytes | None = None,
) -> tuple[bool, str | None, str, dict]:
	"""
	为单个 shot 生成图片。
	返回 (success, error_msg, ref_used, meta_record)。
	ref_used: none | prev_shot | char_anchor | style_anchor
	"""
	shot_id = shot.get("shot_id", "")
	if not shot_id:
		return False, "no shot_id", "none", {}

	png_path = paths.images_shots_dir / f"shot_{shot_id}.png"
	meta_path = paths.images_shots_dir / f"shot_{shot_id}.meta.json"
	image_size = img_cfg["image_size"]
	expected_w, expected_h = parse_size(image_size)
	seed = random.randint(0, 999_999_999)
	use_vlm = bool(img_cfg.get("use_vlm_review", False))
	max_attempts = int(img_cfg.get("review_max_attempts", 8)) if use_vlm else int(img_cfg.get("max_attempts", 3))
	require_char = bool(img_cfg.get("require_char_anchor", False))
	require_style = bool(img_cfg.get("require_style_anchor", False))
	enable_recheck = bool(img_cfg.get("enable_recheck", False))

	primary_char_id = _get_primary_char_id(shot)
	has_char_anchor = char_anchor_bytes is not None and len(char_anchor_bytes) > 0
	has_style_anchor = style_anchor_bytes is not None and len(style_anchor_bytes) > 0

	# 链式条件：同场景、prev 存在且 QC ok、未超 chain_hops、未连续失败 2 次
	chain_allowed = (
		img_cfg["mode"] == "refine"
		and prev_shot_png_path
		and prev_shot_png_path.exists()
		and prev_shot_meta
		and prev_shot_meta.get("qc_pass") is True
		and chain_hops < img_cfg["chain_max_hops"]
		and consecutive_edit_fails < 2
	)

	attempts_log = []
	vlm_client = None
	force_ref = None
	last_suggested_patch = None

	if use_vlm:
		try:
			from novel2comic.providers.vlm.siliconflow_vlm import load_vlm_config, SiliconFlowVLMClient
			vlm_cfg = load_vlm_config(project_root=str(find_project_root()))
			vlm_client = SiliconFlowVLMClient(vlm_cfg)
		except Exception as e:
			return False, f"vlm_init_fail:{str(e)[:100]}", "none", {"attempts": [], "error": str(e)}

	for attempt in range(max_attempts):
		if attempt >= 1:
			seed = random.randint(0, 999_999_999)

		# Ref 选择：force_ref > char_anchor preferred > chain > t2i
		force_t2i = attempt >= 2 and (force_ref or chain_allowed)
		do_edit = not force_t2i
		ref_used = "none"

		if do_edit:
			if force_ref == "char_anchor" and has_char_anchor:
				ref_used = "char_anchor"
			elif force_ref == "style_anchor" and has_style_anchor:
				ref_used = "style_anchor"
			elif force_ref == "prev_shot" and chain_allowed and prev_shot_png_path and prev_shot_png_path.exists():
				ref_used = "prev_shot"
			elif primary_char_id and has_char_anchor:
				ref_used = "char_anchor"
			elif chain_allowed and prev_shot_png_path and prev_shot_png_path.exists():
				ref_used = "prev_shot"
			else:
				ref_used = "none"
				do_edit = False

		# 构建 prompt，应用 patch
		if ref_used == "prev_shot":
			prev_text = (prev_shot_meta or {}).get("prompt", "")
			prompt = build_prompt_qwen_refine(shot, prev_text)
		else:
			prompt = build_prompt_qwen_draft(shot, _camera_from_shot(shot))
		negative = QWEN_NEGATIVE
		if last_suggested_patch:
			from novel2comic.core.image_review_schema import SuggestedPatch
			sp = SuggestedPatch(
				prompt_add=last_suggested_patch.get("prompt_add", []),
				prompt_remove=last_suggested_patch.get("prompt_remove", []),
				negative_add=last_suggested_patch.get("negative_add", []),
				rebase=last_suggested_patch.get("rebase", "none"),
			)
			prompt, negative = apply_prompt_patch(prompt, negative, sp)

		try:
			if do_edit and ref_used == "prev_shot":
				ref_bytes = prev_shot_png_path.read_bytes()
				img, meta = qwen_edit(
					ref_bytes,
					prompt,
					negative_prompt=negative,
					steps=img_cfg["steps"],
					cfg=img_cfg["cfg"],
					seed=seed,
					config=api_cfg,
				)
			elif do_edit and ref_used == "char_anchor" and char_anchor_bytes:
				img, meta = qwen_edit(
					char_anchor_bytes,
					prompt,
					negative_prompt=negative,
					steps=img_cfg["steps"],
					cfg=img_cfg["cfg"],
					seed=seed,
					config=api_cfg,
				)
			elif do_edit and ref_used == "style_anchor" and style_anchor_bytes:
				img, meta = qwen_edit(
					style_anchor_bytes,
					prompt,
					negative_prompt=negative,
					steps=img_cfg["steps"],
					cfg=img_cfg["cfg"],
					seed=seed,
					config=api_cfg,
				)
			else:
				img, meta = qwen_t2i(
					prompt,
					negative_prompt=negative,
					image_size=image_size,
					steps=img_cfg["steps"],
					cfg=img_cfg["cfg"],
					seed=seed,
					config=api_cfg,
				)
				ref_used = "none"

		except Exception as e:
			err = str(e)[:ERR_MSG_META_LEN]
			attempt_rec = {
				"attempt_idx": attempt + 1,
				"seed": seed,
				"ref_used": ref_used,
				"gen_mode": "edit" if do_edit else "t2i",
				"prompt": prompt,
				"provider": "qwen_edit" if do_edit else "qwen",
				"elapsed_ms": 0,
				"qc_pass": False,
				"error": err,
			}
			attempts_log.append(attempt_rec)
			if attempt < max_attempts - 1:
				time.sleep(2 ** attempt)
				continue
			meta_record = {"attempts": attempts_log, "attempt_idx": attempt + 1, "ref_used": ref_used, **attempt_rec}
			meta_path.write_text(json.dumps(meta_record, ensure_ascii=False, indent=2), encoding="utf-8")
			if vlm_client:
				vlm_client.close()
			return False, err, ref_used, meta_record

		img.save(png_path, "PNG")
		ok, reason = qc_image(png_path, expected_w, expected_h)
		attempt_rec = {
			"attempt_idx": attempt + 1,
			"seed": meta.get("seed", seed),
			"ref_used": ref_used,
			"gen_mode": "edit" if do_edit else "t2i",
			"prompt": prompt,
			"prompt_hash": _prompt_hash(prompt),
			"negative_prompt": negative,
			"provider": "qwen_edit" if do_edit else "qwen",
			"elapsed_ms": meta.get("elapsed_ms"),
			"qc_pass": ok,
			"qc_reason": reason,
		}

		if not ok:
			attempts_log.append(attempt_rec)
			if attempt < max_attempts - 1:
				time.sleep(0.5)
				continue
			meta_record = {"attempts": attempts_log, **attempt_rec}
			meta_path.write_text(json.dumps(meta_record, ensure_ascii=False, indent=2), encoding="utf-8")
			if vlm_client:
				vlm_client.close()
			return False, f"qc_fail:{reason}", ref_used, meta_record

		# VLM 评审
		if use_vlm and vlm_client:
			try:
				shot_brief = _build_shot_brief(shot)
				review = vlm_client.review_shot_image(
					png_path.read_bytes(),
					shot_brief,
					char_anchor_bytes=char_anchor_bytes,
					style_anchor_bytes=style_anchor_bytes,
					require_char_anchor=require_char,
					require_style_anchor=require_style,
				)
				attempt_rec["review"] = {
					"round": 1,
					"pass": review.pass_,
					"scores": review.scores,
					"hard_fail": review.hard_fail,
					"issues": [{"type": i.type, "severity": i.severity, "detail": i.detail} for i in review.issues],
				}
				attempts_log.append(attempt_rec)
				last_suggested_patch = None
				if review.suggested_patch:
					last_suggested_patch = {
						"prompt_add": review.suggested_patch.prompt_add,
						"prompt_remove": review.suggested_patch.prompt_remove,
						"negative_add": review.suggested_patch.negative_add,
						"rebase": review.suggested_patch.rebase,
					}

				if not review.pass_:
					# Round2 Recheck
					if enable_recheck and (review.identity_fail or review.style_fail or review.alignment_fail):
						recheck_dims = [d for d in ["identity", "style", "alignment"] if review.hard_fail.get(d)]
						round1_issues = [i.detail for i in review.issues]
						try:
							recheck = vlm_client.review_shot_image_recheck(
								png_path.read_bytes(),
								shot_brief,
								recheck_dims=recheck_dims,
								round1_issues=round1_issues,
								char_anchor_bytes=char_anchor_bytes if "identity" in recheck_dims else None,
								style_anchor_bytes=style_anchor_bytes if "style" in recheck_dims else None,
							)
							attempt_rec["review_round2"] = {
								"pass": recheck.pass_,
								"scores": recheck.scores,
								"hard_fail": recheck.hard_fail,
							}
							if recheck.pass_:
								if vlm_client:
									vlm_client.close()
								meta_record = {"attempts": attempts_log, **attempt_rec}
								meta_path.write_text(json.dumps(meta_record, ensure_ascii=False, indent=2), encoding="utf-8")
								return True, None, ref_used, meta_record
						except Exception as e:
							attempt_rec["review_round2"] = {"pass": False, "error": str(e)[:200]}

					# 断链 rebase
					if review.identity_fail and has_char_anchor:
						force_ref = "char_anchor"
					elif review.style_fail and has_style_anchor:
						force_ref = "style_anchor"
					elif review.suggested_patch and review.suggested_patch.rebase in ("char_anchor", "style_anchor", "prev_shot"):
						force_ref = review.suggested_patch.rebase

					issues_str = "; ".join(i.detail for i in review.issues[:3])
					if attempt < max_attempts - 1:
						time.sleep(1)
						continue
					meta_record = {"attempts": attempts_log, **attempt_rec}
					meta_path.write_text(json.dumps(meta_record, ensure_ascii=False, indent=2), encoding="utf-8")
					vlm_client.close()
					return False, f"vlm_fail:{issues_str[:150]}", ref_used, meta_record
			except Exception as e:
				attempt_rec["review"] = {"round": 1, "pass": False, "error": str(e)[:200]}
				attempts_log.append(attempt_rec)
				if attempt < max_attempts - 1:
					time.sleep(1)
					continue
				meta_record = {"attempts": attempts_log, **attempt_rec}
				meta_path.write_text(json.dumps(meta_record, ensure_ascii=False, indent=2), encoding="utf-8")
				vlm_client.close()
				return False, f"vlm_error:{str(e)[:100]}", ref_used, meta_record

		if vlm_client:
			vlm_client.close()
		meta_record = {"attempts": attempts_log or [attempt_rec], **attempt_rec}
		meta_path.write_text(json.dumps(meta_record, ensure_ascii=False, indent=2), encoding="utf-8")
		return True, None, ref_used, meta_record

	if vlm_client:
		vlm_client.close()
	return False, "max_attempts_exceeded", "none", {"attempts": attempts_log}


class ImageGenerateStage:
	name = "image"

	def run(self, paths: ChapterPaths, ctx: object) -> None:
		shotscript_path = paths.effective_shotscript()
		if not shotscript_path.exists():
			raise FileNotFoundError(f"missing {shotscript_path}")

		data = json.loads(shotscript_path.read_text(encoding="utf-8"))
		shots = data.get("shots", [])
		if not shots:
			raise ValueError("shotscript has no shots")

		m = load_manifest(paths.manifest)
		if m.stage not in ("directed", "images_done", "tts_done", "aligned", "rendered"):
			raise ValueError(f"Image stage requires directed, got {m.stage}")

		if m.stage == "images_done":
			print("[INFO] images_done already, skip image stage")
			return

		paths.images_shots_dir.mkdir(parents=True, exist_ok=True)
		img_cfg = _image_config()
		api_cfg = load_qwen_config(project_root=str(find_project_root()))

		total_ms = 0
		ok_count = 0
		fail_count = 0
		prev_shot_png_path = None
		prev_shot_meta = None
		chain_hops = 0
		consecutive_edit_fails = 0

		for shot in shots:
			shot_id = shot.get("shot_id", "")
			png_path = paths.images_shots_dir / f"shot_{shot_id}.png"
			meta_path = paths.images_shots_dir / f"shot_{shot_id}.meta.json"
			expected_w, expected_h = parse_size(img_cfg["image_size"])

			# 断点续跑
			if png_path.exists() and meta_path.exists():
				ok, reason = qc_image(png_path, expected_w, expected_h)
				if ok:
					meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
					m.images_index[shot_id] = {
						"path": paths.shot_image_rel_path(shot_id),
						"provider": meta_data.get("provider", "qwen"),
						"seed": meta_data.get("seed"),
						"ref_used": meta_data.get("ref_used", "none"),
						"prompt_hash": meta_data.get("prompt_hash"),
						"attempts": meta_data.get("attempt_idx", 1),
						"status": "ok",
					}
					prev_shot_png_path = png_path
					prev_shot_meta = meta_data
					chain_hops = chain_hops + 1 if meta_data.get("ref_used") == "prev_shot" else 0
					consecutive_edit_fails = 0
					ok_count += 1
					continue

			# 加载 anchor（有 primary_char_id 时用 char_anchor）
			char_anchor_bytes = None
			style_anchor_bytes = None
			primary_char_id = _get_primary_char_id(shot)
			if primary_char_id:
				anchor_path = paths.char_anchor_path(primary_char_id)
				if anchor_path.exists():
					char_anchor_bytes = anchor_path.read_bytes()
			style_path = paths.style_anchor_path()
			if style_path.exists():
				style_anchor_bytes = style_path.read_bytes()

			# 生成
			success, err, ref_used, meta_record = _generate_one_shot(
				shot,
				paths,
				prev_shot_png_path,
				prev_shot_meta,
				chain_hops,
				consecutive_edit_fails,
				img_cfg,
				api_cfg,
				char_anchor_bytes=char_anchor_bytes,
				style_anchor_bytes=style_anchor_bytes,
			)

			if success:
				prev_shot_png_path = png_path
				prev_shot_meta = meta_record
				chain_hops = chain_hops + 1 if ref_used == "prev_shot" else 0
				consecutive_edit_fails = 0
				total_ms += meta_record.get("elapsed_ms", 0) or 0
				ok_count += 1
				m.images_index[shot_id] = {
					"path": paths.shot_image_rel_path(shot_id),
					"provider": meta_record.get("provider", "qwen"),
					"seed": meta_record.get("seed"),
					"ref_used": ref_used,
					"prompt_hash": meta_record.get("prompt_hash"),
					"attempts": meta_record.get("attempt_idx", 1),
					"status": "ok",
				}
				print(f"[OK] {shot_id} ref={ref_used} seed={meta_record.get('seed')} qc=ok")
			else:
				if ref_used == "prev_shot":
					consecutive_edit_fails += 1
				chain_hops = 0
				m.images_index[shot_id] = {
					"path": "",
					"provider": "qwen",
					"seed": None,
					"ref_used": ref_used,
					"prompt_hash": None,
					"attempts": img_cfg["max_attempts"],
					"status": "failed",
					"error": (err or "unknown")[:ERR_MSG_MANIFEST_LEN],
				}
				m.add_warning(f"image shot {shot_id} failed: {err}")
				fail_count += 1
				print(f"[WARN] {shot_id} failed: {err}")

			if (ok_count + fail_count) % 5 == 0:
				save_manifest(paths.manifest, m)

		m.set_stage("images_done")
		m.mark_done("image")
		m.durations["image_ms"] = total_ms
		m.artifacts["shots_images_dir"] = "images/shots/"
		save_manifest(paths.manifest, m)
		print(f"[OK] image stage done: {ok_count} ok, {fail_count} failed")
