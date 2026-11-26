"""Word 实机排版验真：长表格跨页后表头是否真的重复、每一行是否都还在。

结构测试只能证明 `w:tblHeader` 写进了 XML；Word 认不认、跨页后有没有重复，
只有让它真排一次版、再从 PDF 里读文字才算数。需要本机 Microsoft Word（macOS）。
"""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata

import pytest

from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.visual_qa.word_pdf import can_render_word_pdf

pytestmark = [
    pytest.mark.word,
    pytest.mark.skipif(not can_render_word_pdf()[0], reason="需要本机 Microsoft Word"),
]

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt"

HEADER = "表头行号"
ROWS = 45


def _pdf_pages_text(pdf: Path) -> list[str]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf)
    try:
        pages = []
        for page in document:
            textpage = page.get_textpage()
            try:
                pages.append(textpage.get_text_range())
            finally:
                textpage.close()
        return pages
    finally:
        document.close()


def test_a_long_table_repeats_its_header_and_keeps_every_row(tmp_path: Path) -> None:
    body = "\n".join(
        f"| 第{i:02d}行 | 数值{i:02d} | 说明文字{i:02d} | 补充{i:02d} |"
        for i in range(1, ROWS + 1)
    )
    manuscript = tmp_path / "table.md"
    manuscript.write_text(
        "# 一 长表\n\n"
        "%% 表题 **表 1** 跨页长表\n\n"
        f"| 表头行号 | 表头数值 | 表头说明 | 表头附注 |\n|:--|--:|:--|:--|\n{body}\n\n"
        "%% 表注 注：长表用于验证跨页表头。\n",
        encoding="utf-8",
    )
    out = tmp_path / "table.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=out,
        format_path=PRESET,
        make_pdf=True,
    ))
    assert result.returncode == 0, result.errors
    pdf = out.with_suffix(".pdf")
    assert pdf.is_file()

    pages = _pdf_pages_text(pdf)
    assert len(pages) >= 2, "这份稿子必须真的跨页，否则测不到表头重复"

    # PDF 提取会在 CJK 与数字之间插空格（“第 01 行”），比对前统一压掉空白。
    compact = [re.sub(r"\s+", "", text) for text in pages]
    flat = "\n".join(compact)
    missing = [f"第{i:02d}行" for i in range(1, ROWS + 1) if f"第{i:02d}行" not in flat]
    assert not missing, f"表格行在 Word 排版后丢失：{missing[:5]}"

    # 表头在至少两页出现：首页表格与跨页后的续页。只出现一次说明 Word 没重复。
    header_pages = [i for i, text in enumerate(compact) if HEADER in text]
    assert len(header_pages) >= 2, f"表头只出现在 {header_pages}，跨页后没有重复"


def test_complex_formulas_survive_a_real_word_render(tmp_path: Path) -> None:
    """aligned / cases / matrix 不只要能写成 OMML，还要能被 Word 真排出来。"""
    manuscript = tmp_path / "math.md"
    manuscript.write_text(
        "# 一 公式\n\n"
        "$$\n\\begin{aligned}\ny &= ax + b \\\\\nz &= c + d\n\\end{aligned}\n$$ {#eq-a}\n\n"
        "$$\n\\begin{cases}\na, & x>0 \\\\\nb, & x\\le 0\n\\end{cases}\n$$\n\n"
        "$$\n\\begin{pmatrix}\n1 & 0 \\\\\n0 & 1\n\\end{pmatrix}\n$$\n\n"
        "由 @eq-a 可知。\n",
        encoding="utf-8",
    )
    out = tmp_path / "math.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript, output_path=out, format_path=PRESET, make_pdf=True,
    ))
    assert result.returncode == 0, result.errors
    pages = _pdf_pages_text(out.with_suffix(".pdf"))
    flat = re.sub(r"\s+", "", unicodedata.normalize("NFKC", "".join(pages)))
    for needle in ("ax+b", "c+d", "x>0", "(1)", "式(1)"):
        assert needle in flat, (needle, flat[:300])
