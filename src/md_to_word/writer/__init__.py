"""md_to_word.writer — 文档模型 → OOXML（自研写出器）。"""

from md_to_word.writer.docx_writer import UnsupportedFeature, write_docx

__all__ = ["write_docx", "UnsupportedFeature"]
