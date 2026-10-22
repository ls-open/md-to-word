#!/usr/bin/env python3
"""read_reference_docx.py — 入口：从参考 .docx 反推格式要求草稿

实现只有一份，在包里（`pipx install md-to-word`）。本文件只把命令行参数转过去；
从源码检出运行时，若有 `src/` 就用仓库里那份，否则用已安装的包。
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from md_to_word.template.extractor import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
