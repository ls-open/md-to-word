"""页眉下边框的线型与图片段落的对齐，都由要求文件里的一行决定。

两者都是「学校/期刊各有一套」的排版项，所以判据不是"我们选了哪种"，而是
**写什么就落成什么**：换一个词就换一种线型，不必改代码。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from md_to_word.spec.parser import parse_requirements
from md_to_word.template.builder import build_template

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "presets" / "zh-academic.txt").read_text(encoding="utf-8")

HEADER = (
    "页眉：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 "
    "段前0磅 段后0磅 首行缩进0字符 {border}\n"
)

# 中文写法 → 期望落到 styles.xml 的 OOXML 线型
CASES = [
    ("下边框单线", "single"),
    ("下边框双线", "thinThickMediumGap"),
    ("下边框等宽双线", "double"),
    ("下边框上粗下细", "thickThinMediumGap"),
    ("下边框三线", "thinThickThinMediumGap"),
]


def _styles_xml(tmp_path: Path, req: str) -> str:
    out = tmp_path / "t.docx"
    build_template(req, out)
    with zipfile.ZipFile(out) as archive:
        return archive.read("word/styles.xml").decode("utf-8")


@pytest.mark.parametrize(("clause", "val"), CASES)
def test_header_border_variant_reaches_the_template(tmp_path: Path, clause: str, val: str) -> None:
    styles = _styles_xml(tmp_path, PRESET + HEADER.format(border=clause))
    assert f'w:val="{val}"' in styles, f"{clause} 没落到 styles.xml"


@pytest.mark.parametrize(("clause", "val"), CASES)
def test_parser_maps_every_variant(clause: str, val: str) -> None:
    from md_to_word.template.generator import BOTTOM_BORDER_STYLE

    spec = parse_requirements(PRESET + HEADER.format(border=clause))
    header = next(s for s in spec.styles if s["style_name"] == "Header")
    assert BOTTOM_BORDER_STYLE[header["bottom_border"]] == val


def test_figure_alignment_follows_the_requirements_file(tmp_path: Path) -> None:
    """图片段落默认居中，要求文件写「左对齐」就左对齐——不是写死的。"""
    req = PRESET.replace(
        "图：宋体/Times New Roman 五号 不加粗 不倾斜 居中",
        "图：宋体/Times New Roman 五号 不加粗 不倾斜 左对齐",
    )
    spec = parse_requirements(req)
    figure = next(s for s in spec.styles if s["style_name"] == "Captioned Figure")
    assert figure["alignment"] == 0  # WD_ALIGN_PARAGRAPH.LEFT

    styles = _styles_xml(tmp_path, req)
    assert 'w:styleId="CaptionedFigure"' in styles
