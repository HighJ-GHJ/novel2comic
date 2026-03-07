# -*- coding: utf-8 -*-
"""
tests/test_image_review_schema.py

VLM 评审 JSON schema 解析与阈值判定单元测试。
"""

from __future__ import annotations

import pytest

from novel2comic.core.image_review_schema import (
	DEFAULT_ALIGNMENT_THRESHOLD,
	DEFAULT_IDENTITY_THRESHOLD,
	DEFAULT_STYLE_THRESHOLD,
	parse_review_json,
)


class TestParseReviewJson:
	def test_valid_pass(self):
		j = '{"pass": true, "scores": {"alignment": 0.9, "identity": 0.95, "style": 0.9}, "hard_fail": {"alignment": false, "identity": false, "style": false}, "issues": [], "must_have": ["路灯"], "missing": [], "suggested_patch": {"prompt_add": [], "prompt_remove": [], "negative_add": [], "rebase": "none"}}'
		r = parse_review_json(j, has_char_anchor=True, has_style_anchor=True)
		assert r.pass_ is True
		assert r.scores["alignment"] == 0.9
		assert r.scores["identity"] == 0.95
		assert r.scores["style"] == 0.9
		assert not r.identity_fail
		assert not r.style_fail
		assert not r.alignment_fail

	def test_hard_fail_identity_overrides_pass(self):
		j = '{"pass": true, "scores": {"alignment": 0.9, "identity": 0.95, "style": 0.9}, "hard_fail": {"alignment": false, "identity": true, "style": false}, "issues": [{"type": "identity_mismatch", "severity": "high", "detail": "换人了"}], "must_have": [], "missing": [], "suggested_patch": {"rebase": "char_anchor"}}'
		r = parse_review_json(j, has_char_anchor=True, has_style_anchor=True)
		assert r.pass_ is False
		assert r.identity_fail is True

	def test_invalid_json_returns_fail(self):
		r = parse_review_json("not json", has_char_anchor=False, has_style_anchor=False)
		assert r.pass_ is False
		assert len(r.issues) >= 1
		assert r.issues[0].type == "parse_error"

	def test_no_anchor_skips_identity_style(self):
		j = '{"pass": true, "scores": {"alignment": 0.9, "identity": 0.5, "style": 0.5}, "hard_fail": {"alignment": false, "identity": true, "style": true}, "issues": [], "must_have": [], "missing": [], "suggested_patch": {}}'
		r = parse_review_json(j, has_char_anchor=False, has_style_anchor=False)
		assert r.scores["identity"] == 1.0
		assert r.scores["style"] == 1.0
		assert r.hard_fail["identity"] is False
		assert r.hard_fail["style"] is False

	def test_below_threshold_fails(self):
		j = '{"pass": true, "scores": {"alignment": 0.7, "identity": 0.95, "style": 0.9}, "hard_fail": {"alignment": false, "identity": false, "style": false}, "issues": [], "must_have": [], "missing": [], "suggested_patch": {}}'
		r = parse_review_json(j, has_char_anchor=True, has_style_anchor=True)
		assert r.pass_ is False

	def test_require_char_anchor_missing_fails(self):
		"""primary_char_id 存在但无 char_anchor 且 require_char_anchor=true → 必须 fail"""
		j = '{"pass": true, "scores": {"alignment": 0.9, "identity": 1.0, "style": 1.0}, "hard_fail": {"alignment": false, "identity": false, "style": false}, "issues": [], "must_have": [], "missing": [], "suggested_patch": {}}'
		r = parse_review_json(
			j,
			has_char_anchor=False,
			has_style_anchor=False,
			primary_char_id="陆江仙",
			require_char_anchor=True,
		)
		assert r.pass_ is False
		assert r.hard_fail["identity"] is True
		assert r.scores["identity"] == 0.0
		assert any(i.type == "missing_char_anchor" for i in r.issues)

	def test_require_char_anchor_false_keeps_old_behavior(self):
		"""require_char_anchor=false 时无 anchor 仍放行（旧行为）"""
		j = '{"pass": true, "scores": {"alignment": 0.9, "identity": 0.5, "style": 0.5}, "hard_fail": {"alignment": false, "identity": true, "style": true}, "issues": [], "must_have": [], "missing": [], "suggested_patch": {}}'
		r = parse_review_json(
			j,
			has_char_anchor=False,
			has_style_anchor=False,
			primary_char_id="陆江仙",
			require_char_anchor=False,
		)
		assert r.scores["identity"] == 1.0
		assert r.scores["style"] == 1.0
		assert r.hard_fail["identity"] is False
		assert r.hard_fail["style"] is False
