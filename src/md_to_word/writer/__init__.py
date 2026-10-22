"""md_to_word.writer — 文档模型 → OOXML（v3 自研渲染器的写出侧）。"""

from md_to_word.writer.docx_writer import UnsupportedFeature, write_docx

__all__ = ["write_docx", "UnsupportedFeature"]
