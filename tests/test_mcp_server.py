"""Tests for Model Context Protocol (MCP) server."""

import pytest
from pathlib import Path
import asyncio
import re

pytest.importorskip("mcp")

from md_to_word.mcp.server import (
    create_mcp_server,
    _resolve_markdown_source,
    RESOURCES_DIR,
)


@pytest.fixture(autouse=True)
def _no_live_word(monkeypatch):
    """底模导出会顺带做版面验真；MCP 单测不启动 Word，真验真另有专门文件。"""
    from md_to_word.visual_qa import word_pdf

    monkeypatch.setattr(word_pdf, "can_render_word_pdf",
                        lambda: (False, "disabled in unit tests"))


def test_mcp_server_initialization():
    async def _run():
        server = create_mcp_server()
        assert server is not None
        assert server.name == "md-to-word"
    asyncio.run(_run())


def test_mcp_list_presets():
    async def _run():
        server = create_mcp_server()
        res = await server.call_tool("list_presets", {})
        assert not res.is_error
        presets = res.structured_content["result"]
        assert len(presets) >= 4
        preset_ids = [p["id"] for p in presets]
        assert "zh-academic" in preset_ids
        assert "zh-tw-academic" in preset_ids
        assert "zh-report" in preset_ids
        assert "en-nature" in preset_ids
    asyncio.run(_run())


def test_mcp_get_contract():
    async def _run():
        server = create_mcp_server()
        res = await server.call_tool("get_contract", {"lang": "en"})
        assert not res.is_error
        payload = res.structured_content
        assert payload["version"]
        assert any(p["id"] == "zh-academic" for p in payload["presets"])
        assert any(s["style"] == "Body Text" for s in payload["styles"])
        assert set(payload["exit_codes"]) == {"0", "1", "2", "3"}
        assert "diagnostics" in payload["json_keys"]
    asyncio.run(_run())


def test_mcp_inspect_base_template():
    async def _run():
        from md_to_word.config import get_base_template_path

        server = create_mcp_server()
        res = await server.call_tool(
            "inspect_base_template", {"docx_path": str(get_base_template_path())}
        )
        assert not res.is_error
        payload = res.structured_content
        assert payload["ok"] is True
        assert payload["section_count"] >= 1
        assert len(payload["sections"]) >= 1
        assert payload["blocking"] == []

        missing = await server.call_tool(
            "inspect_base_template", {"docx_path": "/nonexistent/base.docx"}
        )
        assert missing.structured_content["ok"] is False
        assert missing.structured_content["blocking"]
    asyncio.run(_run())


def test_mcp_inspect_preset():
    async def _run():
        server = create_mcp_server()
        res = await server.call_tool("inspect_preset", {"preset": "zh-academic"})
        assert not res.is_error
        content = res.structured_content["result"]
        assert "宋体" in content or "SimSun" in content or "font" in content
    asyncio.run(_run())


def test_mcp_validate_manuscript():
    async def _run():
        server = create_mcp_server()
        valid_md = "# 标题\n\n## 一级标题\n\n正文内容测试。\n"
        res = await server.call_tool("validate_manuscript", {"markdown": valid_md})
        assert not res.is_error
        data = res.structured_content
        assert data["valid"] is True
        assert len(data["errors"]) == 0
    asyncio.run(_run())


def test_mcp_validate_rejects_a_format_that_cannot_build_a_template():
    """MCP 的 validate 必须和 CLI 的导出用同一套预检。

    空/只有注释的格式能过词表检查，但生成不了样式模板；这里若说 valid，Agent 会
    带着一份注定导不出的稿子继续走。
    """
    async def _run():
        server = create_mcp_server()
        res = await server.call_tool(
            "validate_manuscript",
            {"markdown": "# 一\n\n正文。\n", "format": "# 只有注释\n"},
        )
        assert not res.is_error
        data = res.structured_content
        assert data["valid"] is False
        assert data["errors"], data
    asyncio.run(_run())


