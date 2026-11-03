"""分节的页眉页脚：每节各自带着引用，要「不要」得显式说。

OOXML 里没写引用等于「沿用上一节」，第一节没有可沿用的，结果就是前置部分整段没有
页眉。所以默认每节都带引用，封面那种「不要页眉页脚」用参数表达。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from md_to_word.model.reader import read_markdown
from md_to_word.template.builder import build_template
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "presets" / "zh-academic.txt").read_text(encoding="utf-8")
DECOR = (
    "页眉内容：某某大学学位论文 {样式标题:Heading 1}\n"
    "页眉：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符\n"
)


def _sections(tmp_path: Path, manuscript: str) -> list[str]:
    template = tmp_path / "t.docx"
    build_template(DECOR + PRESET, template)
    out = write_docx(read_markdown(manuscript), template, tmp_path / "o.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    return re.findall(r"<w:sectPr>.*?</w:sectPr>", xml, re.S)


def test_every_section_keeps_the_header_reference(tmp_path: Path) -> None:
    """普通分节不该把页眉丢掉——以前前置部分整段没有页眉。"""
    sections = _sections(tmp_path, "# 一\n\n正文。\n\n{{< section >}}\n\n# 二\n\n正文。\n")

    assert len(sections) == 2
    assert all("headerReference" in s for s in sections)


def test_a_section_can_opt_out_of_header_and_footer(tmp_path: Path) -> None:
    """封面：`页眉=无 页脚=无`，这一节不带引用。"""
    sections = _sections(
        tmp_path, "# 封面\n\n{{< section 页眉=无 页脚=无 >}}\n\n# 一\n\n正文。\n"
    )

    assert "headerReference" not in sections[0] and "footerReference" not in sections[0]
    assert "headerReference" in sections[1], "后面那一节不该受影响"


def test_only_the_marked_section_opts_out(tmp_path: Path) -> None:
    """只要页眉、页脚照旧：两个开关各自独立。"""
    sections = _sections(tmp_path, "# 封面\n\n{{< section 页眉=无 >}}\n\n# 一\n\n正文。\n")

    assert "headerReference" not in sections[0]
    assert "footerReference" in sections[0]


def test_trailing_section_does_not_restart_page_numbers(tmp_path: Path) -> None:
    """格式文件的「起始N」落在最后一节；有分节符时不能再让最后一节从 1 重编。"""
    sections = _sections(
        tmp_path,
        "# 一\n\n正文。\n\n{{< section 页码=阿拉伯 起始=1 >}}\n\n# 二\n\n正文。\n",
    )

    assert 'w:start' not in sections[-1], "最后一节应当接着上一节编"
    assert 'w:start="1"' in sections[0], "起始值由分节标记自己声明"


def test_single_section_keeps_the_start_from_the_format_file(tmp_path: Path) -> None:
    """没有分节符时，「起始」就是整份文档的起点，照旧写进唯一的 sectPr。"""
    sections = _sections(tmp_path, "# 一\n\n正文。\n")

    assert len(sections) == 1 and 'w:start="1"' in sections[0]
