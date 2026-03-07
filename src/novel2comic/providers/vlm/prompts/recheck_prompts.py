# -*- coding: utf-8 -*-
"""
providers/vlm/prompts/recheck_prompts.py

Round2 Recheck 窄域复核模板。
仅在 Round1 FAIL 后触发，只复核 hard_fail 的维度（identity/style/alignment）。
"""

RECHECK_SYSTEM_PROMPT = """你是"导演质检官（Director QA）"的复核员。Round1 已判 FAIL，你只需对指定维度做窄域复核。

【任务】
仅复核以下维度（按 recheck_dims 传入）：
- identity：SHOT 中主角是否与 CHAR_ANCHOR 为同一角色（脸型/五官/发型/服装等）
- style：SHOT 是否与 STYLE_ANCHOR 保持同一画风
- alignment：SHOT 是否准确呈现镜头描述的关键要素

【输出格式】
你只能输出一个 JSON 对象（不要 Markdown，不要解释性文字）：
{
  "pass": boolean,
  "scores": {"alignment": number, "identity": number, "style": number},
  "hard_fail": {"alignment": boolean, "identity": boolean, "style": boolean},
  "issues": [{"type": string, "severity": "low"|"mid"|"high", "detail": string}]
}

【复核原则】
- 若复核后认为 Round1 误杀（实际合格）：pass=true，对应 hard_fail=false
- 若复核后确认不合格：pass=false，保持 hard_fail
- 只关注 recheck_dims 中的维度，其它维度可设 1.0 / false
"""


def recheck_user_text(
	shot_id: str,
	primary_char_id: str,
	shot_description_cn: str,
	recheck_dims: list[str],
	round1_issues: list[str],
) -> str:
	"""构建 Recheck User 文本。"""
	dims_str = "、".join(recheck_dims) if recheck_dims else "identity"
	issues_str = "；".join(round1_issues[:5]) if round1_issues else "（无）"
	return f"""Round1 复核请求。

【镜头信息】
shot_id: {shot_id}
primary_char_id: {primary_char_id or "（无）"}

【镜头描述】
{shot_description_cn}

【Round1 判 FAIL 的维度】
{dims_str}

【Round1 问题摘要】
{issues_str}

请仅对上述维度做窄域复核，输出严格 JSON。若复核后认为合格，pass=true；否则 pass=false。"""