def test_mcp_compile_markdown_success(tmp_path: Path):
    async def _run():
        server = create_mcp_server()
        md = """# 智能体论文标题

## 引言

这是智能体通过 MCP 调用的正文段落，包含一个内联公式 $f(x) = x^2$。

| 指标 | 基线模型 | 本文架构 |
| :--- | :---: | ---: |
| 准确率 | 85.2% | 96.8% |
"""
        out_docx = tmp_path / "compiled_output.docx"
        res = await server.call_tool("compile_markdown", {
            "markdown": md,
            "output_path": str(out_docx),
            "preset": "zh-academic"
        })
        assert not res.is_error
        data = res.structured_content
        assert data["success"] is True
        assert data["returncode"] == 0
        assert out_docx.is_file()
        assert out_docx.stat().st_size > 5000
    asyncio.run(_run())


def test_mcp_guide_is_the_packaged_guide():
    """MCP 不能再维护另一份契约；get_guide 必须原样返回包内 guide.md。"""
    async def _run():
        server = create_mcp_server()
        res = await server.call_tool("get_guide", {})
        assert not res.is_error
        expected = (RESOURCES_DIR / "guide.md").read_text(encoding="utf-8")
        assert res.structured_content["result"] == expected
    asyncio.run(_run())


def test_mcp_extract_format_from_docx():
    """模板反推是 MCP 的核心入口之一，不能只有 CLI 能用。"""
    async def _run():
        server = create_mcp_server()
        docx = Path(__file__).resolve().parent.parent / "demo/00_quickstart/hello.docx"
        res = await server.call_tool(
            "extract_format_from_docx", {"docx_path": str(docx)}
        )
        assert not res.is_error
        data = res.structured_content
        assert data["success"] is True
        assert "纸张：" in data["format_text"]
    asyncio.run(_run())


def test_mcp_rejects_format_and_preset_together(tmp_path: Path):
    """与 CLI 同一条规则：两个格式来源同时给，不替调用方猜，也不静默丢掉一个。"""
    fmt = tmp_path / "format.txt"
    fmt.write_text("正文：宋体 小四 行距1.5倍\n", encoding="utf-8")

    async def _run():
        server = create_mcp_server()
        res = await server.call_tool("compile_markdown", {
            "markdown": "# 一\n\n正文。\n",
            "format": str(fmt),
            "preset": "zh-academic",
        })
        assert not res.is_error
        data = res.structured_content
        assert data["success"] is False
        assert any("preset" in error.lower() for error in data["errors"]), data["errors"]
    asyncio.run(_run())


def test_mcp_compile_does_not_overwrite_existing(tmp_path: Path):
    """MCP 默认输出不能覆盖稿件旁边已有的同名 .docx。"""
    md = tmp_path / "doc.md"
    md.write_text("# 引言\n\n正文。\n", encoding="utf-8")
    existing = tmp_path / "doc.docx"
    existing.write_bytes(b"sentinel")

    async def _run():
        server = create_mcp_server()
        res = await server.call_tool("compile_markdown", {"markdown": str(md)})
        assert not res.is_error
        data = res.structured_content
        assert data["success"] is True
        assert Path(data["output_docx"]).name == "doc.out.docx"
        assert existing.read_bytes() == b"sentinel"
    asyncio.run(_run())


def test_single_line_content_with_a_slash_is_not_a_missing_path(tmp_path: Path):
    """`Accuracy 3/4.` 与含 `/` 的字体对都不是文件路径。"""
    from md_to_word.mcp.server import _resolve_format_source

    path, is_tmp = _resolve_markdown_source("Accuracy improved to 3/4.")
    try:
        assert is_tmp is True and path.is_file()
    finally:
        path.unlink()

    fmt, fmt_tmp = _resolve_format_source("正文：宋体/Times New Roman 小四 行距1.5倍")
    try:
        assert fmt_tmp is True and fmt.is_file()
    finally:
        fmt.unlink()

    async def _run():
        server = create_mcp_server()
        out = tmp_path / "content.docx"
        res = await server.call_tool(
            "compile_markdown",
            {"markdown": "Accuracy improved to 3/4.", "output_path": str(out)},
        )
        assert res.structured_content["success"] is True, res.structured_content
    asyncio.run(_run())


def test_mcp_failure_does_not_report_a_previous_output_as_this_run(tmp_path: Path):
    out = tmp_path / "paper.docx"
    out.write_bytes(b"OLD-BUILD")

    async def _run():
        server = create_mcp_server()
        res = await server.call_tool(
            "compile_markdown",
            {
                "markdown": "# 一\n\n![](missing.png)\n",
                "output_path": str(out),
                "preset": "zh-academic",
            },
        )
        data = res.structured_content
        assert data["success"] is False
        assert data["output_docx"] is None
        assert data["file_size_bytes"] is None, data
        assert data["notice"] == ""
        assert data["errors"]
    asyncio.run(_run())


