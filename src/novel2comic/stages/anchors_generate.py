# -*- coding: utf-8 -*-
"""
novel2comic/stages/anchors_generate.py

Anchors Stage：生成角色锚点 + 风格锚点（16:9）。
- 统计 primary_char_id 频次，取 topK 生成 char anchor
- 可选生成 style_anchor
- 输出：images/anchors/characters/<char_id>/anchor.png, anchors_meta.json
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from novel2comic.core.config_loader import get_stage_config, get_siliconflow
from novel2comic.core.image_qc import parse_size, qc_image
from novel2comic.core.io import ChapterPaths, find_project_root
from novel2comic.core.manifest import load_manifest, save_manifest
from novel2comic.providers.image.image_qwen import (
	DEFAULT_CFG,
	DEFAULT_IMAGE_SIZE as QWEN_IMAGE_SIZE,
	DEFAULT_STEPS,
	generate_t2i as qwen_t2i,
	load_qwen_config,
)

ANCHOR_NEGATIVE = "水印,logo,低清,模糊,乱码文字,多余字幕,畸形手指,畸形脸,多人"
CHAR_ANCHOR_PROMPT_TEMPLATE = "动态漫画分镜风格，角色设定图，单人，{gender}，画面干净，16:9，半身，正面，清晰五官与发型，服装固定。{desc}"
STYLE_ANCHOR_PROMPT = "动态漫画分镜风格，统一画风，干净线条，16:9，场景氛围参考图，无水印，无多余文字。"


def _infer_char_from_text(text: str) -> str:
	"""简单启发式：从文本提取可能的人名（如 XXX说、XXX道、句首人名）。"""
	if not (text or "").strip():
		return ""
	# 常见模式：XXX说、XXX道、XXX问
	m = re.search(r"([\u4e00-\u9fff]{2,4})[说道问]", text)
	if m:
		return m.group(1)
	# 句首人名：XXX做了一个梦、XXX有
	m = re.search(r"^([\u4e00-\u9fff]{2,4})[做有是]", text)
	if m:
		return m.group(1)
	return ""


def _get_primary_char_id(shot: dict) -> str:
	"""从 shot 提取 primary_char_id。优先 image/speaker_char_id，否则从文本推断。"""
	cid = (shot.get("image") or {}).get("primary_char_id") or ""
	if not cid and (shot.get("speech") or {}).get("segments"):
		seg0 = (shot.get("speech", {}).get("segments") or [{}])[0] or {}
		cid = seg0.get("speaker_char_id", "") or ""
	if not cid:
		cid = _infer_char_from_text((shot.get("text") or {}).get("raw_text", ""))
	return (cid or "").strip()


def _topk_chars(shots: list, characters: list, topk: int) -> list[str]:
	"""
	统计 primary_char_id 频次，返回 topK。
	characters 若有 id，优先；否则从 shots 统计。
	"""
	counter: Counter[str] = Counter()
	for s in shots:
		cid = _get_primary_char_id(s)
		if cid:
			counter[cid] += 1
	# 若有 characters 定义，按 counter 排序后取 topK
	ordered = [c for c, _ in counter.most_common(topk)]
	return ordered[:topk]


def _char_description(characters: list, char_id: str) -> tuple[str, str]:
	"""
	从 shotscript.characters 取角色描述与性别。
	返回 (desc, gender)，gender 用于 prompt 避免模型误判。
	"""
	for c in characters or []:
		if (c.get("id") or c.get("char_id") or "") == char_id:
			desc = (c.get("description") or c.get("name") or char_id).strip()[:80]
			gender = (c.get("gender") or c.get("gender_hint") or "").strip()
			return desc, gender or None
	return char_id, None


def _stable_seed(chapter_id: str, char_id: str) -> int:
	"""可复现 seed。"""
	h = hash(f"{chapter_id}:{char_id}") % (2**31)
	return abs(h) if h != 0 else 12345


class AnchorsGenerateStage:
	name = "anchors"

	def run(self, paths: ChapterPaths, ctx: object) -> None:
		shotscript_path = paths.effective_shotscript()
		if not shotscript_path.exists():
			raise FileNotFoundError(f"missing {shotscript_path}")

		m = load_manifest(paths.manifest)
		if m.stage not in ("planned", "directed", "images_done", "tts_done", "aligned", "rendered"):
			raise ValueError(f"Anchors stage requires planned/directed, got {m.stage}")

		cfg = get_stage_config("anchors")
		if not cfg.get("enabled", True):
			print("[INFO] anchors stage disabled, skip")
			return

		data = json.loads(shotscript_path.read_text(encoding="utf-8"))
		shots = data.get("shots", [])
		characters = data.get("characters", [])
		chapter_id = data.get("meta", {}).get("chapter_id", "ch_0001")
		topk = int(cfg.get("topk_chars") or 8)
		default_gender = (cfg.get("default_gender") or "男性").strip()
		image_size = cfg.get("image_size") or get_siliconflow().get("image", {}).get("image_size") or QWEN_IMAGE_SIZE
		steps = int(cfg.get("steps") or DEFAULT_STEPS)
		cfg_val = float(cfg.get("cfg") or DEFAULT_CFG)

		char_ids = _topk_chars(shots, characters, topk)
		if not char_ids:
			print("[INFO] no primary_char_id in shots, skip anchors")
			return

		paths.images_anchors_dir.mkdir(parents=True, exist_ok=True)
		chars_dir = paths.images_anchors_dir / "characters"
		chars_dir.mkdir(parents=True, exist_ok=True)

		api_cfg = load_qwen_config(project_root=str(find_project_root()))
		expected_w, expected_h = parse_size(image_size)
		anchors_meta = {"characters": {}, "style_anchor": None}

		for char_id in char_ids:
			char_dir = chars_dir / char_id
			char_dir.mkdir(parents=True, exist_ok=True)
			anchor_path = char_dir / "anchor.png"
			if anchor_path.exists():
				ok, _ = qc_image(anchor_path, expected_w, expected_h)
				if ok:
					anchors_meta["characters"][char_id] = {"path": f"images/anchors/characters/{char_id}/anchor.png", "status": "cached"}
					continue

			desc, gender_hint = _char_description(characters, char_id)
			gender = (gender_hint or default_gender).strip() or "男性"
			prompt = CHAR_ANCHOR_PROMPT_TEMPLATE.format(gender=gender, desc=desc)
			seed = _stable_seed(chapter_id, char_id)
			try:
				img, meta = qwen_t2i(
					prompt,
					negative_prompt=ANCHOR_NEGATIVE,
					image_size=image_size,
					steps=steps,
					cfg=cfg_val,
					seed=seed,
					config=api_cfg,
				)
				img.save(anchor_path, "PNG")
				ok, reason = qc_image(anchor_path, expected_w, expected_h)
				anchors_meta["characters"][char_id] = {
					"path": f"images/anchors/characters/{char_id}/anchor.png",
					"seed": seed,
					"prompt": prompt,
					"status": "ok" if ok else f"qc_fail:{reason}",
				}
				print(f"[OK] {char_id} anchor seed={seed}")
			except Exception as e:
				anchors_meta["characters"][char_id] = {"status": "failed", "error": str(e)[:200]}
				print(f"[WARN] {char_id} anchor failed: {e}")

		meta_path = paths.images_anchors_dir / "anchors_meta.json"
		meta_path.write_text(json.dumps(anchors_meta, ensure_ascii=False, indent=2), encoding="utf-8")

		m = load_manifest(paths.manifest)
		m.durations["anchors_chars"] = len(anchors_meta["characters"])
		m.artifacts["anchors_meta"] = "images/anchors/anchors_meta.json"
		save_manifest(paths.manifest, m)
		print(f"[OK] anchors stage done: {len(anchors_meta['characters'])} chars")
