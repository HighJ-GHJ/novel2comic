# -*- coding: utf-8 -*-
"""
novel2comic/director_review

导演审阅：对 ShotScript 做节奏与转场审阅，输出 patch-only 补丁。
"""

from novel2comic.director_review.schema import PATCH_ALLOWLIST, validate_director_review
from novel2comic.director_review.apply import apply_director_patch
from novel2comic.director_review.fallback import apply_fallback_gaps, fallback_gap_after_ms

__all__ = [
	"PATCH_ALLOWLIST",
	"validate_director_review",
	"apply_director_patch",
	"apply_fallback_gaps",
	"fallback_gap_after_ms",
]
