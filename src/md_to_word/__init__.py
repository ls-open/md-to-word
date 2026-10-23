"""md_to_word — 把 Markdown 编译成符合声明格式的 Word (.docx)，导出确定性。

提供 Python API 与命令行接口，支持中英文双语声明式排版与全流程质量门禁。
"""

from md_to_word.pipeline import ExportOptions, ExportResult, run_export_pipeline
from md_to_word.spec.models import TemplateSpec
from md_to_word.spec.parser import parse_requirements
from md_to_word.spec.serializer import serialize_requirements
from md_to_word.template.builder import build_template
from md_to_word.validator.check import ValidationReport, validate_manuscript

# 包元数据从这里取这一行（pyproject 的 version 是 dynamic），不维护第二份
__version__ = "2.3.0"


def export(
    manuscript,
    output=None,
    *,
    requirements=None,
    preset=None,
    template=None,
    pdf=False,
    lang=None,
) -> "ExportResult":
    """一行导出：`export("稿.md", "稿.docx", preset="zh-academic")`。

    返回 `ExportResult`；`result.returncode` 为 0 即成功，`result.errors` 是失败原因。
    这一层只是把 `ExportOptions` 的默认值摆好——等价于命令行 `md-to-word`。
    """
    return run_export_pipeline(
        ExportOptions(
            input_path=manuscript,
            output_path=output,
            requirements_path=requirements,
            preset=preset,
            template_path=template,
            make_pdf=pdf,
            lang=lang,
        )
    )

__all__ = [
    "export",
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
