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
        "description": "Standard Chinese academic publication layout with SimSun/Times New Roman, GB/T 7714-2015 citations, double-line header, two-character paragraph indents, and three-line tables.",
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
        "description": "International publication-grade English layout with Times New Roman / Arial, running header, block paragraph spacing (0 indent), and Nature-style numbered citations.",
        "typography": {
            "fonts": "Times New Roman / Arial",
            "header": "English running head with page number right-aligned",
            "body": "10pt, 1.15 line spacing, 6pt after paragraph, 0 indent",
            "tables": "Classic publication three-line table",
            "citations": "Nature numbered brackets [1], APA author-date supported",
        },
    },
}

CONTRACT_GUIDE = """# md-to-word Markdown Compilation Rules & Style Contract

md-to-word compiles Markdown into publication-grade Word documents (.docx) with deterministic byte-level consistency. To ensure 100% compliant rendering, follow these rules:

1. Headers & Sections:
   - Use `# Document Title` for the main title.
   - Use `## Section` for H1 headings, `### Subsection` for H2 headings.
   - For abstracts, use `## 摘要` or `## Abstract`.

2. Mathematical Formulas:
   - Inline formulas: `$E = mc^2$` (Must be enclosed with single dollar signs on the SAME line; do NOT split across lines).
   - Display/Block formulas: Enclose within `$$` on separate lines:
     $$
     \\nabla \\times \\mathbf{B} = \\mu_0 \\mathbf{J} + \\mu_0 \\varepsilon_0 \\frac{\\partial \\mathbf{E}}{\\partial t}
     $$
   - Escaped dollar signs in normal text should be written as `\\$100`.

3. Three-Line Tables:
   - Must have outer pipes:
     | Header 1 | Header 2 | Header 3 |
     | :--- | :---: | ---: |
     | Row 1 | Val 2 | Val 3 |
   - Alignment indicators (`:---`, `:---:`, `---:`) are strictly preserved.

4. Citations & References:
   - In-text citation keys: `[@vaswani2017attention]` or `[@knuth1984; @turing1950]`.
   - Place a `references.bib` file alongside the markdown or configure CSL styles.

5. Code Blocks:
   - Always wrap code in triple-backtick fences ```python ... ```, four-space indentation is not recommended.
"""


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


def _resolve_format_txt(format_txt: str | None) -> tuple[Path | None, bool]:
    """Determine whether format_txt is a file path or raw string.
    Returns (Path or None, is_temporary).
    """
    if not format_txt:
        return None, False
    cleaned = format_txt.strip()
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
    tmp.write(format_txt)
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
        title="md-to-word Publishing Compiler",
        description="Deterministic Markdown to Word (.docx) compiler with publication-grade typography, native formulas, three-line tables, and CSL citations.",
        version=getattr(md_to_word, "__version__", "1.0.0"),
        website_url="https://ls-open.github.io/md-to-word/",
    )

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    @server.tool(
        name="compile_markdown",
        title="Compile Markdown to Word (.docx)",
        description="Compile a Markdown manuscript (string or file path) into a publication-compliant Word (.docx) document.",
    )
    def compile_markdown(
        markdown: str,
        output_path: str = "output.docx",
        preset: str = "zh-academic",
        format_txt: str | None = None,
        generate_pdf: bool = False,
        lang: str | None = None,
    ) -> dict[str, Any]:
        """Compile Markdown into a publication-grade Word (.docx) document.

        Args:
            markdown: The Markdown manuscript content as a string, OR an existing .md file path.
            output_path: Target path for the output .docx file. Defaults to 'output.docx'.
            preset: Built-in style preset name. Choices:
                - 'zh-academic': Chinese Academic Thesis / Journal (CNKI / CSCD / CSSCI standard)
                - 'zh-report': Modern Tech Report / Whitepaper (SimHei, single header, shaded tables)
                - 'en-nature': International English Paper (Nature / IEEE style, running head)
                Ignored if format_txt is explicitly provided.
            format_txt: Optional raw format.txt content (or path) to override all typographic rules.
            generate_pdf: Whether to also generate a PDF version (requires LibreOffice or Word installed).
            lang: Optional explicit document language ('zh' or 'en'). Auto-detected if omitted.

        Returns:
            A dictionary containing compilation status, output paths, file size, warnings, and error messages.
        """
        in_path, in_is_tmp = _resolve_markdown_source(markdown)
        fmt_path, fmt_is_tmp = _resolve_format_txt(format_txt)

        try:
            out_docx = Path(output_path).resolve()
            out_docx.parent.mkdir(parents=True, exist_ok=True)

            result = md_to_word.export(
                manuscript=in_path,
                output=out_docx,
                preset=preset if not fmt_path else None,
                requirements=fmt_path,
                pdf=generate_pdf,
                lang=lang,
            )

            file_size = out_docx.stat().st_size if out_docx.exists() else None
            pdf_str = (
                str(result.output_pdf)
                if result.output_pdf and result.output_pdf.exists()
                else None
            )

            return {
                "success": result.ok,
                "returncode": result.returncode,
                "output_docx": str(out_docx) if result.ok else None,
                "output_pdf": pdf_str,
                "file_size_bytes": file_size,
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
        description="Run preflight validation on a Markdown manuscript before compiling, reporting syntax errors, missing citations, and formatting violations.",
    )
    def validate_manuscript(
        markdown: str,
        preset: str = "zh-academic",
        format_txt: str | None = None,
        lang: str = "zh",
    ) -> dict[str, Any]:
        """Check whether a Markdown manuscript conforms to md-to-word publication rules.

        Args:
            markdown: The Markdown manuscript content as a string, OR an existing .md file path.
            preset: Style preset to validate against.
            format_txt: Optional custom format.txt override.
            lang: Language for error messages ('zh' or 'en').

        Returns:
            Dictionary with 'valid' bool, 'errors' list, and 'warnings' list.
        """
        in_path, in_is_tmp = _resolve_markdown_source(markdown)
        fmt_path, fmt_is_tmp = _resolve_format_txt(format_txt)

        try:
            report = md_to_word.validate_manuscript(
                in_path,
                spec_path=fmt_path,
                lang=lang,
            )
            return {
                "valid": report.valid,
                "errors": report.errors,
                "warnings": report.warnings,
            }
        except Exception as exc:
            logger.exception("Validation failed: %s", exc)
            return {
                "valid": False,
                "errors": [str(exc)],
                "warnings": [],
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
        name="list_presets",
        title="List Built-in Style Presets",
        description="List all available built-in publication style presets (Academic Thesis, Tech Report, Nature English Paper) with typography specifications.",
    )
    def list_presets() -> list[dict[str, Any]]:
        """List all available built-in publication style presets with target domains and typographic highlights."""
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
        """Access the complete Markdown formatting contract for publication-grade Word compilation."""
        return CONTRACT_GUIDE

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
        prompt_content = f"""Please draft a publication-grade manuscript on the topic: "{topic}".

Target Style Preset: {preset}
Target Language: {lang}

IMPORTANT COMPILATION CONTRACT:
1. Document Structure:
   - Begin with `# <Document Title>` on the first line.
   - For academic papers, include `## 摘要` / `## Abstract` with keywords.
   - Structure sections cleanly using `## Section` and `### Subsection`.
2. Mathematical Formulas:
   - Inline math must be written as `$formula$` strictly on the same line.
   - Display/Block formulas must be enclosed in `$$` on separate lines.
3. Tables:
   - Write standard three-line tables with enclosing vertical bars `| ... |`.
4. Quality:
   - Avoid HTML tags or non-standard markdown extensions.
   - Ensure complete citations with `[@key]` if citing literature.
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
