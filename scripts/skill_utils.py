#!/usr/bin/env python3
"""skill_utils.py — 向后兼容垫片脚本（实现已收敛至 md_to_word.utils.skill_utils）。"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from md_to_word.utils.skill_utils import *
