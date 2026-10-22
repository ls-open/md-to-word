#!/usr/bin/env python3
"""generate_template.py — 入口：按格式要求文件生成样式模板

实现只有一份，在包里（`pipx install md-to-word-docx`）。本文件只把命令行参数转过去；
从源码检出运行时，若有 `src/` 就用仓库里那份，否则用已安装的包。
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from md_to_word.template.generator import main  # noqa: E402

if __name__ == "__main__":
    main()
