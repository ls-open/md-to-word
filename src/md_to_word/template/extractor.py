"""md_to_word.template.extractor — 从现有参考 docx 反推格式规范。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from md_to_word.config import WORKSPACE_DIR

_SCRIPTS_DIR = WORKSPACE_DIR / "scripts"
if _SCRIPTS_DIR.is_dir() and str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import read_reference_docx


def extract_spec_from_docx(docx_path: Path | str, output_path: Optional[Path | str] = None) -> str:
    """从给定的 docx 模板反推单行 requirements.txt 草稿。"""
    p_in = Path(docx_path)
    ref = read_reference_docx.Ref(p_in)
    out_lines = []
    # 调用内部方法拼装草稿
    out_lines.append(f"# 从 {p_in.name} 反推的格式要求草稿")
    out_lines.append("# 请人工核对需确认部分\n")

    # 纸张与边距
    if ref.sect is not None:
        paper_sz = ref.paper_size()
        if paper_sz:
            out_lines.append(f"纸张：{paper_sz}")
        m = ref.margins()
        if m:
            out_lines.append(f"页边距：上{m['top']}cm 下{m['bottom']}cm 左{m['left']}cm 右{m['right']}cm")

    # 样式
    for cn, sid in read_reference_docx.STYLES_ORDER:
        desc = ref.format_style(sid)
        if desc:
            out_lines.append(f"{cn}：{desc}")

    content = "\n".join(out_lines) + "\n"
    if output_path:
        Path(output_path).write_text(content, encoding="utf-8")
    return content
