# -*- coding: utf-8 -*-
"""
novel2comic/__main__.py

目的：
- 支持 `python -m novel2comic` 这种启动方式。
- 直接转发到 cli.main()，不在这里放业务逻辑。

为什么要有它：
- 习惯上 Python 包提供 __main__.py 会更“像一个工具”。
"""

from .cli import main

if __name__ == "__main__":
	main()
