"""md_to_word.postprocessor.equations — Word 原生公式排版优化与主题净化。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from md_to_word.config import WORKSPACE_DIR

_SCRIPTS_DIR = WORKSPACE_DIR / "scripts"
if _SCRIPTS_DIR.is_dir() and str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import fix_docx_equations


def postprocess_docx(
    docx_path: Path | str,
    *,
    manuscript_path: Optional[Path | str] = None,
    eq_number_style: str = "asis",
) -> Path:
    """对编译出的 docx 进行公式居中与编号靠右、三线表列宽铺开、以及 XML 主题净化。"""
    docx_path = Path(docx_path)
    table_ratios = None
    if manuscript_path:
        p_ms = Path(manuscript_path)
        if p_ms.is_file():
            text = p_ms.read_text(encoding="utf-8")
            table_ratios = fix_docx_equations.md_table_width_ratios(text)
    fix_docx_equations.process_docx(str(docx_path), eq_number_style=eq_number_style, table_ratios=table_ratios)
    return docx_path
