"""md_to_word — 把 Markdown 编译成符合声明格式的 Word (.docx)，导出确定性。

提供 Python API 与命令行接口，支持中英文双语声明式排版与全流程质量门禁。
"""

from md_to_word.pipeline import ExportOptions, ExportResult, run_export_pipeline
from md_to_word.spec.models import TemplateSpec
from md_to_word.spec.parser import parse_format
from md_to_word.spec.serializer import serialize_format
from md_to_word.template.builder import build_template
from md_to_word.validator.check import ValidationReport, validate_manuscript

# 包元数据从这里取这一行（pyproject 的 version 是 dynamic），不维护第二份
__version__ = "3.2.0"


def export(
    manuscript,
    output=None,
    *,
    format=None,
    requirements=None,
    preset=None,
    pdf=False,
    lang=None,
) -> "ExportResult":
    """一行导出：`export("稿.md", "稿.docx", format="format.txt")`。

    返回 `ExportResult`；`result.returncode` 为 0 即成功，`result.errors` 是失败原因。
    这一层只是把 `ExportOptions` 的默认值摆好——等价于命令行 `md-to-word`。
    `requirements` 为旧版别名，推荐使用 `format`。
    """
    format_p = format if format is not None else requirements
    return run_export_pipeline(
        ExportOptions(
            input_path=manuscript,
            output_path=output,
            format_path=format_p,
            preset=preset,
            make_pdf=pdf,
            lang=lang,
        )
    )


# 向后兼容别名：供旧脚本与下游生态平滑过渡
parse_requirements = parse_format
serialize_requirements = serialize_format

__all__ = [
    "export",
    "run_export_pipeline",
    "ExportOptions",
    "ExportResult",
    "validate_manuscript",
    "ValidationReport",
    "build_template",
    "parse_format",
    "parse_requirements",
    "serialize_format",
    "serialize_requirements",
    "TemplateSpec",
    "__version__",
]
