"""Unit and integration tests for md_to_word.pipeline."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from md_to_word.pipeline import ExportOptions, run_export_pipeline


def test_pipeline_export_zh_academic(tmp_path: Path):
    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    for name in ("manuscript.md", "refs.bib"):
        shutil.copy(fixture_dir / name, tmp_path / name)

    output = tmp_path / "output_zh.docx"
    options = ExportOptions(
        input_path=tmp_path / "manuscript.md",
        output_path=output,
        preset="zh-academic",
    )
    result = run_export_pipeline(options)
    assert result.returncode == 0, f"Errors: {result.errors}"
    assert output.exists()
    assert output.stat().st_size > 5000


def test_pipeline_export_en_nature(tmp_path: Path):
    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    for name in ("manuscript.md", "refs.bib"):
        shutil.copy(fixture_dir / name, tmp_path / name)

    output = tmp_path / "output_en.docx"
    options = ExportOptions(
        input_path=tmp_path / "manuscript.md",
        output_path=output,
        preset="en-nature",
    )
    result = run_export_pipeline(options)
    assert result.returncode == 0, f"Errors: {result.errors}"
    assert output.exists()
    assert output.stat().st_size > 5000


def test_pipeline_fails_on_invalid_manuscript(tmp_path: Path):
    bad_md = tmp_path / "bad.md"
    bad_md.write_text("""---
title: Broken
---

