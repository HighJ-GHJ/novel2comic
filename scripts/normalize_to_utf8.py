# -*- coding: utf-8 -*-
"""
scripts/normalize_to_utf8.py

这个脚本做什么：
- 把输入 txt 统一转换为 UTF-8（内部标准编码），避免在 Linux/VSCode 出现乱码。
- 支持：
  1) 通过 uchardet 自动识别编码（推荐）
  2) 或手动指定 --from_encoding
- 输出：
  - 默认输出到 <out_dir>/<原文件名>（UTF-8）

使用示例：
python scripts/normalize_to_utf8.py \
  --in_path /path/to/raw.txt \
  --out_dir output/xuanjianxianzu/utf8

注意：
- 你当前确认输入为 GB18030，后续也很可能是 GB18030/GBK。
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def detect_encoding_by_uchardet(path: Path) -> str:
	"""
	用 uchardet 检测编码，返回例如 GB18030/UTF-8/UTF-16LE。
	要求系统已安装 uchardet。
	"""
	cp = subprocess.run(
		["uchardet", str(path)],
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		text=True,
	)
	if cp.returncode != 0:
		raise RuntimeError(f"uchardet failed: {cp.stderr.strip()}")
	enc = cp.stdout.strip()
	if not enc:
		raise RuntimeError("uchardet returned empty encoding")
	return enc


def main() -> None:
	ap = argparse.ArgumentParser()
	ap.add_argument("--in_path", required=True, help="输入 txt 路径（可能非 UTF-8）")
	ap.add_argument("--out_dir", required=True, help="输出目录（保存 UTF-8 文本）")
	ap.add_argument("--from_encoding", default="", help="手动指定源编码（留空则用 uchardet 自动检测）")
	ap.add_argument("--overwrite", action="store_true", help="允许覆盖已存在输出文件")
	args = ap.parse_args()

	in_path = Path(args.in_path)
	out_dir = Path(args.out_dir)
	out_dir.mkdir(parents=True, exist_ok=True)

	out_path = out_dir / in_path.name

	if out_path.exists() and not args.overwrite:
		raise SystemExit(f"Refuse to overwrite existing file: {out_path} (use --overwrite)")

	if args.from_encoding:
		src_enc = args.from_encoding.strip()
	else:
		src_enc = detect_encoding_by_uchardet(in_path)

	# 读入并转码：errors='strict' 让错误显式暴露，必要时你可改成 'ignore'
	data = in_path.read_bytes()
	try:
		text = data.decode(src_enc)
	except Exception as e:
		raise SystemExit(f"Decode failed: from={src_enc} err={e}")

	out_path.write_text(text, encoding="utf-8")
	print(f"OK: {in_path} ({src_enc}) -> {out_path} (UTF-8)")


if __name__ == "__main__":
	main()
