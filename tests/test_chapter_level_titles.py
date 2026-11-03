"""章级但非章标题的段落（参考文献）：结构是一级标题，外观是直接格式。

页眉的 `{样式标题:Heading 1}` 是 STYLEREF 域，只认样式名。标题段落若用自己的样式，
域只能回退到上一个一级标题——文献页页眉就会显示「第六章」。所以结构必须升成
Heading 1，外观再从格式文件那一行抄进来。
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

MANUSCRIPT = "%% 文档标题 测试\n\n# 第一章\n\n正文。\n\n%% 参考文献标题 参 考 文 献\n"


def _references_paragraph(tmp_path: Path, style_row: str | None = None) -> str:
    """导出后取文献标题那一段的 XML。"""
    spec = PRESET
    if style_row:
        spec = "\n".join(
            style_row if line.startswith("参考文献标题：") else line
            for line in PRESET.splitlines()
        )
    template = tmp_path / "t.docx"
    build_template(spec, template)
    out = write_docx(read_markdown(MANUSCRIPT), template, tmp_path / "o.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    paragraphs = re.findall(r"<w:p>.*?</w:p>", xml, re.S)
    return next(p for p in paragraphs if "参 考 文 献" in p)


def test_heading_so_the_header_field_can_find_it(tmp_path: Path) -> None:
    """结构必须是 Heading 1——STYLEREF 只认样式名，别的名字它取不到。"""
    paragraph = _references_paragraph(tmp_path)

    assert '<w:pStyle w:val="Heading1"/>' in paragraph


def test_the_declared_look_is_kept_as_direct_formatting(tmp_path: Path) -> None:
    """换了结构不能换长相：字体、字号、居中、段前段后都得还是那一行写的。"""
    paragraph = _references_paragraph(tmp_path)

    assert '<w:jc w:val="center"/>' in paragraph
    assert 'w:sz w:val="32"' in paragraph  # 三号 = 16pt = 32 半磅
    assert 'w:eastAsia="黑体"' in paragraph
    assert '<w:keepNext/>' in paragraph


def test_stays_out_of_the_toc_unless_the_row_says_so(tmp_path: Path) -> None:
    """升成一级标题不能顺手把目录也改了：要不要进目录由「加入目录」说了算。"""
    assert '<w:outlineLvl w:val="9"/>' in _references_paragraph(tmp_path)

    declared = _references_paragraph(
        tmp_path,
        "参考文献标题：黑体/Times New Roman 三号 加粗 不倾斜 居中 行距1.0倍 "
        "段前24磅 段后18磅 首行缩进0字符 与下段同页 段前分页 加入目录",
    )
    assert "outlineLvl" not in declared, "写了「加入目录」就交给 Heading 1 的大纲级别"
    assert "<w:pageBreakBefore/>" in declared
