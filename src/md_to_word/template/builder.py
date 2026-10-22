"""md_to_word.template.builder — Word 样式模板生成器。

基于 pure_modern_base.docx 底模，把格式要求文本编译成只有 styles.xml（及页眉页脚、
页面设置）的模板；写出器拿它当作样式的唯一来源。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from md_to_word.spec.models import TemplateSpec
from md_to_word.spec.serializer import serialize_requirements
from md_to_word.template.generator import generate_template


def build_template(
    spec_or_text: TemplateSpec | str,
    output_path: Path | str,
    *,
    margins: Optional[dict[str, float]] = None,
    lang: str = "zh",
) -> Path:
    """根据格式要求文本（或 TemplateSpec）生成 template.docx。

    传 TemplateSpec 时会先序列化成正典文本再生成；往返等价由
    tests/test_serializer.py 守着。
    """
    out = Path(output_path)
    if isinstance(spec_or_text, TemplateSpec):
        text = serialize_requirements(spec_or_text)
    else:
        text = str(spec_or_text)

    generate_template(text, str(out), margins=margins, lang=lang)
    return out
