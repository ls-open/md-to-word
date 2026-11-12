"""目录/页眉联动必填、解析前置检查、对账、反推与单条 `{.unlisted}`/`{不入目录}` 全链路测试。"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from md_to_word.audit.inspector import audit
from md_to_word.model.reader import read_markdown
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.spec.parser import parse_format
from md_to_word.template.builder import build_template
from md_to_word.template.extractor import extract_spec_from_docx
from md_to_word.template.generator import (
    TemplateError,
    read_header_styles_meta,
    write_header_styles_meta,
)
from md_to_word.utils.skill_utils import dialect_issues, heading_issues
from md_to_word.validator.check import validate_manuscript
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
ZH_ACADEMIC = (REPO_ROOT / "presets" / "zh-academic.txt").read_text(encoding="utf-8")
ZH_REPORT = (REPO_ROOT / "presets" / "zh-report.txt").read_text(encoding="utf-8")
EN_NATURE = (REPO_ROOT / "presets" / "en-nature.txt").read_text(encoding="utf-8")


def _strip_clauses(line: str) -> str:
    for kw in ("不入目录", "加入目录", "不入页眉", "加入页眉", "no-toc", "join-toc", "no-header", "join-header"):
        line = line.replace(f" {kw}", "")
    return line


def _without_linkage(spec_text: str) -> str:
    return "\n".join(
        _strip_clauses(line)
        if line.startswith(("摘要标题：", "参考文献标题：", "Abstract Title:", "References Title:"))
        else line
        for line in spec_text.splitlines()
    ) + "\n"


# 1. 零负担原则：未用目录与 STYLEREF 的文档，无需写任何目录/页眉开关
def test_plain_report_without_toc_or_styleref_needs_no_linkage_clauses(tmp_path: Path) -> None:
    fmt = tmp_path / "format.txt"
    fmt.write_text(ZH_REPORT, encoding="utf-8")
    md = tmp_path / "report.md"
    md.write_text("%% 文档标题 测试报告\n\n%% 摘要标题 摘要\n\n%% 摘要 内容。\n\n# 第一节\n\n正文。\n", encoding="utf-8")
    res = run_export_pipeline(
        ExportOptions(input_path=md, output_path=tmp_path / "out.docx", format_path=fmt)
    )
    assert res.returncode == 0, res.errors
    assert read_header_styles_meta(tmp_path / "out.docx") == set()


# 2. 联动必填报错（中英文 + CLI/pipeline res.errors）
def test_linkage_omission_fails_with_actionable_zh_and_en_errors(tmp_path: Path) -> None:
    # 2a) 中文有目录样式但省略加入目录/不入目录
    zh_fmt = tmp_path / "zh_fmt.txt"
    zh_fmt.write_text(_without_linkage(ZH_ACADEMIC), encoding="utf-8")
    zh_md = tmp_path / "zh.md"
    zh_md.write_text("%% 文档标题 测试\n\n# 引言\n\n正文。\n", encoding="utf-8")
    res_zh = run_export_pipeline(
        ExportOptions(input_path=zh_md, output_path=tmp_path / "zh.docx", format_path=zh_fmt)
    )
    assert res_zh.returncode != 0
    err_zh = "\n".join(res_zh.errors)
    assert "Abstract Title" in err_zh and "References Title" in err_zh
    assert "加入目录" in err_zh and "不入目录" in err_zh

    # 2b) 英文有 TOC 样式但省略 join-toc/no-toc，且加了 {styleref:Heading 1} 省略 join-header/no-header
    en_base = _without_linkage(EN_NATURE)
    en_fmt = tmp_path / "en_fmt.txt"
    en_fmt.write_text(
        en_base
        + "\nHeader: Times New Roman 9pt not-bold not-italic center line-spacing 1.0 "
        "space-before 0pt space-after 0pt indent 0\n"
        + "Header Content: {style-title:Heading 1}\n",
        encoding="utf-8",
    )
    en_md = tmp_path / "en.md"
    en_md.write_text("# Introduction\n\nEnglish body.\n", encoding="utf-8")
    res_en = run_export_pipeline(
        ExportOptions(input_path=en_md, output_path=tmp_path / "en.docx", format_path=en_fmt)
    )
    assert res_en.returncode != 0
    err_en = "\n".join(res_en.errors)
    assert "join-toc" in err_en and "join-header" in err_en
    assert "Abstract Title" in err_en and "References Title" in err_en


# 3. 解析期前置条件拦阻
def test_parse_preconditions_reject_invalid_targets_and_conflicts() -> None:
    # Heading 1..6 不可挂加入目录/不入目录/加入页眉/不入页眉
    for clause in ("加入目录", "不入目录", "加入页眉", "不入页眉"):
        with pytest.raises(ValueError) as exc:
            parse_format(
                f"一级标题：黑体 三号 加粗 不倾斜 左对齐 行距1.5倍 段前0磅 段后0磅 首行缩进0字符 {clause}\n"
            )
        if clause in ("加入目录", "不入目录"):
            assert "{不入目录}" in str(exc.value) or "{.unlisted}" in str(exc.value)

    for clause in ("join-toc", "no-toc", "join-header", "no-header"):
        with pytest.raises(ValueError):
            parse_format(
                f"Heading 2: Times New Roman 12pt bold not-italic left line-spacing 1.5 "
                f"space-before 0pt space-after 0pt indent 0 {clause}\n"
            )

    # 正文/紧凑等非目录样式不可挂不入目录/加入页眉/不入页眉
    for clause in ("加入目录", "不入目录", "加入页眉", "不入页眉"):
        with pytest.raises(ValueError):
            parse_format(
                f"正文：宋体 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前0磅 段后0磅 首行缩进2字符 {clause}\n"
            )

    # no-toc + join-header 互斥（中英文）
    with pytest.raises(ValueError, match="不入目录.*加入页眉"):
        parse_format(
            "摘要标题：黑体 四号 加粗 不倾斜 居中 行距1.5倍 段前0磅 段后0磅 首行缩进0字符 不入目录 加入页眉\n"
        )
    with pytest.raises(ValueError, match="no-toc.*join-header"):
        parse_format(
            "References Title: Times New Roman 14pt bold not-italic left line-spacing 1.5 "
            "space-before 12pt space-after 6pt indent 0 no-toc join-header\n"
        )


# 4. 对账 Inspector：meta 篡改、未升级段落检测、无该段时不误报
def test_inspector_audits_join_header_meta_and_paragraph_promotion(tmp_path: Path) -> None:
    fmt_path = tmp_path / "format.txt"
    fmt_path.write_text(ZH_ACADEMIC, encoding="utf-8")
    tpl_path = tmp_path / "tpl.docx"
    build_template(ZH_ACADEMIC, tpl_path)

    # 4a) 稿件根本没有参考文献标题段落（例如全篇只有正文），不得误报
    doc_no_refs = write_docx(
        read_markdown("%% 文档标题 标题\n\n# 第一章\n\n正文。\n"),
        tpl_path,
        tmp_path / "no_refs.docx",
    )
    assert audit(doc_no_refs, fmt_path, lang="zh") == []

    # 4b) 稿件有参考文献标题段落，正常升级通过
    doc_ok = write_docx(
        read_markdown("%% 文档标题 标题\n\n# 第一章\n\n正文。\n\n%% 参考文献标题 参考文献\n"),
        tpl_path,
        tmp_path / "ok.docx",
    )
    assert audit(doc_ok, fmt_path, lang="zh") == []

    # 4c) 篡改 /customXml/mdw_meta.xml 为 [] -> 对账必须报元数据不符
    from docx import Document

    bad_meta = tmp_path / "bad_meta.docx"
    d = Document(doc_ok)
    write_header_styles_meta(d, set())
    d.save(bad_meta)
    probs_meta = audit(bad_meta, fmt_path, lang="zh")
    assert any(cat == "页眉联动" and "mdw_meta.xml" not in msg for cat, msg in probs_meta) or any(
        cat == "页眉联动" and "References Title" in msg for cat, msg in probs_meta
    ), probs_meta

    # 4d) document.xml 里若段落还保留 ReferencesTitle（未升级为 Heading1），对账必须抓出来
    unpromoted = tmp_path / "unpromoted.docx"
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    w = f"{{{ns_w}}}"
    with zipfile.ZipFile(doc_ok, "r") as zin, zipfile.ZipFile(unpromoted, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                root = etree.fromstring(data)
                for p in root.findall(f".//{w}p"):
                    txt = "".join(t.text or "" for t in p.findall(f".//{w}t"))
                    if "参考文献" in txt:
                        ps = p.find(f"{w}pPr/{w}pStyle")
                        assert ps is not None
                        ps.set(f"{w}val", "ReferencesTitle")
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            zout.writestr(item, data)
    probs_unp = audit(unpromoted, fmt_path, lang="zh")
    assert any(cat == "页眉联动" and "References Title" in msg for cat, msg in probs_unp), probs_unp


# 5. Extractor 往返与第三方参考模板保守推断
@pytest.mark.parametrize("preset_text", [ZH_ACADEMIC, EN_NATURE, ZH_REPORT])
def test_extractor_round_trips_presets_with_valid_drafts(tmp_path: Path, preset_text: str) -> None:
    tpl = tmp_path / "tpl.docx"
    build_template(preset_text, tpl)
    draft = extract_spec_from_docx(tpl)
    # 抽出的草稿可直接解析并重新生成模板，不再因联动缺失挂掉
    parse_format(draft)
    build_template(draft, tmp_path / "rebuilt.docx")


def test_extractor_third_party_docx_without_meta_marks_header_unverified(tmp_path: Path) -> None:
    """无 mdw_meta.xml 的第三方含 STYLEREF 参考文档：保守写不入页眉并列待确认提示。"""
    with_hdr = (
        ZH_ACADEMIC.rstrip()
        + "\n页眉：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符\n"
        + "页眉内容：{样式标题:Heading 1}\n"
    )
    tpl = tmp_path / "tpl.docx"
    build_template(with_hdr, tpl)

    # 剥离 customXml/mdw_meta.xml 模拟第三方机构模板
    third_party = tmp_path / "third_party.docx"
    with zipfile.ZipFile(tpl, "r") as zin, zipfile.ZipFile(third_party, "w") as zout:
        for item in zin.infolist():
            if item.filename == "customXml/mdw_meta.xml":
                continue
            zout.writestr(item, zin.read(item.filename))

    draft = extract_spec_from_docx(third_party)
    assert "参考文献标题：" in draft
    # 因缺少 mdw_meta.xml 佐证，对参考文献标题保守输出 不入页眉
    ref_line = next(l for l in draft.splitlines() if l.startswith("参考文献标题："))
    assert "不入页眉" in ref_line
    assert "加入页眉" in draft and "不入页眉" in draft  # 待确认提示中列出需核对
    # 但草稿仍合法且能直接 build
    build_template(draft, tmp_path / "rebuilt.docx")


# 6. 单条标题退出目录：`{.unlisted}` 与 `{不入目录}`
def test_unlisted_heading_creates_unlisted_style_and_keeps_numbering(tmp_path: Path) -> None:
    md_text = (
        "---\n"
        "bibliography: refs.bib\n"
        "crossref:\n"
        "  chapters: true\n"
        "---\n\n"
        "%% 文档标题 测试论文\n\n"
        "{{< toc 2 >}}\n\n"
        "# 第一章 绪论\n\n"
        "见 @eq-main 與 @eq-app。\n\n"
        "$$a = b$$ {#eq-main}\n\n"
        "# 附录 A 补充推导\n\n"
        "$$c = d$$ {#eq-app}\n\n"
        "# 致谢 {不入目录}\n\n"
        "## 个人致谢 {.unlisted}\n\n"
        "感谢支持。\n\n"
        "# 参考文献 {.unlisted}\n"
    )
    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{k1, author={Zhang, San}, title={Paper}, journal={J}, year={2024}}\n",
        encoding="utf-8",
    )
    md_text = md_text.replace("感谢支持。", "感谢支持 [@k1]。")

    md_path = tmp_path / "paper.md"
    md_path.write_text(md_text, encoding="utf-8")

    # 6a) 语法工具类不得误伤合法 {.unlisted}/{不入目录}，同时必须继续抓非法用法
    assert heading_issues(md_text) == []
    assert dialect_issues(md_text) == []
    empty_en = dialect_issues("# {.unlisted}\n", lang="en")
    assert len(empty_en) == 1 and "no text" in empty_en[0][1].lower(), empty_en
    empty_zh = dialect_issues("## {不入目录}\n", lang="zh")
    assert len(empty_zh) == 1 and "没有文字" in empty_zh[0][1], empty_zh
    span_prose = dialect_issues("正文 [文字]{.unlisted} 测试。\n", lang="zh")
    assert len(span_prose) == 1 and (
        "underline" in span_prose[0][1].lower() or "属性" in span_prose[0][1]
    ), span_prose

    # 6b) 加上 Heading 1 带颜色与段前缩进等视觉继承，验证 UnlistedHeading1 完整拷贝
    spec_text = (
        ZH_ACADEMIC.replace(
            "一级标题：黑体/Times New Roman 三号 加粗 不倾斜 居中 行距1.5倍 段前18磅 段后12磅 首行缩进0字符 与下段同页",
            "一级标题：黑体/Times New Roman 三号 加粗 不倾斜 居中 颜色#1F4E79 行距1.5倍 段前18磅 段后12磅 首行缩进0字符 与下段同页",
        ).rstrip()
        + "\n页眉：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符\n"
        + "页眉内容：{样式标题:Heading 1}\n"
    )
    fmt_path = tmp_path / "format.txt"
    fmt_path.write_text(spec_text, encoding="utf-8")

    # 预检对搭配动态样式标题页眉的 unlisted 标题给出非阻断提醒（valid 仍为 True）
    report = validate_manuscript(md_path, spec=parse_format(spec_text), lang="zh")
    assert report.valid
    assert any("动态样式标题" in w for w in report.warnings), report.warnings

    out_docx = tmp_path / "out.docx"
    res = run_export_pipeline(
        ExportOptions(input_path=md_path, output_path=out_docx, format_path=fmt_path)
    )
    assert res.returncode == 0, res.errors
    assert any("动态样式标题" in w for w in res.warnings), res.warnings

    with zipfile.ZipFile(out_docx) as z:
        styles_xml = z.read("word/styles.xml").decode("utf-8")
        doc_xml = z.read("word/document.xml").decode("utf-8")

    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    w = f"{{{ns_w}}}"
    sroot = etree.fromstring(styles_xml.encode("utf-8"))
    for st_id, expected_sz in (("UnlistedHeading1", "32"), ("UnlistedHeading2", "28")):
        unlisted_st = next(
            (s for s in sroot.findall(f"{w}style") if s.get(f"{w}styleId") == st_id),
            None,
        )
        assert unlisted_st is not None, f"应生成 {st_id} 样式"
        based_on = unlisted_st.find(f"{w}basedOn")
        assert based_on is not None and based_on.get(f"{w}val") == "Normal"
        ol = unlisted_st.find(f"{w}pPr/{w}outlineLvl")
        assert ol is not None and ol.get(f"{w}val") == "9"
        sz = unlisted_st.find(f"{w}rPr/{w}sz")
        assert sz is not None and sz.get(f"{w}val") == expected_sz

    unlisted_h1 = next(s for s in sroot.findall(f"{w}style") if s.get(f"{w}styleId") == "UnlistedHeading1")
    color_el = unlisted_h1.find(f"{w}rPr/{w}color")
    assert color_el is not None and color_el.get(f"{w}val") == "1F4E79"

    # 致谢与参考文献段落都落入 UnlistedHeading1，个人致谢落入 UnlistedHeading2，且文末已插入文献条目
    droot = etree.fromstring(doc_xml.encode("utf-8"))
    paras = droot.findall(f".//{w}p")
    para_texts = ["".join(t.text or "" for t in p.findall(f".//{w}t")) for p in paras]
    ack_p = next(p for p, t in zip(paras, para_texts) if t == "致谢")
    sub_ack_p = next(p for p, t in zip(paras, para_texts) if t == "个人致谢")
    ref_p = next(p for p, t in zip(paras, para_texts) if t == "参考文献")
    assert ack_p.find(f"{w}pPr/{w}pStyle").get(f"{w}val") == "UnlistedHeading1"
    assert sub_ack_p.find(f"{w}pPr/{w}pStyle").get(f"{w}val") == "UnlistedHeading2"
    assert ref_p.find(f"{w}pPr/{w}pStyle").get(f"{w}val") == "UnlistedHeading1"
    # 文献条目（Bibliography 样式）确实跟在 `# 参考文献 {.unlisted}` 后插入了
    bib_paras = [
        p for p in paras
        if p.find(f"{w}pPr/{w}pStyle") is not None
        and p.find(f"{w}pPr/{w}pStyle").get(f"{w}val") == "Bibliography"
    ]
    assert bib_paras and any("Paper" in "".join(t.text or "" for t in p.findall(f".//{w}t")) for p in bib_paras)
    # 章节/附录按章公式编号未被打乱
    full_text = "\n".join(para_texts)
    assert "（1-1）" in full_text
    assert "（A-1）" in full_text
