"""md_to_word.template — 模板生成与反推子包。"""

from md_to_word.template.builder import build_template
from md_to_word.template.extractor import extract_spec_from_docx

__all__ = ["build_template", "extract_spec_from_docx"]
