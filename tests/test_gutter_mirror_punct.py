"""tests/test_gutter_mirror_punct.py — 装订线、对称页边距、标点压缩、繁中字型识别与对账端到端回归测试。"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest
from docx import Document as open_docx
from docx.shared import Cm, Emu
from lxml import etree

from md_to_word.audit.inspector import audit
from md_to_word.model.reader import read_markdown
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.spec.constants import NS_W, TWIPS_PER_CM
from md_to_word.spec.parser import parse_format
from md_to_word.template.builder import build_template
from md_to_word.template.extractor import _auto_lang, extract_spec_from_docx
from md_to_word.validator.check import content_width_cm
from md_to_word.writer.docx_writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESETS = REPO_ROOT / "presets"
W = f"{{{NS_W}}}"


def test_native_gutter_and_mirror_margins_xml_and_clamping(tmp_path: Path) -> None:
    """原生装订线写入 pgMar/@w:gutter、左边距保持原值、settings.xml 中 mirrorMargins 位于 defaultTabStop 之前；
    点线制表位、图片钳宽与校验器版心计算均减去装订线。
    """
    base = (PRESETS / "zh-tw-academic.txt").read_text(encoding="utf-8")
    fmt_text = (
        base.rstrip()
        + "\n装订线：1.5cm\n对称页边距：开\n目录一级：PMingLiU/Times New Roman 小四 加粗 不倾斜 左对齐 行距1.5倍 段前0磅 段后0磅 首行缩进0字符 点线制表位\n"
    )
    # 替换已有目录一级避免重复定义
    lines = [
        "目录一级：PMingLiU/Times New Roman 小四 加粗 不倾斜 左对齐 行距1.5倍 段前0磅 段后0磅 首行缩进0字符 点线制表位"
        if line.startswith("目录一级：")
        else line
        for line in (base.rstrip() + "\n装订线：1.5cm\n对称页边距：开\n").splitlines()
    ]
    fmt_text = "\n".join(lines) + "\n"
    spec = parse_format(fmt_text)
    assert content_width_cm(spec) == pytest.approx(21.0 - 3.18 - 3.18 - 1.5, abs=0.01)

    tpl_path = tmp_path / "tpl.docx"
    build_template(fmt_text, tpl_path)

    with zipfile.ZipFile(tpl_path) as z:
        doc_root = etree.fromstring(z.read("word/document.xml"))
        settings_root = etree.fromstring(z.read("word/settings.xml"))
        styles_root = etree.fromstring(z.read("word/styles.xml"))

    pgmar = doc_root.find(f".//{W}sectPr/{W}pgMar")
    assert pgmar is not None
    # 左边距保持 3.18cm，不能把装订线混加进 w:left
    assert int(pgmar.get(f"{W}left")) == Cm(3.18).twips
    assert int(pgmar.get(f"{W}gutter")) == Cm(1.5).twips

    # mirrorMargins 必须在 defaultTabStop 之前（OOXML schema 顺序）
    setting_tags = [etree.QName(el).localname for el in settings_root]
    assert "mirrorMargins" in setting_tags
    if "defaultTabStop" in setting_tags:
        assert setting_tags.index("mirrorMargins") < setting_tags.index("defaultTabStop")

    # 标点压缩在 zh-tw-academic 为 doNotCompress
    csc = settings_root.find(f"{W}characterSpacingControl")
    assert csc is not None and csc.get(f"{W}val") == "doNotCompress"

    # 点线制表位位置 = A4 宽 - 左 - 右 - 装订线
    toc1 = next(s for s in styles_root.findall(f"{W}style") if s.get(f"{W}styleId") == "TOC1")
    tab = toc1.find(f".//{W}tabs/{W}tab")
    expected_twips = int(round((21.0 - 3.18 - 3.18 - 1.5) * TWIPS_PER_CM))
    assert tab is not None and abs(int(tab.get(f"{W}pos")) - expected_twips) <= 2

    # 写出器钳宽：超宽图片必须钳在减去装订线之后的版心内
    pic = REPO_ROOT / "demo" / "01_chinese_thesis" / "figures" / "qa_pipeline.png"
    shutil.copy(pic, tmp_path / "pic.png")
    md_text = "# 緒論\n\n測試正文。\n\n![](pic.png){width=20cm}\n\n%% 图片题注 圖 1 測試\n"
    out_docx = write_docx(read_markdown(md_text), tpl_path, tmp_path / "out.docx", base_dir=tmp_path)
    out_doc = open_docx(out_docx)
    sect = out_doc.sections[0]
    limit_cm = Emu(sect.page_width - sect.left_margin - sect.right_margin - sect.gutter).cm
    assert limit_cm == pytest.approx(21.0 - 3.18 - 3.18 - 1.5, abs=0.02)
    assert out_doc.inline_shapes[0].width.cm == pytest.approx(limit_cm, abs=0.02)


def test_extractor_round_trips_tc_settings_and_detects_tc_auto_lang(tmp_path: Path) -> None:
    """extractor 正确反推 装订线 / 对称页边距 / 标点压缩，且在无 w:lang 时仍把繁中字型识别为 zh。"""
    fmt_text = (PRESETS / "zh-tw-academic.txt").read_text(encoding="utf-8").rstrip() + (
        "\n装订线：1cm\n对称页边距：开\n"
    )
    tpl_path = tmp_path / "tw_tpl.docx"
    build_template(fmt_text, tpl_path)

    draft = extract_spec_from_docx(tpl_path)
    assert "装订线：1cm" in draft
    assert "对称页边距：开" in draft
    assert "校对语言：zh-TW" in draft
    assert "标点压缩：不压缩" in draft

    # 剥离 word/styles.xml 里的 <w:lang>，模拟未标注校对语言的第三方繁体 Word 模板
    stripped_path = tmp_path / "tw_no_lang.docx"
    with zipfile.ZipFile(tpl_path, "r") as zin, zipfile.ZipFile(stripped_path, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/styles.xml":
                root = etree.fromstring(data)
                for lang_el in list(root.iter(f"{W}lang")):
                    lang_el.getparent().remove(lang_el)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            zout.writestr(item, data)

    assert _auto_lang(stripped_path) == "zh"


def _mutate_docx_part(src: Path, dst: Path, member: str, mutator) -> Path:
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == member:
                root = etree.fromstring(data)
                mutator(root)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            zout.writestr(item, data)
    return dst


def test_inspector_catches_gutter_mirror_punctuation_and_alignment_regressions(tmp_path: Path) -> None:
    """导出对账（inspector）必须通过正常繁中稿件，并准确捕获装订线、对称页边距、标点压缩与段落对齐偏差。"""
    fmt_path = tmp_path / "format.txt"
    fmt_path.write_text(
        (PRESETS / "zh-tw-academic.txt").read_text(encoding="utf-8").rstrip()
        + "\n装订线：1cm\n对称页边距：开\n",
        encoding="utf-8",
    )
    md_path = tmp_path / "paper.md"
    md_path.write_text(
        "# 第一章 緒論\n\n繁體中文「測試」段落，數值為 98.6%。\n",
        encoding="utf-8",
    )
    out_docx = tmp_path / "out.docx"
    result = run_export_pipeline(
        ExportOptions(input_path=md_path, output_path=out_docx, format_path=fmt_path)
    )
    assert result.returncode == 0, result.errors
    assert audit(out_docx, fmt_path, lang="zh") == []

    # 1. 装订线被改成 0
    bad_gutter = _mutate_docx_part(
        out_docx,
        tmp_path / "bad_gutter.docx",
        "word/document.xml",
        lambda r: r.find(f".//{W}sectPr/{W}pgMar").set(f"{W}gutter", "0"),
    )
    assert any(cat == "装订线" for cat, _ in audit(bad_gutter, fmt_path, lang="zh"))

    # 2. 对称页边距被删除
    def drop_mirror(root):
        el = root.find(f"{W}mirrorMargins")
        if el is not None:
            root.remove(el)

    bad_mirror = _mutate_docx_part(out_docx, tmp_path / "bad_mirror.docx", "word/settings.xml", drop_mirror)
    assert any(cat == "对称页边距" for cat, _ in audit(bad_mirror, fmt_path, lang="zh"))

    # 3. 标点压缩被错误改成 compressPunctuation（破坏 zh-TW 默认）
    bad_csc = _mutate_docx_part(
        out_docx,
        tmp_path / "bad_csc.docx",
        "word/settings.xml",
        lambda r: r.find(f"{W}characterSpacingControl").set(f"{W}val", "compressPunctuation"),
    )
    assert any(cat == "标点压缩" for cat, _ in audit(bad_csc, fmt_path, lang="zh"))

    # 4. 段落对齐回归（覆盖 inspector 曾因误查 ALIGN_VAL 而静默失效的 bug）：Heading 1 居中被改成左对齐
    def break_heading_align(root):
        for st in root.findall(f"{W}style"):
            if st.get(f"{W}styleId") == "Heading1":
                st.find(f"{W}pPr/{W}jc").set(f"{W}val", "left")

    bad_align = _mutate_docx_part(out_docx, tmp_path / "bad_align.docx", "word/styles.xml", break_heading_align)
    assert any(cat == "对齐" for cat, _ in audit(bad_align, fmt_path, lang="zh"))


def test_traditional_chinese_bibliography_and_appendix_headings(tmp_path: Path) -> None:
    """繁体正文的 `# 參考文獻` 與 `# 附錄 A` 應正確觸發書目落位與附錄編號重算。"""
    (tmp_path / "refs.bib").write_text(
        "@article{chen2025, author={Chen, Yi}, title={TC Study}, journal={J}, year={2025}}\n",
        encoding="utf-8",
    )
    (tmp_path / "paper.md").write_text(
        "---\n"
        "bibliography: refs.bib\n"
        "csl: apa.csl\n"
        "crossref:\n"
        "  chapters: true\n"
        "---\n\n"
        "# 第一章 緒論\n\n"
        "正文引用 [@chen2025] 與式（@eq-a）。\n\n"
        "$$\n"
        "x = 1\n"
        "$$ {#eq-a}\n\n"
        "# 參考文獻\n\n"
        "# 附錄 A 補充推導\n\n"
        "附錄公式見 @eq-app。\n\n"
        "$$\n"
        "y = 2\n"
        "$$ {#eq-app}\n",
        encoding="utf-8",
    )
    out_docx = tmp_path / "out.docx"
    res = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "paper.md", output_path=out_docx, preset="zh-tw-academic")
    )
    assert res.returncode == 0, res.errors
    assert not any("参考文献标题" in m for m in res.warnings), res.warnings

    paras = [p.text for p in open_docx(out_docx).paragraphs if p.text.strip()]
    ref_i = next(i for i, p in enumerate(paras) if "參考文獻" in p)
    bib_i = next(i for i, p in enumerate(paras) if "TC Study" in p)
    app_i = next(i for i, p in enumerate(paras) if "附錄 A" in p)
    assert ref_i < bib_i < app_i
    # 附錄 A 的公式編號應為 A-1 而非 2-1
    assert any("A-1" in p for p in paras), paras

