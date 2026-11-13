"""对账器的三条判据：开关型元素、缺节的产物、继承来的字号。

共同点是「读错了会安静地得出相反结论」：把 `val="0"` 当成开、把没有节属性的产物当成
全部通过、把继承来的字号当成没写。三条都只在产物被改坏之后才暴露，所以这里手动改坏
一份合规产物再让对账去认。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from md_to_word.audit.inspector import audit_docx_against_spec

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt"

MANUSCRIPT = """\
%% 文档标题 对账测试稿

# 一、引言

正文一段，用来占位。

%% 表题 表 1 测试

| 参数 | 含义 |
|:--|:--|
| a | b |
"""


@pytest.fixture
def good_docx(tmp_path: Path) -> Path:
    from md_to_word.pipeline import ExportOptions, run_export_pipeline

    manuscript = tmp_path / "m.md"
    manuscript.write_text(MANUSCRIPT, encoding="utf-8")
    (tmp_path / "format.txt").write_text(
        PRESET.read_text(encoding="utf-8"), encoding="utf-8"
    )
    out = tmp_path / "out.docx"
    result = run_export_pipeline(
        ExportOptions(input_path=manuscript, output_path=out,
                      format_path=tmp_path / "format.txt")
    )
    assert result.returncode == 0, result.errors
    return out


def _rewrite(docx: Path, member: str, transform) -> Path:
    """把 docx 里某个部件读出来改一改再塞回去。"""
    with zipfile.ZipFile(docx) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    text = parts[member].decode("utf-8")
    parts[member] = transform(text).encode("utf-8")
    docx.unlink()
    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return docx


def _problems(docx: Path) -> list[str]:
    matched, problems = audit_docx_against_spec(docx, PRESET, "zh")
    return [] if matched else [msg for _, msg in problems]


def test_a_good_export_passes(good_docx: Path) -> None:
    """先确认这份产物本身是合规的，后面三条才有意义。"""
    assert _problems(good_docx) == []


def test_a_product_without_section_properties_is_not_silently_approved(
    good_docx: Path,
) -> None:
    """纸张、页边距、装订线、页码全挂在 body 级 sectPr 上。

    取不到它的时候那些判据一条都跑不了。以前这里写的是 `if sect is not None:` 而没有
    else——没写 sectPr 的产物会拿到「逐条对上」的绿灯，它的纸张和页边距根本没被看过。
    """
    _rewrite(
        good_docx,
        "word/document.xml",
        lambda xml: re.sub(r"<w:sectPr[ >].*?</w:sectPr>", "", xml, flags=re.S),
    )
    problems = _problems(good_docx)
    assert problems, "没有 sectPr 的产物被判成合规了"
    assert any("sectPr" in msg for msg in problems), problems


@pytest.mark.parametrize(
    ("xml", "expected"),
    [
        ("<w:keepNext/>", True),
        ('<w:keepNext w:val="1"/>', True),
        ('<w:keepNext w:val="true"/>', True),
        ('<w:keepNext w:val="0"/>', False),
        ('<w:keepNext w:val="false"/>', False),
        ('<w:keepNext w:val="off"/>', False),
    ],
)
def test_the_switch_reader_honours_every_way_of_writing_off(xml: str, expected: bool) -> None:
    """`<w:keepNext w:val="0"/>` 是**明确关掉**，不是「写了」。

    只按元素在不在判断，会把从 basedOn 继承来的「关」读成「开」，于是一份其实没生效的
    产物被判合规。
    """
    from docx.oxml.ns import nsdecls
    from lxml import etree

    from md_to_word.audit.inspector import _element_on

    fragment = xml.replace("<w:keepNext", f"<w:keepNext {nsdecls('w')}", 1)
    assert _element_on(etree.fromstring(fragment)) is expected
    assert _element_on(None) is False


def test_a_switch_turned_off_in_the_product_is_reported(good_docx: Path) -> None:
    """端到端：把产物里「与下段同页」改成 val="0"，对账必须报出来。"""
    with zipfile.ZipFile(good_docx) as z:
        styles = z.read("word/styles.xml").decode("utf-8")
    if "<w:keepNext" not in styles:
        pytest.skip("这份预设没有声明 keepNext")

    before = _problems(good_docx)
    _rewrite(
        good_docx,
        "word/styles.xml",
        lambda xml: re.sub(r"<w:keepNext(?: [^/>]*)?/>", '<w:keepNext w:val="0"/>', xml),
    )
    assert len(_problems(good_docx)) > len(before), "把 keepNext 改成 val=\"0\" 之后仍然判合规"


def test_font_size_inherited_from_based_on_is_accepted(good_docx: Path) -> None:
    """字号写在父样式上是合法的 OOXML，也是反推学校模板的常见形态。

    直读本样式的 `w:sz` 会得到 None，然后把一份合规产物判成不合规并拒绝交付。
    """
    from docx.oxml.ns import qn as _qn
    from lxml import etree

    with zipfile.ZipFile(good_docx) as z:
        styles_xml = z.read("word/styles.xml")
    root = etree.fromstring(styles_xml)

    normal = root.find(f".//{_qn('w:style')}[@{_qn('w:styleId')}='Normal']")
    assert normal is not None
    normal_rpr = normal.find(_qn("w:rPr"))
    if normal_rpr is None:
        normal_rpr = etree.SubElement(normal, _qn("w:rPr"))

    moved = False
    for style in root.findall(_qn("w:style")):
        sid = style.get(_qn("w:styleId"))
        if sid == "Normal":
            continue
        rpr = style.find(_qn("w:rPr"))
        if rpr is None:
            continue
        sz = rpr.find(_qn("w:sz"))
        if sz is None:
            continue
        # 新建一条父样式扛住这个字号，再让本样式 basedOn 它——不动 Normal，
        # 否则会顺带改掉 Normal 自己的要求，测不出想测的东西
        rpr.remove(sz)
        parent = etree.Element(_qn("w:style"))
        parent.set(_qn("w:type"), "paragraph")
        parent.set(_qn("w:styleId"), "InheritCarrier")
        name = etree.SubElement(parent, _qn("w:name"))
        name.set(_qn("w:val"), "InheritCarrier")
        carrier_rpr = etree.SubElement(parent, _qn("w:rPr"))
        carrier_rpr.append(sz)
        style.insert(1, parent)
        based = etree.Element(_qn("w:basedOn"))
        based.set(_qn("w:val"), "InheritCarrier")
        style.insert(1, based)
        moved = True
        break

    if not moved:
        pytest.skip("产物里没有可挪走的显式字号")

    _rewrite(
        good_docx,
        "word/styles.xml",
        lambda _xml: etree.tostring(root, encoding="unicode"),
    )
    assert _problems(good_docx) == [], "继承来的字号被当成「产物 None」"
