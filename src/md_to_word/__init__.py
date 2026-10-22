"""md_to_word — 现代学术 Markdown 到标准 Word (.docx) 的确定性编译引擎。

提供 Python API 与命令行接口，支持中英文双语声明式排版与全流程质量门禁。
"""

from md_to_word.pipeline import ExportOptions, ExportResult, run_export_pipeline
from md_to_word.spec.models import TemplateSpec
from md_to_word.spec.parser import parse_requirements
from md_to_word.spec.serializer import serialize_requirements
from md_to_word.template.builder import build_template
from md_to_word.validator.check import ValidationReport, validate_manuscript

__version__ = "2.0.0.dev1"

__all__ = [
    "run_export_pipeline",
    "ExportOptions",
    "ExportResult",
    "validate_manuscript",
    "ValidationReport",
    "build_template",
    "parse_requirements",
    "serialize_requirements",
    "TemplateSpec",
    "__version__",
]
