"""Tests for Model Context Protocol (MCP) server."""

import pytest
from pathlib import Path
import tempfile
import asyncio

pytest.importorskip("mcp")

from md_to_word.mcp.server import (
    create_mcp_server,
    _resolve_markdown_source,
    _resolve_format_source,
    RESOURCES_DIR,
)


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
        assert len(presets) >= 3
        preset_ids = [p["id"] for p in presets]
        assert "zh-academic" in preset_ids
        assert "zh-report" in preset_ids
        assert "en-nature" in preset_ids
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


def test_mcp_can_return_the_thesis_volume() -> None:
    """第 1 册里写着「封面见第 2 册」，远端调用方读不到本地路径——第 2 册必须能单独取。"""
    async def _run():
        server = create_mcp_server()
        general = await server.call_tool("get_manual", {"lang": "zh"})
        thesis = await server.call_tool("get_manual", {"lang": "zh", "volume": "thesis"})
        a = general.structured_content["result"]
        b = thesis.structured_content["result"]
        assert "--base-template" in b
        assert a != b
    asyncio.run(_run())


def test_all_three_entrances_offer_the_same_options() -> None:
    """CLI / Python / MCP 是同一个引擎的三张脸。少一张脸的门票，用户就得换入口才能用。

    以前 `--base-template` 只在命令行有：走 Python 的脚本和走 MCP 的 Agent 完全用不了。
    """
    import inspect

    import md_to_word
    from md_to_word.pipeline import ExportOptions

    names = ("base_template", "cover_sections", "keep_pages", "keep_until")
    fields = set(ExportOptions.__annotations__)
    api = set(inspect.signature(md_to_word.export).parameters)
    src = inspect.getsource(create_mcp_server)

    for name in names:
        assert name in fields, f"ExportOptions 缺 {name}"
        assert name in api, f"Python API export() 缺 {name}"
        assert f"{name}:" in src or f"{name} =" in src or f'"{name}"' in src, \
            f"MCP compile_markdown 缺 {name}"


def test_the_thesis_volume_is_readable_as_a_resource() -> None:
    """资源模板也要能取到：工具（get_manual）和资源是两条路，只测一条等于没测。"""
    async def _run():
        server = create_mcp_server()
        out = await server.read_resource("manual-thesis://zh")
        text = out[0].content if isinstance(out, list) else str(out)
        assert "--base-template" in text
        assert "--keep-until" in text

    asyncio.run(_run())
