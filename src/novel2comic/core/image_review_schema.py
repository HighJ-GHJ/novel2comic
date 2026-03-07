# -*- coding: utf-8 -*-
"""
novel2comic/core/image_review_schema.py

VLM 评审输出 JSON 的解析与校验。
保证失败可重试、不会把脏数据写进 pipeline。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ReviewIssue:
	type: str
	severity: str  # low | mid | high
	detail: str


@dataclass
class SuggestedPatch:
	prompt_add: List[str] = field(default_factory=list)
	prompt_remove: List[str] = field(default_factory=list)
	negative_add: List[str] = field(default_factory=list)
	rebase: str = "none"  # prev_shot | char_anchor | style_anchor | none


@dataclass
class ReviewResult:
	"""VLM 评审结果，用于重试决策。"""
	pass_: bool
	scores: Dict[str, float]  # alignment, identity, style
	hard_fail: Dict[str, bool]
	issues: List[ReviewIssue]
	must_have: List[str]
	missing: List[str]
	suggested_patch: SuggestedPatch
	raw: Optional[Dict[str, Any]] = None

	@property
	def identity_fail(self) -> bool:
		return self.hard_fail.get("identity", False)

	@property
	def style_fail(self) -> bool:
		return self.hard_fail.get("style", False)

	@property
	def alignment_fail(self) -> bool:
		return self.hard_fail.get("alignment", False)


# 严格阈值（任务书 G1）
DEFAULT_ALIGNMENT_THRESHOLD = 0.85
DEFAULT_IDENTITY_THRESHOLD = 0.90
DEFAULT_STYLE_THRESHOLD = 0.85


def _parse_score(v: Any) -> float:
	if isinstance(v, (int, float)):
		return float(max(0, min(1, v)))
	return 0.0


def _parse_bool(v: Any) -> bool:
	if isinstance(v, bool):
		return v
	if isinstance(v, str):
		return v.strip().lower() in ("1", "true", "yes")
	return False


def _parse_list_str(v: Any) -> List[str]:
	if isinstance(v, list):
		return [str(x) for x in v if x is not None]
	return []


def _parse_suggested_patch(d: Any) -> SuggestedPatch:
	if not isinstance(d, dict):
		return SuggestedPatch()
	return SuggestedPatch(
		prompt_add=_parse_list_str(d.get("prompt_add")),
		prompt_remove=_parse_list_str(d.get("prompt_remove")),
		negative_add=_parse_list_str(d.get("negative_add")),
		rebase=str(d.get("rebase", "none")).strip().lower() or "none",
	)


def _parse_issues(issues: Any) -> List[ReviewIssue]:
	if not isinstance(issues, list):
		return []
	result = []
	for item in issues:
		if isinstance(item, dict):
			result.append(ReviewIssue(
				type=str(item.get("type", "")),
				severity=str(item.get("severity", "mid")),
				detail=str(item.get("detail", "")),
			))
	return result


def parse_review_json(
	json_str: str,
	*,
	alignment_threshold: float = DEFAULT_ALIGNMENT_THRESHOLD,
	identity_threshold: float = DEFAULT_IDENTITY_THRESHOLD,
	style_threshold: float = DEFAULT_STYLE_THRESHOLD,
	has_char_anchor: bool = False,
	has_style_anchor: bool = False,
	primary_char_id: str = "",
	require_char_anchor: bool = False,
	require_style_anchor: bool = False,
) -> ReviewResult:
	"""
	解析 VLM 输出的 JSON，返回 ReviewResult。
	若 JSON 无效或缺字段，返回 pass=False 的兜底结果（触发重试）。

	Policy（Strict 模式）：
	- require_char_anchor=True 且 primary_char_id 非空 且 无 char_anchor：
	  直接 hard_fail.identity=True，scores.identity=0.0，issues 加 missing_char_anchor
	- require_style_anchor 同理
	"""
	try:
		data = json.loads(json_str)
	except json.JSONDecodeError:
		return ReviewResult(
			pass_=False,
			scores={"alignment": 0, "identity": 0, "style": 0},
			hard_fail={"alignment": True, "identity": True, "style": True},
			issues=[ReviewIssue("parse_error", "high", "invalid JSON")],
			must_have=[],
			missing=[],
			suggested_patch=SuggestedPatch(),
			raw=None,
		)

	if not isinstance(data, dict):
		return ReviewResult(
			pass_=False,
			scores={"alignment": 0, "identity": 0, "style": 0},
			hard_fail={"alignment": True, "identity": True, "style": True},
			issues=[ReviewIssue("parse_error", "high", "root not dict")],
			must_have=[],
			missing=[],
			suggested_patch=SuggestedPatch(),
			raw=None,
		)

	# Policy：缺 anchor 时 strict 直接 fail
	missing_char = bool((primary_char_id or "").strip()) and require_char_anchor and not has_char_anchor
	missing_style = require_style_anchor and not has_style_anchor

	scores_raw = data.get("scores") or {}
	scores = {
		"alignment": _parse_score(scores_raw.get("alignment", 0)),
		"identity": 0.0 if missing_char else (_parse_score(scores_raw.get("identity", 1.0)) if has_char_anchor else 1.0),
		"style": 0.0 if missing_style else (_parse_score(scores_raw.get("style", 1.0)) if has_style_anchor else 1.0),
	}

	hard_raw = data.get("hard_fail") or {}
	hard_fail = {
		"alignment": _parse_bool(hard_raw.get("alignment", False)),
		"identity": missing_char or (_parse_bool(hard_raw.get("identity", False)) if has_char_anchor else False),
		"style": missing_style or (_parse_bool(hard_raw.get("style", False)) if has_style_anchor else False),
	}

	issues = _parse_issues(data.get("issues"))
	if missing_char:
		issues = [ReviewIssue("missing_char_anchor", "high", "有主角但未提供角色锚点，无法核验")] + issues
	if missing_style:
		issues = [ReviewIssue("missing_style_anchor", "high", "要求风格锚点但未提供")] + issues

	pass_val = _parse_bool(data.get("pass", False))
	# 若 hard_fail 任一为 true，必须 pass=False
	if any(hard_fail.values()):
		pass_val = False
	# 分数阈值
	if not hard_fail.get("alignment") and scores["alignment"] < alignment_threshold:
		pass_val = False
	if has_char_anchor and not hard_fail.get("identity") and scores["identity"] < identity_threshold:
		pass_val = False
	if has_style_anchor and not hard_fail.get("style") and scores["style"] < style_threshold:
		pass_val = False

	return ReviewResult(
		pass_=pass_val,
		scores=scores,
		hard_fail=hard_fail,
		issues=issues,
		must_have=_parse_list_str(data.get("must_have")),
		missing=_parse_list_str(data.get("missing")),
		suggested_patch=_parse_suggested_patch(data.get("suggested_patch")),
		raw=data,
	)