## 1. Wrong heading level
![](missing_image.png)
""", encoding="utf-8")

    output = tmp_path / "bad.docx"
    options = ExportOptions(
        input_path=bad_md,
        output_path=output,
        preset="zh-academic",
    )
    result = run_export_pipeline(options)
    assert result.returncode == 1
    # 稿件是英文，门禁也按英文报（`--preset zh-academic` 只决定版式，不决定消息语言）
    assert any("image file not found" in e for e in result.errors)


def _write_bib(directory: Path) -> None:
    (directory / "refs.bib").write_text(
        "@article{smith2024,\n  author={Smith, John},\n  title={A Study},\n"
        "  year={2024},\n  journal={Journal of Tests}\n}\n",
        encoding="utf-8",
    )


def _paragraph_texts(docx_path: Path) -> list[str]:
    from docx import Document

    return [p.text for p in Document(docx_path).paragraphs]


def test_default_csl_is_shared_by_both_writers(tmp_path: Path) -> None:
    """稿件没写 `csl:` 时，两条通道必须用同一个默认样式。

    否则同一份稿子换个后端就换出两种文献表——作者只会觉得"怎么又变了"。
    """
    _write_bib(tmp_path)
    (tmp_path / "m.md").write_text(
        '---\nbibliography: refs.bib\n---\n\n# 一 引言\n\n'
        "中文正文引用一次 [@smith2024] 即可。\n",
        encoding="utf-8",
    )
    native = tmp_path / "native.docx"
    result = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "m.md", output_path=native, check_md=False)
    )
    assert result.returncode == 0, result.errors
    text = "\n".join(_paragraph_texts(native))
    assert "[1]" in text, "中文稿未写 csl: 时应走 GB/T 数字制"
    assert "Smith, John. (2024)" not in text, "不该走作者-年份制"


def test_default_csl_follows_language(tmp_path: Path) -> None:
    """英文稿不写 `csl:` 走 APA：同一个机制，按字种选样式。"""
    from md_to_word.config import default_csl_path

    assert default_csl_path("这是一份中文稿件。" * 20).name == "chinese-gb7714-2015-numeric.csl"
    assert default_csl_path("This is an English manuscript. " * 20).name == "apa.csl"


def test_export_reminds_to_open_the_result(tmp_path: Path) -> None:
    """门禁全绿不等于版面合格。行高列宽、公式与题注的落版只能目视核对，
    因此每次成功导出都必须附一条核对提醒，使其成为交付流程的一环。

    措辞只给一句整体提醒，不列举该看哪里：逐项列举既啰嗦，又会让「看过了」变成
    「按清单看过、清单外没看」——真要看的是整份版面。"""
    (tmp_path / "m.md").write_text('---\n---\n\n# 一 引言\n\n正文。\n', encoding="utf-8")
    result = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "m.md", output_path=tmp_path / "o.docx", preset="zh-academic")
    )
    assert result.returncode == 0, result.errors
    assert any("版面仍须在 Word 中人工核验" in m for m in result.messages), result.messages


def test_image_paths_are_relative_to_the_manuscript(tmp_path: Path, monkeypatch) -> None:
    """稿里的图片路径相对稿件目录，不相对进程 cwd——否则换个目录调用就全是"图不存在"。"""
    work = tmp_path / "paper"
    (work / "figures").mkdir(parents=True)
    shutil.copy(
        Path(__file__).resolve().parents[1] / "demo/01_chinese_thesis/figures/qa_pipeline.png",
        work / "figures" / "x.png",
    )
    (work / "m.md").write_text(
        '---\n---\n\n![](figures/x.png){width=8cm}\n\n%% 图片题注 图 1 示意图\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)  # 站在别的目录调用
    result = run_export_pipeline(
        ExportOptions(input_path=work / "m.md", output_path=work / "o.docx", preset="zh-academic")
    )
    assert result.returncode == 0, result.errors
    assert "drawing" in __import__("zipfile").ZipFile(work / "o.docx").read("word/document.xml").decode()


def test_bad_format_returns_error_instead_of_exiting(tmp_path: Path) -> None:
    """作为库调用时，写错的格式文件必须返回错误码，不能 sys.exit 掉调用方的进程。"""
    (tmp_path / "m.md").write_text('---\n---\n\n# 一\n\n正文。\n', encoding="utf-8")
    (tmp_path / "req.txt").write_text("正文：宋体 小四\n", encoding="utf-8")

    try:
        result = run_export_pipeline(
            ExportOptions(input_path=tmp_path / "m.md", output_path=tmp_path / "o.docx",
                          format_path=tmp_path / "req.txt")
        )
    except SystemExit:  # pragma: no cover - 旧实现会走到这里
        pytest.fail("写错的格式文件不应终止进程，应返回 returncode=1")

    assert result.returncode == 1
    assert any("格式文件" in e for e in result.errors), result.errors


def test_user_csl_direct_formatting_is_stripped(tmp_path: Path) -> None:
    """用户自带的 CSL 里若有 hanging-indent 之类的直接格式，导出时要忽略它。

    直接格式的优先级高于样式：不剥，同一份 format.txt 换个 CSL，参考文献的
    悬挂缩进和行距就跟着变——「同一份稿件重跑一致」当场作废。
    """
    (tmp_path / "refs.bib").write_text(
        "@article{a2020, author={Doe, Jane}, title={A Paper}, journal={J}, year={2020}}\n",
        encoding="utf-8",
    )
    (tmp_path / "mine.csl").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<style xmlns="http://purl.org/net/xbiblio/csl" class="in-text" version="1.0">\n'
        "<info><title>Mine</title><id>http://example.com/mine</id></info>\n"
        "<citation><layout><text variable=\"title\"/></layout></citation>\n"
        '<bibliography hanging-indent="true" second-field-align="flush">\n'
        "<layout><text variable=\"title\"/></layout></bibliography></style>\n",
        encoding="utf-8",
    )
    (tmp_path / "m.md").write_text(
        "---\nbibliography: refs.bib\ncsl: mine.csl\n---\n\n# 一 引言\n\n见 [@a2020]。\n\n"
        "%% 参考文献标题 参考文献\n",
        encoding="utf-8",
    )

    result = run_export_pipeline(ExportOptions(input_path=tmp_path / "m.md", output_path=tmp_path / "o.docx"))
    assert result.returncode == 0, result.errors
    assert any("hanging-indent" in m for m in result.messages), result.messages


def test_default_preset_follows_the_manuscript_language(tmp_path: Path) -> None:
    """不给 -f 也不给 --preset 时，中文稿走 zh-academic、英文稿走 en-nature。

    英文稿套上中文学位论文的格式（首行缩进两字符 + 宋体 fallback）是错的，而这个错
    看不出来：文档能打开、样式都在，只是每段都被顶了两个字符。
    """
    import re
    import zipfile

    def body_text_style(docx: Path) -> str:
        with zipfile.ZipFile(docx) as archive:
            styles = archive.read("word/styles.xml").decode("utf-8")
        match = re.search(r'<w:style [^>]*w:styleId="BodyText".*?</w:style>', styles, re.S)
        assert match, "模板里没有 Body Text 样式"
        return match.group(0)

    (tmp_path / "en.md").write_text("# 1 Introduction\n\nEnglish body.\n", encoding="utf-8")
    en = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "en.md", output_path=tmp_path / "en.docx")
    )
    assert en.returncode == 0, en.errors
    assert any("en-nature" in m for m in en.messages), en.messages
    assert 'w:firstLineChars="0"' in body_text_style(tmp_path / "en.docx")

    (tmp_path / "zh.md").write_text("# 一 引言\n\n中文正文。\n", encoding="utf-8")
    zh = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "zh.md", output_path=tmp_path / "zh.docx")
    )
    assert zh.returncode == 0, zh.errors
    assert any("zh-academic" in m for m in zh.messages), zh.messages
    assert 'w:firstLineChars="200"' in body_text_style(tmp_path / "zh.docx")


def test_missing_output_directory_is_reported_not_raised(tmp_path: Path) -> None:
    """输出目录不存在时要给一句话，而不是等流水线跑完再抛 FileNotFoundError。

    对着 traceback 的人不会想到自己只是漏建了一个目录。
    """
    manuscript = tmp_path / "m.md"
    manuscript.write_text("# 引言\n\n正文。\n", encoding="utf-8")

    result = run_export_pipeline(
        ExportOptions(
            input_path=manuscript,
            output_path=tmp_path / "no_such_dir" / "out.docx",
            preset="zh-academic",
        )
    )

    assert result.returncode == 1
    assert any("输出目录不存在" in e for e in result.errors), result.errors
def test_template_reader_rejects_non_docx(tmp_path: Path) -> None:
    """把 .md 当成模板传进去时给一句话，而不是 BadZipFile 的 traceback。"""
    from md_to_word.template.extractor import main as extract_main

    not_docx = tmp_path / "notes.md"
    not_docx.write_text("# 引言\n", encoding="utf-8")

    assert extract_main([str(not_docx)]) == 1


def test_library_and_cli_reverse_engineer_identically(tmp_path: Path, capsys) -> None:
    """反推要求文件只有一份实现：库调用与命令行必须给出同一份草稿。

    从前 `main()` 与 `extract_spec_from_docx()` 各写了一遍，改一边另一边就悄悄落后；
    这条把它们钉在同一份输出上。
    """
    import io
    from contextlib import redirect_stdout

    from md_to_word.template import extract_spec_from_docx
    from md_to_word.template.extractor import main as extract_main

    source = tmp_path / "seed.docx"
    assert run_export_pipeline(
        ExportOptions(
            input_path=_write_manuscript(tmp_path),
            output_path=source,
            preset="zh-academic",
        )
    ).returncode == 0

    from_library = extract_spec_from_docx(source)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert extract_main([str(source)]) == 0
    from_cli = buffer.getvalue()

    assert from_cli == from_library


def _write_manuscript(tmp_path: Path) -> Path:
    manuscript = tmp_path / "seed.md"
    manuscript.write_text("%% 文档标题 题目\n\n# 一\n\n正文。\n", encoding="utf-8")
    return manuscript


def test_unpicked_txt_files_are_named(tmp_path: Path) -> None:
    """没传 -f 时只认 `format.txt`；旁边的 .txt 一概不猜，但要在提醒里点名。

    猜「唯一那个 .txt 大概是格式文件」看着贴心，实则是把笔记当格式用——静默用错格式，
    比直接不认它难查得多。不猜，但也不能装作没看见：用户以为它生效了才是真问题。
    """
    (tmp_path / "doc.md").write_text("# 引言\n\n正文。\n", encoding="utf-8")
    (tmp_path / "随手记.txt").write_text("这是笔记\n", encoding="utf-8")

    result = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "doc.md", output_path=tmp_path / "doc.docx")
    )

    assert result.returncode == 0, result.errors
    assert any("随手记.txt" in msg for msg in result.messages), result.messages
    assert any("格式文件" in msg for msg in result.messages), result.messages


def test_contract_cheatsheet_needs_no_manuscript(capsys) -> None:
    """只装了包、手上没有技能文档的调用方，要能自己问出稿件怎么写。"""
    from md_to_word.cli import main

    assert main(["--contract"]) == 0
    out = capsys.readouterr().out
    assert "%% 样式名" in out and "文档标题" in out and "@eq-" in out


def test_json_output_is_one_machine_readable_object(tmp_path: Path, capsys) -> None:
    """Agent 与脚本读键，不读措辞：stdout 只有一行 JSON，键名固定。"""
    import json

    from md_to_word.cli import main

    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    for name in ("manuscript.md", "refs.bib"):
        shutil.copy(fixture_dir / name, tmp_path / name)

    code = main([str(tmp_path / "manuscript.md"), "-o", str(tmp_path / "out.docx"), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == payload["returncode"] == 0
    assert payload["ok"] is True
    assert payload["output"].endswith("out.docx")
    assert payload["errors"] == []
    assert set(payload) == {"ok", "returncode", "input", "output", "pdf", "lang", "messages", "errors"}


def test_json_output_reports_a_missing_manuscript(tmp_path: Path, capsys) -> None:
    import json

    from md_to_word.cli import main

    code = main([str(tmp_path / "nope.md"), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == payload["returncode"] == 1
    assert payload["ok"] is False and payload["errors"]
    assert payload["output"] is None


def test_json_output_survives_an_internal_error(tmp_path: Path, capsys, monkeypatch) -> None:
    """没料到的异常也要留下一行 JSON：`--json` 是给程序读的契约，不能被 traceback 吞掉。"""
    import json

    import md_to_word.cli as cli

    def boom(_options):
        raise TypeError("模拟内部异常")

    monkeypatch.setattr(cli, "run_export_pipeline", boom)
    code = cli.main([str(tmp_path / "nope.md"), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == payload["returncode"] == 1
    assert payload["ok"] is False
    assert any("TypeError" in error for error in payload["errors"]), payload["errors"]
    assert "Traceback" in captured.err, "traceback 仍要留给维护者，不能静默"


def test_guide_is_readable_without_the_skill_directory(capsys) -> None:
    """只装了 pip 包的人也要能一条命令读到‘按什么顺序做’。"""
    from md_to_word.cli import main

    assert main(["--guide"]) == 0
    out = capsys.readouterr().out
    assert "Read this before the first run" in out and "## 1. The work, in order" in out


def test_guide_and_skill_entry_are_one_text() -> None:
    """技能用户读 SKILL.md、pip 用户读 guide.md，两份必须是同一份流程。"""
    root = Path(__file__).resolve().parents[1]
    body = (root / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2].lstrip("\n")
    assert (root / "src/md_to_word/resources/guide.md").read_text(encoding="utf-8") == body


def test_init_writes_an_exportable_pair(tmp_path: Path, capsys) -> None:
    """第一条命令就要能出成品：init 生成的稿件与格式声明必须直接导出成功。"""
    from md_to_word.cli import main

    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "format.txt").exists() and (tmp_path / "hello.md").exists()

    out = tmp_path / "hello.docx"
    assert main([str(tmp_path / "hello.md"), "-o", str(out)]) == 0
    assert out.exists()
    # 第一次导出不该有任何告警：样例本身必须是范本，不能一上手就「折行段落」。
    assert "⚠️" not in capsys.readouterr().err


def test_init_does_not_overwrite_and_speaks_the_chosen_language(tmp_path: Path, capsys) -> None:
    from md_to_word.cli import main

    assert main(["init", str(tmp_path), "--lang", "en"]) == 0
    assert "Created:" in capsys.readouterr().out
    assert (tmp_path / "hello.md").read_text(encoding="utf-8").startswith("%% Title")

    code = main(["init", str(tmp_path)])
    assert code == 1
    assert "未覆盖" in capsys.readouterr().out
    assert main(["init", str(tmp_path), "--force"]) == 0


def test_init_sample_follows_the_preset_not_the_message_language(tmp_path: Path, capsys) -> None:
    """格式词表是英文（Table Caption、Body Text），样例里也必须是英文样式名。"""
    from md_to_word.cli import main

    assert main(["init", str(tmp_path), "--preset", "en-nature"]) == 0
    assert (tmp_path / "hello.md").read_text(encoding="utf-8").startswith("%% Title")
    assert main([str(tmp_path / "hello.md"), "-o", str(tmp_path / "out.docx")]) == 0


def test_init_unknown_preset_is_reported(tmp_path: Path, capsys) -> None:
    from md_to_word.cli import main

    assert main(["init", str(tmp_path), "--preset", "nope"]) == 1
    assert "nope" in capsys.readouterr().out


def test_theme_attrs_are_stripped_for_fonts_colors_and_fills() -> None:
    """字体、颜色、底纹三类主题属性都要剥：`w:shd` 同时有 fill 与 themeFill 时以主题色为准。"""
    from md_to_word.utils.skill_utils import strip_theme_attrs_from_xml

    xml = (
        b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'<w:style w:styleId="a"><w:rPr><w:rFonts w:ascii="Times New Roman" w:asciiTheme="majorHAnsi"/>'
        b'<w:color w:val="000000" w:themeColor="text1" w:themeTint="99"/>'
        b'<w:shd w:fill="FFFFFF" w:themeFill="background1" w:themeFillTint="33"/></w:rPr></w:style>'
        b"</w:styles>"
    )
    cleaned = strip_theme_attrs_from_xml(xml).decode("utf-8")
    for attr in ("asciiTheme", "themeColor", "themeTint", "themeFill", "themeFillTint"):
        assert f"w:{attr}=" not in cleaned, cleaned
    assert 'w:ascii="Times New Roman"' in cleaned and 'w:fill="FFFFFF"' in cleaned


def test_backward_compatibility_requirements_aliases(tmp_path: Path) -> None:
    """向后兼容性保护：旧版 -r 参数、requirements 别名与函数在 v4 中必须无缝兼容。"""
    from md_to_word.cli import build_parser
    from md_to_word import (
        export,
        parse_format,
        parse_requirements,
        serialize_format,
        serialize_requirements,
    )

    # 1. CLI -r / --requirements 解析到 format_path
    parser = build_parser()
    args = parser.parse_args(["manuscript.md", "-r", "custom_req.txt"])
    assert args.format_path == "custom_req.txt"

    args2 = parser.parse_args(["manuscript.md", "--requirements", "custom_req2.txt"])
    assert args2.format_path == "custom_req2.txt"

    # 2. 函数别名指向一致
    assert parse_requirements is parse_format
    assert serialize_requirements is serialize_format

    # 3. export(..., requirements=...) 传参兼容
    md_file = tmp_path / "test.md"
    md_file.write_text("# 测试\n\n正文。\n", encoding="utf-8")
    out_docx = tmp_path / "out.docx"
    res = export(md_file, out_docx, requirements=None, preset="zh-academic")
    assert res.ok and out_docx.exists()


def test_legacy_r_flag_still_works_and_says_so(tmp_path: Path, capsys) -> None:
    """老技能文件还在用 `-r`：留着别名，但每次用都要说一句该换成 `-f`——用 `-f` 的人看不到。"""
    from md_to_word.cli import main as cli_main

    manuscript = _write_manuscript(tmp_path)
    out = tmp_path / "out.docx"

    assert cli_main([str(manuscript), "-r", "presets/zh-academic.txt", "-o", str(out)]) == 0
    assert "-r" in capsys.readouterr().err

    assert cli_main([str(manuscript), "-f", "presets/zh-academic.txt", "-o", str(out)]) == 0
    assert "旧写法" not in capsys.readouterr().err


def _two_section_base(path: Path) -> Path:
    from docx import Document
    from docx.enum.section import WD_SECTION

    doc = Document()
    for i in range(2):
        doc.sections[-1].header.paragraphs[0].text = "某某大学学位论文"
        doc.add_paragraph(f"封面第{i + 1}节")
        if i == 0:
            doc.add_section(WD_SECTION.NEW_PAGE)
    doc.save(path)
    return path


def test_keep_pages_without_a_renderer_is_a_usage_answer_not_an_internal_error(
    tmp_path: Path, monkeypatch
) -> None:
    """按页换算节数要先排版，而这台机器排不了。

    以前它从深处抛出去，被 CLI 兜底成「这是本工具的缺陷，请把 traceback 发给维护者」——
    Windows 上这条路永远走不通，却报得像我们出了 bug。
    """
    from md_to_word.visual_qa import word_pdf

    monkeypatch.setattr(word_pdf, "can_render_word_pdf", lambda: (False, "not-darwin"))
    manuscript = tmp_path / "m.md"
    manuscript.write_text("# 第一章 绪论\n\n正文。\n", encoding="utf-8")

    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=tmp_path / "o.docx",
        base_template=str(_two_section_base(tmp_path / "base.docx")),
        keep_pages=2,
    ))

    assert result.returncode != 0
    joined = " ".join(result.errors)
    assert "--cover-sections" in joined and "2 节" in joined, joined
    assert not (tmp_path / "o.docx").exists()


def test_the_success_line_does_not_claim_a_page_check_that_never_ran(
    tmp_path: Path, monkeypatch
) -> None:
    """没有 Word 时只能验结构，就不能说「与原件逐页一致」——那行字正是这条路径的信任来源。"""
    import logging

    from md_to_word.visual_qa import word_pdf

    # 直接挂在 logger 上取，别依赖 caplog：别的用例会把日志配置成不向上传播
    lines: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: lines.append(record.getMessage())
    sink = logging.getLogger("md2word")
    sink.addHandler(handler)
    monkeypatch.setattr(sink, "level", logging.INFO)

    monkeypatch.setattr(word_pdf, "can_render_word_pdf", lambda: (False, "not-darwin"))
    manuscript = tmp_path / "m.md"
    manuscript.write_text("# 第一章 绪论\n\n正文。\n", encoding="utf-8")

    try:
        result = run_export_pipeline(ExportOptions(
            input_path=manuscript,
            output_path=tmp_path / "o.docx",
            base_template=str(_two_section_base(tmp_path / "base.docx")),
            cover_sections=1,
        ))
    finally:
        sink.removeHandler(handler)

    assert result.returncode == 0, result.errors
    text = " | ".join(lines)
    assert "逐页一致" not in text, f"没排过版却说逐页一致：{text}"
    assert "逐节点一致" in text, text


def test_the_output_says_which_version_and_format_made_it(tmp_path: Path) -> None:
    """产物要能自证出处：哪个版本、照哪份格式文件。写进 docProps，且不能带时间戳——
    带了的话同一份稿件重复导出就不再逐字节一致。"""
    import hashlib
    import zipfile

    (tmp_path / "m.md").write_text("---\n---\n\n# 一\n\n正文。\n", encoding="utf-8")
    out = tmp_path / "o.docx"
    result = run_export_pipeline(ExportOptions(input_path=tmp_path / "m.md", output_path=out,
                                               preset="zh-academic"))
    assert result.returncode == 0, result.errors

    core = zipfile.ZipFile(out).read("docProps/core.xml").decode("utf-8")
    preset = Path("presets") / "zh-academic.txt"
    digest = hashlib.sha256(preset.read_bytes()).hexdigest()[:8]
    assert "md-to-word" in core and "zh-academic.txt" in core and digest in core, core


def test_a_skipped_pdf_says_why_and_what_to_do(tmp_path: Path, capsys, monkeypatch) -> None:
    """`--pdf` 没做成时不能只说"未执行"。

    用户既不知道缺什么，也不知道换条路行不行。这条盯着两件事：退出码还是 3（docx 是好的），
    以及屏幕上要说清"为什么非 Word 不可"——LibreOffice 之类不展开域，目录会空着。
    """
    from md_to_word.cli import main as cli_main
    from md_to_word.visual_qa import word_pdf

    monkeypatch.setattr(word_pdf, "can_render_word_pdf", lambda: (False, "not-darwin"))
    monkeypatch.setattr(word_pdf, "render_pdf_via_word", lambda *a, **k: (False, "not-darwin"))

    md = tmp_path / "m.md"
    md.write_text("# 一\n\n正文。\n", encoding="utf-8")
    code = cli_main([str(md), "-o", str(tmp_path / "o.docx"), "--pdf", "--no-check"])
    err = capsys.readouterr().err

    assert code == 3
    assert (tmp_path / "o.docx").is_file()
    assert "Word" in err and "另存" in err, err


def test_an_unreadable_base_is_refused_before_sections_are_counted(tmp_path: Path) -> None:
    """底模不是有效的 docx 时，按内容换算节数那一步不能先撞上去。

    以前 `--keep-until` / `--keep-pages` 在体检之前就去读这份文件，BadZipFile 从深处抛出去，
    CLI 兜底成「这是本工具的缺陷，请把 traceback 发给维护者」——用户拿到的是一句我们自己的
    道歉，而不是「你给的文件打不开」。
    """
    manuscript = tmp_path / "m.md"
    manuscript.write_text("# 第一章 绪论\n\n正文。\n", encoding="utf-8")
    base = tmp_path / "base.docx"
    base.write_bytes(b"Forbidden")          # 网盘/邮件里下坏的那种

    for kwargs in ({"keep_until": "版权使用授权书"}, {"keep_pages": 2}):
        result = run_export_pipeline(ExportOptions(
            input_path=manuscript,
            output_path=tmp_path / "o.docx",
            base_template=str(base),
            **kwargs,
        ))

        joined = " ".join(result.errors)
        assert result.returncode != 0
        assert "打不开" in joined, joined
        assert "本工具的缺陷" not in joined, joined
        assert not (tmp_path / "o.docx").exists()
