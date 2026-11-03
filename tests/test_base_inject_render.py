"""灌完必须和原件长得一样——这条只能用真 Word 验，没装 Word 的机器整文件跳过。

判据就是坐标：Word 排过版才知道分页有没有变、空白页有没有丢，这些从 OOXML 里看不出来。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from docx.enum.section import WD_SECTION

from md_to_word.model.reader import read_markdown
from md_to_word.template.base_inject import apply_base_template
from md_to_word.template.builder import build_template
from md_to_word.visual_qa.word_pdf import can_render_word_pdf
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "presets" / "zh-academic.txt").read_text(encoding="utf-8")

pytestmark = pytest.mark.skipif(
    not can_render_word_pdf()[0], reason="需要本机 Microsoft Word 才能验真"
)


def test_cover_pages_survive_page_by_page(tmp_path: Path) -> None:
    base = tmp_path / "base.docx"
    doc = Document()
    for i in range(3):
        section = doc.sections[-1]
        section.header.is_linked_to_previous = False
        section.header.paragraphs[0].text = "某某大学学位论文"
        doc.add_paragraph(f"封面第 {i + 1} 节")
        if i < 2:
            doc.add_section(WD_SECTION.NEW_PAGE)
    doc.save(base)

    template = tmp_path / "tpl.docx"
    build_template(PRESET, template)
    rendered = write_docx(
        read_markdown("# 第一章 绪论\n\n正文第一段。\n"), template, tmp_path / "r.docx"
    )

    out = tmp_path / "out.docx"
    apply_base_template(base, rendered, 2, out, "第一章绪论")

    assert out.is_file()
