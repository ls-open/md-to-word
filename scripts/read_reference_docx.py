#!/usr/bin/env python3
"""read_reference_docx.py — 向后兼容垫片脚本（实现已收敛至 md_to_word.template.extractor）。"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from md_to_word.template.extractor import *

if __name__ == '__main__':
    sys.exit(main())
