"""两处「行高放不下」的边界：多行公式不许压到邻居，网格行数不许虚报。

- 正文用固定行距时，公式比这一行高，多出来的部分会压到上下两段正文上。
- 声明「每页 N 行」时，N 超过版心能放下的行数就兑现不了，Word 会把行高向上取整到
  网格整数倍，实际行数反而比不声明网格更少。

两条的第一半在 Word 渲染里都实测过（压穿、以及 44 行的实际行数），这里钉住机制。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from md_to_word.model.reader import read_markdown
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.spec.parser import parse_format
from md_to_word.template.builder import build_template
from md_to_word.template.generator import max_doc_grid_lines
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "presets" / "zh-academic.txt").read_text(encoding="utf-8")

EQUATION = "---\ncrossref:\n  chapters: true\n---\n\n# 一\n\n$$a=b$$ {#eq-a}\n"


def _spec_with(body_row: str, extra: str = "") -> str:
    rows = [body_row if line.startswith("正文：") else line for line in PRESET.splitlines()]
    return extra + "\n".join(rows) + "\n"


def _equation_spacing(tmp_path: Path, spec: str) -> str:
    template = tmp_path / "t.docx"
    build_template(spec, template)
    out = write_docx(read_markdown(EQUATION), template, tmp_path / "o.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    paragraph = next(p for p in xml.split("</w:p>") if "oMath" in p)
    return "".join(re.findall(r"<w:spacing[^/]*/>", paragraph))


EXACT = "正文：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距20磅 段前0磅 段后0磅 首行缩进2字符"
MULTIPLE = "正文：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.3倍 段前0磅 段后0磅 首行缩进2字符"


def test_equation_relaxes_fixed_line_spacing(tmp_path: Path) -> None:
    """固定行距下公式段落改成同值的「最小值」：单行不变，高的自己撑开。"""
    spacing = _equation_spacing(tmp_path, _spec_with(EXACT))

    assert 'w:line="400"' in spacing and 'w:lineRule="atLeast"' in spacing


def test_equation_leaves_multiple_spacing_alone(tmp_path: Path) -> None:
    """倍数行距本来就会撑开，不该改写行距；只补那 6 磅段后。"""
    spacing = _equation_spacing(tmp_path, _spec_with(MULTIPLE))

    assert "w:line=" not in spacing and "lineRule" not in spacing
    assert 'w:after="120"' in spacing


def test_equation_keeps_a_gap_below_it(tmp_path: Path) -> None:
    """公式盒子紧贴内容底部，不补段后就会贴着下文——实测上下 7.8 / 1.9pt。"""
    assert 'w:after="120"' in _equation_spacing(tmp_path, _spec_with(EXACT))


@pytest.mark.parametrize(
    ("body_line", "limit"),
    [("行距1.3倍", 34), ("行距1.0倍", 44), ("行距20磅", 34)],
)
def test_grid_limit_follows_the_body_line_height(body_line: str, limit: int) -> None:
    """上限 = 版心高 ÷ 正文行高；数字来自 Word 渲染实测（1.3 倍确实只落 34 行）。"""
    spec = parse_format(_spec_with(EXACT.replace("行距20磅", body_line)))
    assert max_doc_grid_lines(spec) == limit


def test_unreachable_grid_rows_are_reported(tmp_path: Path) -> None:
    """每页 44 行配 1.3 倍行距做不到，要提醒；22 行做得到，不该打扰。"""
    (tmp_path / "m.md").write_text("# 一\n\n正文。\n", encoding="utf-8")
    for lines, warned in ((44, True), (22, False)):
        (tmp_path / "f.txt").write_text(
            _spec_with(MULTIPLE, f"文档网格：每页{lines}行\n"), encoding="utf-8"
        )
        result = run_export_pipeline(
            ExportOptions(
                input_path=tmp_path / "m.md",
                output_path=tmp_path / "o.docx",
                format_path=tmp_path / "f.txt",
            )
        )
        hit = any("文档网格" in message for message in result.messages)
        assert hit is warned, f"每页{lines}行: {result.messages}"
