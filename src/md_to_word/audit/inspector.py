"""md_to_word.audit.inspector — 产物与格式要求逐条对账。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from md_to_word.config import WORKSPACE_DIR

_SCRIPTS_DIR = WORKSPACE_DIR / "scripts"
if _SCRIPTS_DIR.is_dir() and str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import audit_export


def audit_docx_against_spec(
    docx_path: Path | str, spec_path: Path | str
) -> tuple[bool, list[tuple[str, str]]]:
    """比对产物 docx 的实际 XML 属性与格式要求。返回 (是否完全匹配, 差异列表)。"""
    docx_p = Path(docx_path)
    spec_p = Path(spec_path)
    problems = audit_export.audit(docx_p, spec_p)
    return len(problems) == 0, problems
