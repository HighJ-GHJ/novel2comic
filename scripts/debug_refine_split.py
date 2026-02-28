# -*- coding: utf-8 -*-
"""
scripts/debug_refine_split.py

这个脚本做什么：
- 读取章节文本（默认 docs/chapter_clean.txt）
- baseline 规则切分 -> base_shots
- 调用 refine_shot_split skill（通过 SiliconFlow LLM）-> refined_shots
- 打印：
  1) baseline/refine 的 shot 数
  2) refine 是否 fallback（失败回退 baseline）
  3) 若失败，输出错误原因
  4) 预览前 N 条 refined shots（便于你肉眼检查切分质量）

使用方式：
1) 在项目根目录创建 .env（并确保 .gitignore 忽略它）：
   SILICONFLOW_API_KEY=xxx
   SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
   SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2
2) 放入测试文本：docs/chapter_clean.txt
3) 运行：
   python scripts/debug_refine_split.py
"""

from __future__ import annotations

import argparse

from novel2comic.core.split_baseline import split_baseline, SplitConfig
from novel2comic.skills.refine_shot_split.skill import RefineShotSplitSkill
from novel2comic.skills.refine_shot_split.schema import Constraints
from novel2comic.providers.llm.siliconflow_client import load_siliconflow_client


def build_argparser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser()
	p.add_argument("--in_path", default="docs/chapter_clean.txt", help="输入章节文本路径（UTF-8）")
	p.add_argument("--chapter_id", default="ch_debug", help="章节ID（用于 patch 标识）")

	# baseline 切分参数：先用默认，后续我们根据统计调优
	p.add_argument("--min_chars", type=int, default=80)
	p.add_argument("--soft_target", type=int, default=140)
	p.add_argument("--hard_cut", type=int, default=220)

	# refine 目标 shot 数范围
	p.add_argument("--min_shots", type=int, default=60)
	p.add_argument("--max_shots", type=int, default=120)

	p.add_argument("--preview", type=int, default=8, help="预览 refined 前 N 条")
	return p


def main() -> None:
	args = build_argparser().parse_args()

	with open(args.in_path, "r", encoding="utf-8") as f:
		text = f.read()

	# 1) baseline
	cfg = SplitConfig(
		min_chars=args.min_chars,
		soft_target=args.soft_target,
		hard_cut=args.hard_cut,
	)
	base_shots = split_baseline(text, cfg)
	print(f"[baseline] shots={len(base_shots)} (min_chars={args.min_chars}, soft_target={args.soft_target}, hard_cut={args.hard_cut})")

	# 2) refine（从 .env 加载，不需要 export）
	llm = load_siliconflow_client(project_root=".")
	try:
		skill = RefineShotSplitSkill(llm)
		c = Constraints(
			min_shots=args.min_shots,
			max_shots=args.max_shots,
			forbid_cross_scene_break=True,
		)

		result = skill.run(args.chapter_id, base_shots, c)

		print(f"[refine] shots={len(result.refined_shots)} fallback={result.used_fallback}")
		if result.used_fallback:
			print(f"[refine] error={result.error}")

		print(f"\n--- preview refined shots (first {args.preview}) ---")
		for i, s in enumerate(result.refined_shots[: args.preview]):
			snip = s.text.replace("\n", " ")
			if len(snip) > 160:
				snip = snip[:160] + "..."
			print(f"{i:03d} [{s.kind}] {snip}")

	finally:
		llm.close()


if __name__ == "__main__":
	main()
