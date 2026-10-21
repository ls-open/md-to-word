"""md_to_word.template.builder — Word 样式模板生成器。

基于 pure_modern_base.docx 底模，将 TemplateSpec 或规范文本编译生成 Quarto / Pandoc 可用的 reference-doc。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from md_to_word.config import WORKSPACE_DIR
from md_to_word.spec.models import TemplateSpec

# 确保 scripts 目录在搜索路径中以便复用成熟实现
_SCRIPTS_DIR = WORKSPACE_DIR / "scripts"
if _SCRIPTS_DIR.is_dir() and str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import generate_template


def build_template(
    spec_or_text: TemplateSpec | str,
    output_path: Path | str,
    *,
    margins: Optional[dict[str, float]] = None,
) -> Path:
    """根据 Spec 或配置文本生成 template.docx。"""
    out = Path(output_path)
    if isinstance(spec_or_text, TemplateSpec):
        # 如果是已经解析好的 Spec，目前 generate_template 接收文本格式，或者通过内部方法
        # 在 2.0 中，支持传文本；后续 3.0 可重构为直接消费内存 Spec 对象
        raise NotImplementedError("目前支持传入 requirements 文本生成模板")
    text = str(spec_or_text)
    generate_template.generate_template(text, str(out), margins=margins)
    return out
