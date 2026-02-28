# -*- coding: utf-8 -*-
"""
scripts/smoke_tts_style_prompt.py

CosyVoice2 风格提示词冒烟测试：故意设 TTS_USE_STYLE_PROMPT=prefix，
验证 CosyVoice2 下仍强制 endofprompt，input 不以 instruction+\\n 开头。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 确保项目根在 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from novel2comic.providers.tts.siliconflow_tts import (
	TTS_STYLE_ENDOPROMPT,
	build_input_text,
	load_siliconflow_tts,
)


def main() -> int:
	# 故意设成会出问题的 prefix
	os.environ["TTS_USE_STYLE_PROMPT"] = "prefix"

	text = "你好。"
	style_prompt = "兴奋"

	# 1) 字符串级断言
	input_text, effective_mode = build_input_text(
		text,
		style_prompt,
		"prefix",
		model="FunAudioLLM/CosyVoice2-0.5B",
	)

	print(f"[smoke] mode 选择结果: {effective_mode}")
	print(f"[smoke] final input_text: {repr(input_text)}")
	print(f"[smoke] 是否触发强制降级: {effective_mode == 'endofprompt'}")

	# 断言
	assert not input_text.startswith(style_prompt + "\n"), "input 不应以 instruction+\\n 开头"
	assert TTS_STYLE_ENDOPROMPT in input_text, "应含 <|endofprompt|>"
	assert input_text == f"{style_prompt}{TTS_STYLE_ENDOPROMPT}{text}"

	print("[OK] smoke_tts_style_prompt passed")
	return 0


if __name__ == "__main__":
	sys.exit(main())
