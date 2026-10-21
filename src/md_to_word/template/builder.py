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
    """根据 Spec 或配置文本生成 template.docx。"""
    out = Path(output_path)
    if isinstance(spec_or_text, TemplateSpec):
        # 若传入的是 Spec 对象，当前先转换为其规范文本表达（或直接提取样式生成）
        # 3.0 将进一步演化为纯内存对象编译
        text = "\n".join(
            f"{s.get('style_name')}: {s}" for s in spec_or_text.styles
        )
    else:
        text = str(spec_or_text)

    generate_template(text, str(out), margins=margins)
    return out
