"""Model Context Protocol (MCP) server for md-to-word.

Exposes publication-grade deterministic Word compilation, style inspection,
and preflight manuscript validation to AI agents (Claude Desktop, Claude Code,
Cursor, LibreChat, Antigravity, etc.).

Compatible with both modern MCP 2.x (MCPServer) and 1.x (FastMCP).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import md_to_word
from md_to_word.config import (
    DEFAULT_PRESET_EN,
    DEFAULT_PRESET_ZH,
    get_presets_dir,
    resolve_preset_path,
)
from md_to_word.i18n import resolve_lang
from md_to_word.template.extractor import extract_spec_from_docx

logger = logging.getLogger("md_to_word.mcp")

# Detect MCP SDK version (mcp 2.x renamed FastMCP to MCPServer)
try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError:
        MCPServer = None

PRESET_METADATA: dict[str, dict[str, Any]] = {
    "zh-academic": {
        "id": "zh-academic",
        "name": "中文学术期刊 / 学位论文规范 (Chinese Academic Thesis & Journal)",
        "target": "中国知网 (CNKI)、万方、高校硕博学位论文、CSCD/CSSCI 核心期刊",
        "description": "Standard Chinese academic format with SimSun/Times New Roman, GB/T 7714-2015 citations, double-line header, two-character paragraph indents, and three-line tables.",
        "typography": {
            "fonts": "宋体 (SimSun) / Times New Roman",
            "header": "双线页眉 (Double-line header) with running title",
            "body": "小四 (12pt), 首行缩进 2 字符, 1.25 倍行距",
            "tables": "标准三线表 (Three-line table)",
            "citations": "GB/T 7714-2015 顺序编码制 / 著者-出版年制",
        },
    },
    "zh-report": {
        "id": "zh-report",
        "name": "现代技术白皮书 / 机构分析报告 (Modern Tech Report & Whitepaper)",
        "target": "企业技术白皮书、行业研究报告、工程技术规范、解决方案",
        "description": "Modern technical whitepaper layout with SimHei/Calibri, single-line header, compact spacing, shaded tables, and highlighted code fences.",
        "typography": {
            "fonts": "黑体 (SimHei) / Calibri",
            "header": "现代单线页眉 (Single-line header)",
            "body": "五号 (10.5pt), 1.2 倍行距",
            "tables": "现代三线表，表头灰色阴影底纹",
            "citations": "尾注文献列表 / 超链接附录",
        },
    },
    "en-nature": {
        "id": "en-nature",
        "name": "国际顶级英文期刊规范 (International English Paper - Nature / IEEE Style)",
        "target": "Nature, IEEE, ACM, Springer, Elsevier, arXiv submissions",
        "description": "International journal format with Times New Roman / Arial, running header, block paragraph spacing (0 indent), and Nature-style numbered citations.",
        "typography": {
            "fonts": "Times New Roman / Arial",
            "header": "English running head with page number right-aligned",
            "body": "10pt, 1.15 line spacing, 6pt after paragraph, 0 indent",
            "tables": "Classic three-line table",
            "citations": "Nature numbered brackets [1], APA author-date supported",
        },
    },
}

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"


def _read_resource(name: str) -> str:
    """读取包内文档。MCP 不再维护另一份契约，避免和 SKILL.md / guide.md 分叉。"""
    return (RESOURCES_DIR / name).read_text(encoding="utf-8")



def _resolve_markdown_source(markdown: str) -> tuple[Path, bool]:
    """Determine whether input is an existing file path or raw markdown content.
    Returns (Path, is_temporary).
    """
    cleaned = markdown.strip()
    if "\n" not in cleaned:
        candidate = Path(cleaned)
        if candidate.is_file():
            return candidate.resolve(), False

    tmp = tempfile.NamedTemporaryFile(
        suffix=".md",
        mode="w",
        encoding="utf-8",
        delete=False,
    )
    tmp.write(markdown)
    tmp.flush()
    tmp.close()
    return Path(tmp.name), True


def _default_output_path(in_path: Path) -> Path:
    """不覆盖已有文件：同名 .docx 存在时改用 `.out.docx`，再冲突就加序号。"""
    candidate = in_path.with_suffix(".docx")
    if not candidate.exists():
        return candidate
    candidate = in_path.with_name(in_path.stem + ".out.docx")
    if not candidate.exists():
        return candidate
    for i in range(2, 100):
        candidate = in_path.with_name("%s.out-%d.docx" % (in_path.stem, i))
        if not candidate.exists():
            return candidate
    return in_path.with_name("%s.out-%s.docx" % (in_path.stem, os.urandom(4).hex()))


def _resolve_format_source(format: str | None) -> tuple[Path | None, bool]:
    """Determine whether format is a file path or raw string.
    Returns (Path or None, is_temporary).
    """
    if not format:
        return None, False
    cleaned = format.strip()
    if "\n" not in cleaned:
        candidate = Path(cleaned)
        if candidate.is_file():
            return candidate.resolve(), False

    tmp = tempfile.NamedTemporaryFile(
        suffix=".txt",
        mode="w",
        encoding="utf-8",
        delete=False,
    )
    tmp.write(format)
    tmp.flush()
    tmp.close()
    return Path(tmp.name), True


def create_mcp_server() -> Any:
    """Create and configure the MCPServer instance with all tools, resources, and prompts."""
    if MCPServer is None:
        raise RuntimeError(
            "MCP Python SDK is not installed. Please install it with:\n"
            "    pip install \"md-to-word-docx[mcp]\" or pip install \"mcp>=1.0.0\""
        )

    server = MCPServer(
        name="md-to-word",
        title="md-to-word Word Compiler",
        description="Deterministic Markdown to Word (.docx) compiler with native formulas, tables, and CSL citations.",
        version=getattr(md_to_word, "__version__", "1.0.0"),
        website_url="https://ls-open.github.io/md-to-word/",
    )

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    @server.tool(
        name="compile_markdown",
        title="Compile Markdown to Word (.docx)",
        description=(
            "Compile Markdown into a Word (.docx) document. "
            "Ensure structures beyond standard Markdown (e.g. captions, TOC, page breaks, abstract, "
            "math blocks) follow the contract in get_guide. Uses the provided format file, or defaults "
            "to a built-in preset."
        ),
    )
    def compile_markdown(
        markdown: str,
        output_path: str | None = None,
        format: str | None = None,
        preset: str | None = None,
        generate_pdf: bool = False,
        lang: str | None = None,
    ) -> dict[str, Any]:
        """Compile Markdown into a Word (.docx) document.

        Args:
            markdown: The Markdown manuscript content as a string, OR an existing .md file path.
            output_path: Target .docx path. If omitted, the output is written next to the input
                file without overwriting an existing file (`.out.docx` is used on collision);
                raw Markdown goes to a temporary file and its path is returned.
            format: A format file path OR raw format content. This is the typography contract
                (the `format.txt` file), not Python dependency requirements.
            preset: Built-in preset name ('zh-academic', 'zh-report', 'en-nature'). Only used
                when `format` is absent. A preset is a preview baseline, not a deliverable.
            generate_pdf: Whether to also generate a PDF (requires LibreOffice or Word).
            lang: Optional message/document language ('zh' or 'en'); auto-detected if omitted.

        Returns:
            Compilation status, output paths, the format source, warnings and errors.
        """
        in_path, in_is_tmp = _resolve_markdown_source(markdown)
        fmt_path, fmt_is_tmp = _resolve_format_source(format)

        try:
            if output_path:
                out_docx = Path(output_path).expanduser().resolve()
            elif not in_is_tmp:
                out_docx = _default_output_path(in_path)
            else:
                out_docx = Path(tempfile.gettempdir()) / (
                    "md-to-word-%s.docx" % os.urandom(4).hex()
                )
            out_docx.parent.mkdir(parents=True, exist_ok=True)

            result = md_to_word.export(
                manuscript=in_path,
                output=out_docx,
                format=fmt_path,
                preset=preset if not fmt_path else None,
                pdf=generate_pdf,
                lang=lang,
            )

            file_size = out_docx.stat().st_size if out_docx.exists() else None
            pdf_str = (
                str(result.output_pdf)
                if result.output_pdf and result.output_pdf.exists()
                else None
            )
            format_source = (
                "format" if fmt_path
                else ("preset:%s" % preset if preset else "auto-preset")
            )
            notice = ""
            if not fmt_path:
                used_preset = preset or ("zh-academic" if result.lang == "zh" else "en-nature")
                notice = (
                    f"已套用官方内置预设「{used_preset}」完成排版。建议在 Word 中打开核对效果；"
                    "若学校或期刊有专属格式要求，可提供 format 文件或参考 .docx 重新编译。"
                )

            return {
                "success": result.ok,
                "returncode": result.returncode,
                "output_docx": str(out_docx) if result.ok else None,
                "output_pdf": pdf_str,
                "file_size_bytes": file_size,
                "format_source": format_source,
                "notice": notice,
                "messages": result.messages,
                "warnings": result.warnings,
                "errors": result.errors,
                "lang": result.lang,
            }
        except Exception as exc:
            logger.exception("Compilation failed: %s", exc)
            return {
                "success": False,
                "returncode": -1,
                "output_docx": None,
                "output_pdf": None,
                "file_size_bytes": None,
                "format_source": "format" if fmt_path else "none",
                "notice": "",
                "messages": [],
                "warnings": [],
                "errors": [str(exc)],
                "lang": lang or "unknown",
            }
        finally:
            if in_is_tmp and in_path.exists():
                try:
                    in_path.unlink()
                except OSError:
                    pass
            if fmt_is_tmp and fmt_path and fmt_path.exists():
                try:
                    fmt_path.unlink()
                except OSError:
                    pass

    @server.tool(
        name="validate_manuscript",
        title="Validate Markdown Manuscript",
        description=(
            "Validate a Markdown manuscript's syntax and non-standard Markdown structure mappings "
            "against the compilation contract before export."
        ),
    )
    def validate_manuscript(
        markdown: str,
        format: str | None = None,
        preset: str | None = None,
        lang: str | None = None,
    ) -> dict[str, Any]:
        """Check whether a Markdown manuscript conforms to the declared format.

        Args:
            markdown: The Markdown manuscript content as a string, OR an existing .md file path.
            format: A format file path OR raw format content.
            preset: Built-in preset to validate against when `format` is absent.
            lang: Message language ('zh' or 'en'); auto-detected from the manuscript if omitted.

        Returns:
            Dictionary with 'valid', 'errors', 'warnings' and the format source.
        """
        in_path, in_is_tmp = _resolve_markdown_source(markdown)
        fmt_path, fmt_is_tmp = _resolve_format_source(format)

        try:
            if in_is_tmp:
                lang_text = markdown
            else:
                lang_text = in_path.read_text(encoding="utf-8", errors="ignore")
            doc_lang = resolve_lang(lang_text, lang)

            spec_path = fmt_path
            format_source = "format" if fmt_path else ""
            if spec_path is None:
                preset_name = preset or (
                    DEFAULT_PRESET_ZH if doc_lang == "zh" else DEFAULT_PRESET_EN
                )
                spec_path = resolve_preset_path(preset_name)
                format_source = "preset:%s" % preset_name

            report = md_to_word.validate_manuscript(
                in_path,
                spec_path=spec_path,
                lang=doc_lang,
            )
            return {
                "valid": report.valid,
                "errors": report.errors,
                "warnings": report.warnings,
                "format_source": format_source,
                "lang": doc_lang,
            }
        except Exception as exc:
            logger.exception("Validation failed: %s", exc)
            return {
                "valid": False,
                "errors": [str(exc)],
                "warnings": [],
                "format_source": "format" if fmt_path else "none",
                "lang": lang or "unknown",
            }
        finally:
            if in_is_tmp and in_path.exists():
                try:
                    in_path.unlink()
                except OSError:
                    pass
            if fmt_is_tmp and fmt_path and fmt_path.exists():
                try:
                    fmt_path.unlink()
                except OSError:
                    pass

    @server.tool(
        name="get_guide",
        title="Read the Workflow Guide",
        description=(
            "Read this before drafting or compiling. Explains requirements confirmation, "
            "non-standard Markdown structure mappings, and the compilation contract."
        ),
    )
    def get_guide() -> str:
        """Return the packaged workflow guide (identical to SKILL.md)."""
        return _read_resource("guide.md")

    @server.tool(
        name="get_manual",
        title="Read the Full Manual",
        description=(
            "Read the full manual when a spelling or behaviour is not certain: every style "
            "name, YAML key, equation rule, CSL preset and known limit."
        ),
    )
    def get_manual(lang: str = "zh") -> str:
        """Return the full manual; `lang` is 'zh' or 'en'."""
        name = "manual_en.md" if lang == "en" else "manual.md"
        return _read_resource(name)

    @server.tool(
        name="extract_format_from_docx",
        title="Reverse-engineer a format file from a .docx",
        description=(
            "Read a school/journal/company .docx template and produce a draft format file. "
            "The draft lists every value it could determine and a 'to confirm' list it could "
            "not; review those before compiling."
        ),
    )
    def extract_format_from_docx(
        docx_path: str,
        output_path: str | None = None,
        lang: str = "zh",
    ) -> dict[str, Any]:
        """Extract a draft format file from a reference .docx."""
        try:
            text = extract_spec_from_docx(docx_path, output_path, lang)
            return {
                "success": True,
                "format_text": text,
                "output_format": str(Path(output_path).expanduser().resolve())
                if output_path else None,
            }
        except Exception as exc:
            logger.exception("Format extraction failed: %s", exc)
            return {
                "success": False,
                "format_text": None,
                "output_format": None,
                "errors": [str(exc)],
            }

    @server.tool(
        name="list_presets",
        title="List Built-in Style Presets",
        description="List all available built-in style presets (Academic Thesis, Tech Report, Nature English Paper) with typography specifications.",
    )
    def list_presets() -> list[dict[str, Any]]:
        """List all available built-in style presets with target domains and typographic highlights."""
        presets_dir = get_presets_dir()
        result = []
        found_ids = set()

        for meta_id, meta in PRESET_METADATA.items():
            preset_file = presets_dir / f"{meta_id}.txt"
            item = dict(meta)
            item["available_on_disk"] = preset_file.is_file()
            result.append(item)
            found_ids.add(meta_id)

        # Scan any additional custom presets placed in presets/ directory
        if presets_dir.is_dir():
            for p in sorted(presets_dir.glob("*.txt")):
                pid = p.stem
                if pid not in found_ids:
                    result.append({
                        "id": pid,
                        "name": f"Custom Preset ({pid})",
                        "target": "Custom defined specification",
                        "description": f"Custom preset file found at {p.name}",
                        "typography": {},
                        "available_on_disk": True,
                    })

        return result

    @server.tool(
        name="inspect_preset",
        title="Inspect Style Specification (format.txt)",
        description="Inspect the full format.txt typography specification for a given preset.",
    )
    def inspect_preset(preset: str) -> str:
        """Inspect the raw format.txt specification for a given preset name.

        Args:
            preset: Preset name (e.g. 'zh-academic', 'zh-report', 'en-nature').

        Returns:
            Raw text of format.txt specification.
        """
        path = resolve_preset_path(preset)
        if not path or not path.is_file():
            raise ValueError(f"Preset '{preset}' not found in presets directory.")
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    @server.resource("preset://{preset}")
    def get_preset_resource(preset: str) -> str:
        """Access format.txt specification for a style preset."""
        path = resolve_preset_path(preset)
        if not path or not path.is_file():
            return f"# Preset '{preset}' not found."
        return path.read_text(encoding="utf-8")

    @server.resource("guide://contract")
    def get_contract_guide() -> str:
        """Access the packaged workflow guide (same text as SKILL.md)."""
        return _read_resource("guide.md")

    @server.resource("manual://{lang}")
    def get_manual_resource(lang: str) -> str:
        """Access the full manual: `manual://zh` or `manual://en`."""
        return _read_resource("manual_en.md" if lang == "en" else "manual.md")

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    @server.prompt()
    def draft_academic_manuscript(
        topic: str,
        preset: str = "zh-academic",
        lang: str = "zh",
    ) -> list[dict[str, Any]]:
        """Guide the LLM to draft a structured Markdown manuscript compatible with md-to-word.

        Args:
            topic: The subject or title of the paper/report to write.
            preset: Target style preset ('zh-academic', 'zh-report', or 'en-nature').
            lang: Language for the manuscript ('zh' or 'en').
        """
        prompt_content = f"""Please draft a manuscript on the topic: "{topic}".
Target style: {preset}. Target language: {lang}.

Workflow:
1. Confirm export requirements: Use the user's custom format if specified; otherwise use the built-in preset '{preset}'.
2. Draft content following the manuscript contract for elements beyond standard Markdown (captions, TOC, abstract, math blocks; call get_guide for syntax).
"""
        return [{"role": "user", "content": prompt_content}]

    return server


def main() -> None:
    """CLI entry point for running the md-to-word MCP Server."""
    parser = argparse.ArgumentParser(
        description="md-to-word Model Context Protocol (MCP) Server"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for SSE/HTTP transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE/HTTP transport (default: 8000)",
    )
    args = parser.parse_args()

    try:
        server = create_mcp_server()
    except RuntimeError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run(args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
