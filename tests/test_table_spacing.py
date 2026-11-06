"""表格的两种留白：单元格四周的内边距、表格之后的间距。

两处都不是「引擎替作者决定留多少」，而是把作者声明的那个数翻译到位——所以不写就 0，
写了就得处处生效，产物与对账两边都得对上。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest
from docx import Document
from lxml import etree

from md_to_word.audit.inspector import audit
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.spec.parser import parse_format, parse_table_props
from md_to_word.spec.serializer import serialize_format
from md_to_word.template.extractor import Ref, q, read_table

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "presets" / "zh-academic.txt").read_text(encoding="utf-8")
# 整行换掉而不是往后追加：预设自己也会声明这两项，追加就撞成"写了两次"
SPEC = re.sub(r"^表格：.*$", "表格：居中 三线表 单元格垂直居中 单元格内边距0.15cm 表后间距6磅",
              PRESET, flags=re.M)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

BODY = """---
---

# 一 引言

| 指标 | 值 |
|:--|:--|
| 增长率 | 0.5 |

%% 表注 注：数据来源。

正文。
"""


def _export(tmp_path: Path, spec: str = SPEC, body: str = BODY):
    (tmp_path / "m.md").write_text(body, encoding="utf-8")
    (tmp_path / "f.txt").write_text(spec, encoding="utf-8")
    return run_export_pipeline(ExportOptions(
        input_path=tmp_path / "m.md",
        output_path=tmp_path / "m.docx",
        format_path=tmp_path / "f.txt",
    ))


def _part(tmp_path: Path, name: str) -> bytes:
    return zipfile.ZipFile(tmp_path / "m.docx").read(name)


def test_cell_margin_reaches_all_four_sides(tmp_path):
    """`单元格内边距` 说的是四周：只管左右的话，词名就在骗人。"""
    assert SPEC != PRESET, "预设里的表格行改了，这条断言要跟着改"
    result = _export(tmp_path)
    assert result.returncode == 0, result.errors
    styles = etree.fromstring(_part(tmp_path, "word/styles.xml"))
    cell_mar = next(
        s.find(f"{W}tblPr/{W}tblCellMar") for s in styles.iter(f"{W}style")
        if any(n.get(W + "val") == "Table" for n in s.findall(f"{W}name"))
    )
    assert [cell_mar.find(W + s).get(W + "w")
            for s in ("top", "left", "bottom", "right")] == ["85"] * 4


def test_table_gap_lands_after_the_table_note(tmp_path):
    """表注属于表格：垫片落在它之后，不然表格和注之间被撑开一道缝。"""
    result = _export(tmp_path)
    assert result.returncode == 0, result.errors
    xml = _part(tmp_path, "word/document.xml").decode("utf-8")
    spacer = re.search(r'<w:spacing w:before="0" w:after="0" w:line="120" w:lineRule="exact"/>', xml)
    assert spacer, "6 磅 = 120 二十分之一磅的定高空段落没写出来"
    assert xml.index("TableNote") < spacer.start()


def test_table_gap_without_a_note_sits_right_after_the_table(tmp_path):
    """没有表注时，垫片就紧贴表格。"""
    result = _export(tmp_path, body=BODY.replace("%% 表注 注：数据来源。\n\n", ""))
    assert result.returncode == 0, result.errors
    xml = _part(tmp_path, "word/document.xml").decode("utf-8")
    assert xml.index("</w:tbl>") < xml.index('w:line="120" w:lineRule="exact"')


def test_audit_reports_a_missing_gap(tmp_path):
    """对账要独立成立：把垫片删掉，它必须自己看出来。"""
    _export(tmp_path)
    docx = tmp_path / "m.docx"
    xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")
    stripped = re.sub(r'<w:p>(?:(?!</w:p>).)*?w:line="120" w:lineRule="exact".*?</w:p>', "", xml, flags=re.S)
    assert stripped != xml, "垫片没找到，删不动"
    _rewrite(docx, "word/document.xml", stripped)
    assert any("表后间距" in msg for _, msg in audit(docx, tmp_path / "f.txt"))


def test_a_space_before_the_value_parses_the_same():
    """`表后间距 6磅` 与 `表后间距6磅` 是同一种写法：组合词归一化对表格行同样成立。"""
    assert (parse_table_props("居中 三线表 表后间距 6磅")
            == parse_table_props("居中 三线表 表后间距6磅"))


def test_both_keywords_survive_a_round_trip():
    """`build_template(spec)` 是先序列化再解析的：这里漏一项，Python API 那份规约就被改了。"""
    text = serialize_format(parse_format(SPEC))
    assert "单元格内边距0.15cm" in text
    assert "表后间距6磅" in text


def test_a_table_ending_the_document_needs_no_gap(tmp_path):
    """没有「之后」就不垫，对账也不能因此判它不符。"""
    result = _export(tmp_path, body="# 一 引言\n\n| 指标 | 值 |\n|:--|:--|\n| 增长率 | 0.5 |\n")
    assert result.returncode == 0, result.errors


@pytest.mark.parametrize("sides,expected", [
    ((85, 85, 85, 85), "单元格内边距0.15cm"),
    ((0, 85, 0, 85), None),
])
def test_extractor_reads_cell_margin_only_when_it_is_uniform(tmp_path, sides, expected):
    """四边不同值时格式文件表达不了：要么读出一个数，要么列进需确认清单。"""
    document = Document()
    document.add_table(rows=2, cols=2, style="Table Grid")
    style = next(s for s in document.styles.element.findall(q("style"))
                 if s.get(q("styleId")) == "TableGrid")
    tbl_pr = style.find(q("tblPr"))
    for stale in tbl_pr.findall(q("tblCellMar")):   # 底模自带的要先清掉，不然用的是它
        tbl_pr.remove(stale)
    mar = tbl_pr.makeelement(q("tblCellMar"), {})
    for side, twips in zip(("top", "left", "bottom", "right"), sides):
        el = mar.makeelement(q(side), {})
        el.set(q("w"), str(twips))
        mar.append(el)
    tbl_pr.append(mar)
    path = tmp_path / "reference.docx"
    document.save(path)

    lines, doubt = read_table(Ref(path, "zh"))
    got = [line for line in lines if "单元格内边距" in line]
    if expected is None:
        assert got == []
        assert any("单元格内边距" in note for note in doubt), doubt
    else:
        assert expected in lines[0], lines


def _rewrite(docx: Path, name: str, content: str) -> None:
    """就地替换包里一个部件，其余条目原样搬运。"""
    with zipfile.ZipFile(docx) as src:
        items = [(info, src.read(info.filename)) for info in src.infolist()]
    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as dst:
        for info, data in items:
            dst.writestr(info, content.encode("utf-8") if info.filename == name else data)