def test_mcp_validate_keeps_the_same_keys_on_success_and_failure(tmp_path: Path):
    async def _run():
        server = create_mcp_server()
        ok = await server.call_tool(
            "validate_manuscript", {"markdown": "# 一\n\n正文。\n", "preset": "zh-academic"}
        )
        bad = await server.call_tool(
            "validate_manuscript", {"markdown": str(tmp_path / "missing.md")}
        )
        assert set(ok.structured_content) == set(bad.structured_content)
        assert bad.structured_content["valid"] is False
        assert bad.structured_content["diagnostics"][0]["code"] == "pipeline.input_missing"
    asyncio.run(_run())


def test_resolve_markdown_source_file(tmp_path: Path):
    f = tmp_path / "doc.md"
    f.write_text("# Test", encoding="utf-8")
    p, is_tmp = _resolve_markdown_source(str(f))
    assert p == f.resolve()
    assert is_tmp is False


def test_resolve_markdown_source_raw_content():
    p, is_tmp = _resolve_markdown_source("# Raw content\nline 2")
    assert is_tmp is True
    assert p.is_file()
    assert p.read_text(encoding="utf-8") == "# Raw content\nline 2"
    p.unlink()


def test_mcp_missing_markdown_path_is_an_error() -> None:
    """路径拼错不能当成正文导出成一份“内容是路径”的 docx。"""
    async def _run():
        server = create_mcp_server()
        res = await server.call_tool(
            "compile_markdown", {"markdown": "/definitely/missing/paper.md"}
        )
        assert not res.is_error
        data = res.structured_content
        assert data["success"] is False
        assert any("not found" in error.lower() for error in data["errors"]), data["errors"]
    asyncio.run(_run())


def test_mcp_format_accepts_a_path_or_text_not_a_preset_name() -> None:
    async def _run():
        server = create_mcp_server()
        res = await server.call_tool(
            "compile_markdown",
            {"markdown": "# Title\n\nBody.\n", "format": "zh-academic"},
        )
        assert not res.is_error
        data = res.structured_content
        assert data["success"] is False
        assert any("preset" in error.lower() for error in data["errors"]), data["errors"]
    asyncio.run(_run())


def test_mcp_invalid_preset_is_an_error_not_a_skipped_gate() -> None:
    async def _run():
        server = create_mcp_server()
        res = await server.call_tool(
            "validate_manuscript",
            {"markdown": "# 一\n\n正文。\n", "preset": "zh_academic"},
        )
        assert not res.is_error
        data = res.structured_content
        assert data["valid"] is False
        # 报错语言跟稿件走（中文稿），所以断言只认预设名，不认英文外壳
        assert any("zh_academic" in error for error in data["errors"]), data["errors"]
    asyncio.run(_run())


def test_mcp_gbk_file_detects_chinese(tmp_path: Path) -> None:
    manuscript = tmp_path / "gbk.md"
    manuscript.write_bytes("# 引言\n\n这是一段中文正文。\n".encode("gbk"))

    async def _run():
        server = create_mcp_server()
        res = await server.call_tool(
            "validate_manuscript",
            {"markdown": str(manuscript), "preset": "zh-academic"},
        )
        assert not res.is_error
        data = res.structured_content
        assert data["valid"] is True, data
        assert data["doc_lang"] == "zh"
    asyncio.run(_run())


def test_mcp_notice_uses_the_actual_preset_not_message_language(tmp_path: Path) -> None:
    manuscript = tmp_path / "paper.md"
    manuscript.write_text("# 引言\n\n这是一段中文正文。\n", encoding="utf-8")

    async def _run():
        server = create_mcp_server()
        res = await server.call_tool(
            "compile_markdown",
            {"markdown": str(manuscript), "lang": "en"},
        )
        assert not res.is_error
        data = res.structured_content
        assert data["success"] is True, data
        assert data["doc_lang"] == "zh"
        assert data["format_source"] == "preset:zh-academic"
        assert "zh-academic" in data["notice"]
        assert "en-nature" not in data["notice"]
    asyncio.run(_run())


