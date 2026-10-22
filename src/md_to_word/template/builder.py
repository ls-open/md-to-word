"""md_to_word.template.builder — Word 样式模板生成器。

基于 pure_modern_base.docx 底模，将规范文本编译生成 Quarto / Pandoc 可用的 reference-doc。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from md_to_word.spec.models import TemplateSpec
from md_to_word.template.generator import generate_template


def build_template(
    spec_or_text: TemplateSpec | str,
    output_path: Path | str,
    *,
    margins: Optional[dict[str, float]] = None,
) -> Path:
    """根据格式要求文本生成 template.docx。

    只接受文本：TemplateSpec 是解析结果的**产物**，不是入口。
    """
    out = Path(output_path)
    if isinstance(spec_or_text, TemplateSpec):
        # 曾经这里把 dict 直接插进字符串拼成「要求文本」，产物是乱码且报错指向字体段。
        # TemplateSpec → 文本的序列化还没实现，宁可当场说清楚，也不能给一个看起来能跑的结果。
        raise TypeError(
            "build_template 目前只接受格式要求文本，不接受 TemplateSpec："
            "TemplateSpec → 文本的序列化尚未实现。请把原始的 requirements 文本传进来。"
        )

    generate_template(str(spec_or_text), str(out), margins=margins)
    return out
