"""md_to_word.audit — 产物内容检查与格式对账门禁子包。"""

from md_to_word.audit.inspector import audit_docx_against_spec
from md_to_word.audit.postflight import (
    verify_chinese_integrity, verify_latin_integrity, verify_numeric_integrity,
)

__all__ = [
    "audit_docx_against_spec",
    "verify_chinese_integrity",
    "verify_latin_integrity",
    "verify_numeric_integrity",
]