def test_mcp_compile_can_pour_into_a_school_template(tmp_path: Path) -> None:
    """MCP 是第三个入口：命令行有的能力，这里也得有，否则走 MCP 的 Agent 用不了这条路。"""
    from docx import Document
    from docx.enum.section import WD_SECTION

    base = tmp_path / "base.docx"
    doc = Document()
    for i in range(2):
        doc.add_paragraph(f"封面第{i + 1}节")
        if i == 0:
            doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_paragraph("版权使用授权书 本人同意……")
    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_paragraph("正文占位")
    doc.save(base)

    async def _run():
        server = create_mcp_server()
        res = await server.call_tool("compile_markdown", {
            "markdown": "# 第一章 绪论\n\n正文。\n",
            "output_path": str(tmp_path / "out.docx"),
            "base_template": str(base),
            "keep_until": "版权使用授权书",
        })
        payload = res.structured_content
        assert payload["success"], payload["errors"]
        assert Path(payload["output_docx"]).is_file()

    asyncio.run(_run())


def test_mcp_returns_the_whole_manual_including_the_thesis_part() -> None:
    """手册只有一份：远端调用方拿到的那份里，学位论文那一章也得在。"""
    async def _run():
        server = create_mcp_server()
        out = await server.call_tool("get_manual", {"lang": "zh"})
        text = out.structured_content["result"]
        assert "--base-template" in text and "## 9. " in text
    asyncio.run(_run())


def test_all_three_entrances_offer_the_same_options() -> None:
    """CLI / Python / MCP 是同一个引擎的三张脸。少一张脸的门票，用户就得换入口才能用。

    以前 `--base-template` 只在命令行有：走 Python 的脚本和走 MCP 的 Agent 完全用不了。
    这里直接读 MCP 的 tool schema，不再对源码做子串搜索——注释里出现一个词不算支持。
    """
    import inspect

    import md_to_word
    from md_to_word.pipeline import ExportOptions

    async def _schema() -> dict:
        server = create_mcp_server()
        for tool in await server.list_tools():
            if tool.name == "compile_markdown":
                return tool.input_schema
        raise AssertionError("MCP 没有 compile_markdown")

    schema = asyncio.run(_schema())
    fields = set(ExportOptions.__annotations__)
    api = set(inspect.signature(md_to_word.export).parameters)
    properties = set(schema["properties"])

    pairs = {
        "base_template": "base_template",
        "cover_sections": "cover_sections",
        "keep_pages": "keep_pages",
        "keep_until": "keep_until",
        "blind_review": "blind_review",
        # 同一个能力三个入口的历史叫法不同：Python/CLI 说 pdf，MCP 说 generate_pdf
        "make_pdf": "pdf",
    }
    for field, api_name in pairs.items():
        assert field in fields, f"ExportOptions 缺 {field}"
        assert api_name in api, f"Python API export() 缺 {api_name}"
    assert "generate_pdf" in properties, "MCP compile_markdown 缺 generate_pdf"
    for name in ("base_template", "cover_sections", "keep_pages", "keep_until", "blind_review"):
        assert name in properties, f"MCP compile_markdown 缺 {name}"


def test_the_manual_is_readable_as_a_resource() -> None:
    """资源模板也要能取到：工具（get_manual）和资源是两条路，只测一条等于没测。"""
    async def _run():
        server = create_mcp_server()
        out = await server.read_resource("manual://zh")
        text = out[0].content if isinstance(out, list) else str(out)
        assert "--base-template" in text
        assert "--keep-until" in text

    asyncio.run(_run())


def test_mcp_list_presets_speaks_the_requested_language() -> None:
    """预设说明是给 Agent 读的：英文请求不能拿回一屏中文。"""
    async def _run():
        server = create_mcp_server()
        en = (await server.call_tool("list_presets", {"lang": "en"})).structured_content["result"]
        zh = (await server.call_tool("list_presets", {"lang": "zh"})).structured_content["result"]

        blob = str([(p["name"], p["target"], p["typography"]) for p in en])
        assert not re.search(r"[一-鿿]", blob), blob
        assert any(re.search(r"[一-鿿]", p["name"]) for p in zh)
    asyncio.run(_run())
