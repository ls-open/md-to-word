"""反推参考文件时，`docDefaults` 与样式继承链两处的生效值。

三条都是同一类失败：**Word 里看得见的格式，草稿里没有**（或写成了另一个值）。
共同点是"参考文件没在样式那一层写"，而读取方只看样式那一层：

1. `docDefaults/pPrDefault` 里的行距、段前段后 —— python-docx 与 Word 默认模板都把它们
   写在 docDefaults 里，真实参考文件里极常见；漏读就整条落成"行距1.0倍、段距不写"，
   照着草稿生成的模板就和参考文件不是一回事了。
2. 整条链上都没有 `w:spacing` 时，`段前`/`段后` 不能干脆不写 —— 少字段的草稿喂回生成器
   会被直接拒掉，而拒的理由（"缺少段前"）与用户看到的现象（排版不对）对不上。
3. 表样式也能 `basedOn` —— 只看最外层那层，派生样式的表格边框就被判成"没定义"。

判据一律是「**参考文件里生效的是什么，草稿就写什么**」，且草稿本身必须是一份能生成
模板的合法格式文件。
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

from docx import Document
from docx.shared import Pt

from md_to_word.template.builder import build_template
from md_to_word.template.extractor import Ref, _build_draft, clauses_for, q, read_table

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt").read_text(encoding="utf-8")


def _style_of(document, style_id: str):
    for style in document.styles.element.findall(q("style")):
        if style.get(q("styleId")) == style_id:
            return style
    raise AssertionError(f"没有 {style_id}")


def _strip_spacing(document) -> None:
    """把 styles.xml 里的 `w:spacing` 全删干净：行距、段距、字距都不留。"""
    for element in list(document.styles.element.iter(q("spacing"))):
        element.getparent().remove(element)


def _set_doc_defaults_spacing(document, *, line: int, after: int) -> None:
    defaults = document.styles.element.find(q("docDefaults"))
    paragraph_properties = defaults.find(f'{q("pPrDefault")}/{q("pPr")}')
    for old in paragraph_properties.findall(q("spacing")):
        paragraph_properties.remove(old)
    spacing = paragraph_properties.makeelement(q("spacing"), {})
    spacing.set(q("line"), str(line))
    spacing.set(q("lineRule"), "auto")
    spacing.set(q("after"), str(after))
    paragraph_properties.append(spacing)


def _blank_reference(directory: Path) -> Path:
    """一份"正文只有字体字号、行距段距一个都没写"的参考文件（Word 文档的常见形态）。"""
    document = Document()
    document.styles["Normal"].font.name = "Times New Roman"
    document.styles["Normal"].font.size = Pt(11)
    document.add_paragraph("正文样本。")
    _strip_spacing(document)
    path = directory / "reference.docx"
    document.save(path)
    return path


def _draft_line(draft: str, prefix: str) -> str:
    for line in draft.splitlines():
        if line.startswith(prefix):
            return line
    raise AssertionError(f"草稿里没有以「{prefix}」开头的行：\n{draft}")


def test_doc_defaults_paragraph_properties_are_read(tmp_path):
    """docDefaults 里写的行距与段后，必须读出来（这是 Word 与 python-docx 的默认写法）。"""
    document = Document()
    document.styles["Normal"].font.name = "Times New Roman"
    document.styles["Normal"].font.size = Pt(11)
    document.add_paragraph("正文样本。")
    _strip_spacing(document)
    _set_doc_defaults_spacing(document, line=360, after=240)   # 1.5 倍 / 段后 12 磅
    path = tmp_path / "reference.docx"
    document.save(path)

    clauses, doubt, _ = clauses_for(Ref(path, "zh"), "normal")
    assert "行距1.5倍" in clauses, clauses
    assert "段前0磅" in clauses, clauses
    assert "段后12磅" in clauses, clauses
    # rPr 那个桶没有回归：字号仍从 docDefaults 读得到
    assert "11pt" in clauses, clauses
    assert not any("单倍" in note for note in doubt), doubt


def test_style_level_spacing_wins_over_doc_defaults(tmp_path):
    """样式自己写了行距时，docDefaults 不能盖过它。"""
    document = Document()
    document.styles["Normal"].font.name = "Times New Roman"
    document.styles["Normal"].font.size = Pt(11)
    _strip_spacing(document)
    _set_doc_defaults_spacing(document, line=360, after=240)   # docDefaults：1.5 倍
    normal = _style_of(document, "Normal")
    paragraph_properties = normal.makeelement(q("pPr"), {})
    spacing = normal.makeelement(q("spacing"), {q("line"): "240", q("lineRule"): "auto"})
    paragraph_properties.append(spacing)
    normal.append(paragraph_properties)
    path = tmp_path / "reference.docx"
    document.save(path)

    clauses, _, _ = clauses_for(Ref(path, "zh"), "normal")
    assert "行距1倍" in clauses, clauses


def test_missing_spacing_keeps_required_fields(tmp_path):
    """整条链都没有 spacing 时，段前段后写 0 —— 缺字段的草稿生成不出模板。"""
    reference = _blank_reference(tmp_path)

    draft, _, _ = _build_draft(Ref(reference, "zh"), "zh")
    line = _draft_line(draft, "普通：")
    assert "段前0磅" in line and "段后0磅" in line, line


def test_draft_without_any_spacing_generates_a_template(tmp_path):
    """一份哪儿都没写行距的参考文件，读出的草稿仍要能直接生成模板。"""
    with_spacing = tmp_path / "with-spacing.docx"
    build_template(PRESET, with_spacing)

    # 把正规模的每一处 spacing 撤掉，模拟"行距全靠 Word 默认"的参考文件
    stripped = tmp_path / "stripped.docx"
    _rewrite_part(with_spacing, stripped, "word/styles.xml",
                  lambda text: re.sub(r"<w:spacing[^/]*/>", "", text))

    draft, _, _ = _build_draft(Ref(stripped, "zh"), "zh")
    for prefix in ("正文：", "一级标题："):
        line = _draft_line(draft, prefix)
        assert "段前0磅" in line and "段后0磅" in line, line
    # 不抛 TemplateError = 每条样式行都写全了必填字段
    build_template(draft, tmp_path / "out.docx")


def _rewrite_part(source: Path, target: Path, part: str, transform) -> None:
    shutil.copy(source, target)
    with zipfile.ZipFile(source) as archive:
        raw = archive.read(part).decode("utf-8")
    names = zipfile.ZipFile(source).namelist()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            data = (transform(raw).encode("utf-8") if name == part
                    else zipfile.ZipFile(source).read(name))
            archive.writestr(name, data)


def test_table_style_follows_based_on(tmp_path):
    """派生表样式（basedOn 基础三线样式，自己不写边框）也要读得出边框。"""
    document = Document()
    styles = document.styles.element
    base = styles.makeelement(q("style"), {})
    base.set(q("type"), "table")
    base.set(q("styleId"), "BaseThreeLine")
    base.append(base.makeelement(q("name"), {q("val"): "Base Three Line"}))
    table_properties = base.makeelement(q("tblPr"), {})
    borders = base.makeelement(q("tblBorders"), {})
    for side in ("top", "bottom"):
        borders.append(base.makeelement(q(side), {q("val"): "single", q("sz"): "12"}))
    table_properties.append(borders)
    base.append(table_properties)
    styles.append(base)

    derived = styles.makeelement(q("style"), {})
    derived.set(q("type"), "table")
    derived.set(q("styleId"), "Table")
    derived.append(derived.makeelement(q("name"), {q("val"): "Table"}))
    derived.append(derived.makeelement(q("basedOn"), {q("val"): "BaseThreeLine"}))
    styles.append(derived)
    path = tmp_path / "reference.docx"
    document.save(path)

    lines, doubt = read_table(Ref(path, "zh"))
    joined = " ".join(lines)
    assert "三线表" in joined, (lines, doubt)
    assert "线宽上1.5磅" in joined and "线宽底1.5磅" in joined, joined
    assert not any("边框" in note for note in doubt), doubt
