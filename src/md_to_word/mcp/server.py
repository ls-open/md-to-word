"""Model Context Protocol (MCP) server for md-to-word.

Exposes deterministic Word compilation, style inspection,
and preflight manuscript validation to AI agents (Claude Desktop, Claude Code,
Cursor, LibreChat, Antigravity, etc.).

Compatible with both modern MCP 2.x (MCPServer) and 1.x (FastMCP).
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import md_to_word
from md_to_word.config import (
    resolve_preset_path,
)
from md_to_word.contract import contract_payload
from md_to_word.i18n import resolve_lang, t
from md_to_word.spec.presets import list_available_presets
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
        "name": "简体中文学术期刊 / 学位论文规范",
        "name_en": "Simplified Chinese academic journal / thesis",
        "target": "中国知网 (CNKI)、万方、高校硕博学位论文、CSCD/CSSCI 核心期刊",
        "target_en": "CNKI, Wanfang, university master's and doctoral theses, CSCD/CSSCI journals",
        "description": "Simplified Chinese academic format (zh-CN) with SimSun/SimHei + Times New Roman, compressed punctuation (compressPunctuation), 2-char indent, 1.5x line spacing, and three-line tables.",
        "typography": {
            "fonts": "宋体 (SimSun) / 黑体 (SimHei) / Times New Roman",
            "header": "无默认页眉（按学术规范留白；页脚居中阿拉伯数字页码）",
            "body": "小四 (12pt), 首行缩进 2 字符, 1.5 倍行距, 校对语言 zh-CN",
            "tables": "标准三线表 (Three-line table)",
            "citations": "GB/T 7714-2015 顺序编码制（中文默认）/ 著者-出版年制",
        },
        "typography_en": {
            "fonts": "SimSun / SimHei / Times New Roman",
            "header": "No header by default; centered decimal page number in the footer",
            "body": "12pt, 2-char first-line indent, 1.5 line spacing, proofing zh-CN",
            "tables": "Three-line table",
            "citations": "GB/T 7714-2015 numeric (default) / author-date",
        },
    },
    "zh-tw-academic": {
        "id": "zh-tw-academic",
        "name": "繁體中文學術期刊 / 學位論文規範",
        "name_en": "Traditional Chinese academic journal / thesis",
        "target": "台灣 / 香港 / 澳門繁體中文碩博士學位論文與學術期刊",
        "target_en": "Master's and doctoral theses and journals in Taiwan, Hong Kong and Macau",
        "description": "Traditional Chinese academic format (zh-TW) using PMingLiU/Microsoft JhengHei + Times New Roman, uncompressed full-width punctuation (doNotCompress), 2-char indent, 1.5x spacing, and three-line tables.",
        "typography": {
            "fonts": "PMingLiU (新細明體) / Microsoft JhengHei (微軟正黑體) / Times New Roman",
            "header": "無預設頁眉（頁腳置中阿拉伯數字頁碼）",
            "body": "小四 (12pt), 首行縮進 2 字符, 1.5 倍行距, 校對語言 zh-TW, 標點不壓縮",
            "tables": "標準三線表 (Three-line table)",
            "citations": "APA / IEEE / GB/T 7714-2015（於稿件 YAML 以 csl: 指定）",
        },
        "typography_en": {
            "fonts": "PMingLiU / Microsoft JhengHei / Times New Roman",
            "header": "No header by default; centered decimal page number in the footer",
            "body": "12pt, 2-char first-line indent, 1.5 line spacing, proofing zh-TW, punctuation uncompressed",
            "tables": "Three-line table",
            "citations": "APA / IEEE / GB/T 7714-2015 (set csl: in the manuscript YAML)",
        },
    },
    "zh-report": {
        "id": "zh-report",
        "name": "现代技术白皮书 / 机构分析报告",
        "name_en": "Modern technical whitepaper / institutional report",
        "target": "企业技术白皮书、行业研究报告、工程技术规范、解决方案",
        "target_en": "Corporate whitepapers, industry research, engineering specifications, proposals",
        "description": "Modern technical whitepaper layout with SimSun/SimHei/KaiTi + Times New Roman, a colored level-1 heading, single-line header, full-grid tables, and block paragraphs (0 indent, 6pt after).",
        "typography": {
            "fonts": "宋体 (SimSun) / 黑体 (SimHei) / 楷体 (KaiTi) / Times New Roman",
            "header": "现代单线页眉",
            "body": "小四 (12pt), 1.5 倍行距, 段后 6pt, 首行缩进 0",
            "tables": "全网格线表格 (0.75pt 外框 / 0.5pt 内线)",
            "citations": "GB/T 7714-2015 / APA",
        },
        "typography_en": {
            "fonts": "SimSun / SimHei / KaiTi / Times New Roman",
            "header": "Modern single-line header",
            "body": "12pt, 1.5 line spacing, 6pt after, no first-line indent",
            "tables": "Full-grid table (0.75pt outer / 0.5pt inner)",
            "citations": "GB/T 7714-2015 / APA",
        },
    },
    "zh-gb9704": {
        "id": "zh-gb9704",
        "name": "党政机关公文正文版式 (GB/T 9704-2012)",
        "name_en": "Chinese official-document body (GB/T 9704-2012)",
        "target": "党政机关公文、通知、函件（正文版式；红头与版记需 --base-template）",
        "target_en": "Party and government documents, notices and letters (body layout; the letterhead and document-tail block need --base-template)",
        "description": "GB/T 9704-2012 body layout: A4, 37/35/28/26mm mirrored margins, 16pt FangSong body, 28.9pt fixed line spacing (22 lines per page), 22pt XiaoBiaoSong title, 14pt SimSun page number. Not the red letterhead, document number or document-tail block.",
        "typography": {
            "fonts": "仿宋 / 黑体 / 楷体 / 方正小标宋简体 / 宋体",
            "header": "无页眉",
            "body": "三号 (16pt), 首行缩进 2 字符, 固定行距 28.9 磅, 每面 22 行, 校对语言 zh-CN",
            "tables": "全网格线 (0.5pt)",
            "citations": "不设参考文献表（公文引用用发文字号）",
            "known_deviations": "页码数字按西文字体 Times New Roman 渲染；标题的方正小标宋简体需自行安装，缺字体时 Word 会替换；无红头/版记/印章",
        },
        "typography_en": {
            "fonts": "FangSong / SimHei / KaiTi / FangZheng XiaoBiaoSong / SimSun",
            "header": "No header",
            "body": "16pt, 2-char first-line indent, fixed 28.9pt line spacing, 22 lines per page, proofing zh-CN",
            "tables": "Full-grid (0.5pt)",
            "citations": "No reference list (documents cite by document number)",
            "known_deviations": "Page-number digits render in Times New Roman; the FangZheng XiaoBiaoSong title font must be installed (Word substitutes it when missing); no red letterhead, document-tail block or seal",
        },
    },
    "en-apa-student": {
        "id": "en-apa-student",
        "name": "APA 7（学生论文）",
        "name_en": "APA 7 (student paper)",
        "target": "美国高校课程论文与学期作业",
        "target_en": "US university coursework and term papers",
        "description": "APA 7 distinguishes student and professional formats; this preset is the student one (no running head, page number top right). US Letter, 1-inch margins, 12pt Times New Roman, double spacing, 0.5-inch first-line indent, heading levels 1-5 (levels 4 and 5 approximated as indented paragraphs), references on a new page with 0.5-inch hanging indent.",
        "typography": {
            "fonts": "Times New Roman / Consolas (code)",
            "header": "右上角页码（学生论文：无 running head）",
            "body": "12pt, 双倍行距, 首行缩进 0.5in, en-US",
            "tables": "三线表（无竖线）",
            "citations": "APA 7th（默认）",
        },
        "typography_en": {
            "fonts": "Times New Roman / Consolas (code)",
            "header": "Page number top-right (student paper: no running head)",
            "body": "12pt, double spacing, 0.5in first-line indent, en-US",
            "tables": "Three-line table (no vertical rules)",
            "citations": "APA 7th (default)",
        },
    },
    "en-nature": {
        "id": "en-nature",
        "name": "国际英文期刊通用版式",
        "name_en": "International English journal (generic)",
        "target": "通用英文期刊与预印本投稿（按目标期刊调整数值）",
        "target_en": "General English journals and preprints (tune the values per venue)",
        "description": "Generic single-column journal layout with Times New Roman / Consolas, block paragraph spacing (0 indent, 6pt after) and 1.5x line spacing. The preset does not reproduce any publisher's template; citation style is chosen with csl: (APA by default, nature.csl / ieee.csl for numbered styles).",
        "typography": {
            "fonts": "Times New Roman / Consolas（代码）",
            "header": "默认无页眉；页脚居中阿拉伯数字页码",
            "body": "12pt，1.5 倍行距，段后 6pt，首行不缩进，en-US",
            "tables": "标准三线表",
            "citations": "默认 APA 著者-出版年；YAML 写 csl: 可改用 Nature / IEEE 顺序编码",
        },
        "typography_en": {
            "fonts": "Times New Roman / Consolas (code)",
            "header": "No header by default; centered decimal page number in the footer",
            "body": "12pt, 1.5 line spacing, 6pt after, no first-line indent, en-US",
            "tables": "Classic three-line table",
            "citations": "APA author-date default; Nature/IEEE numbered citations via csl: YAML",
        },
    },
}

def _preset_view(meta: dict[str, Any], lang: str) -> dict[str, Any]:
    """预设说明按消息语言取：中文名字、适用场景与排版摘要各一套。"""
    en = lang == "en"
    return {
        "name": meta.get("name_en") if en else meta.get("name"),
        "target": meta.get("target_en") if en else meta.get("target"),
        "description": meta.get("description"),
        "typography": meta.get("typography_en") if en else meta.get("typography"),
    }


RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"


def _read_resource(name: str) -> str:
    """读取包内文档。MCP 不再维护另一份契约，避免和 SKILL.md / guide.md 分叉。"""
    return (RESOURCES_DIR / name).read_text(encoding="utf-8")


def _read_manual(lang: str) -> str:
    """手册只有一份；学位论文那一部分在 §9。"""
    return _read_resource("manual_en.md" if lang == "en" else "manual.md")



def _looks_like_path(value: str) -> bool:
    """单行输入是路径还是正文。

    只看「含 `/`」会把 `Accuracy 3/4.`、`正文：宋体/Times New Roman 12pt` 这类
    正常内容误判成缺失文件。判据收紧为：绝对/相对路径前缀、盘符、反斜杠，
    或已知的文件扩展名。
    """
    if "\n" in value or not value.strip():
        return False
    cleaned = value.strip()
    if cleaned.startswith(("/", "~", "./", "../")):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", cleaned) or "\\" in cleaned:
        return True
    return Path(cleaned).suffix.lower() in {
        ".md", ".markdown", ".txt", ".docx", ".bib"
    }


def _resolve_markdown_source(markdown: str) -> tuple[Path, bool]:
    """Determine whether input is an existing file path or raw markdown content.
    Returns (Path, is_temporary).
    """
    cleaned = markdown.strip()
    if "\n" not in cleaned:
        candidate = Path(cleaned)
        if candidate.is_file():
            return candidate.resolve(), False
        if _looks_like_path(cleaned):
            # 路径拼错时不能把路径字符串当正文导出；交回一个不存在的绝对路径，
            # 由流水线统一报 `pipeline.input_missing`（带 code、file、正确语言）。
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
        if _looks_like_path(cleaned):
            # 同上：交给 `resolve_format` 报 `pipeline.format_missing`。
            return candidate.resolve(), False
        if resolve_preset_path(cleaned):
            raise ValueError(
                f"`format` accepted a preset name ({cleaned}). "
                "Pass it as `preset`; `format` is a file path or raw format text."
            )

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
        version=md_to_word.__version__,
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
            "to a built-in preset. With `base_template`, use exactly one of `keep_until` (cut after "
            "the named paragraph) or `cover_sections` (keep N whole sections); compatibility mode, "
            "mirror margins, punctuation compression and odd/even headers must match the format, or "
            "the export is refused."
        ),
    )
    def compile_markdown(
        markdown: str,
        output_path: str | None = None,
        format: str | None = None,
        preset: str | None = None,
        generate_pdf: bool = False,
        lang: str | None = None,
        base_template: str | None = None,
        cover_sections: int = 0,
        keep_until: str = "",
        blind_review: bool = False,
    ) -> dict[str, Any]:
        """Compile Markdown into a Word (.docx) document.

        Args:
            markdown: The Markdown manuscript content as a string, OR an existing .md file path.
                Raw content is compiled from a temporary directory, so relative `bibliography:`,
                `csl:` and image paths cannot resolve; pass the manuscript path when it uses them.
            output_path: Target .docx path. If omitted, the output is written next to the input
                file without overwriting an existing file (`.out.docx` is used on collision);
                raw Markdown goes to a temporary file and its path is returned.
            format: A format file path OR raw format content. This is the typography contract
                (the `format.txt` file), not Python dependency requirements. A preset name
                (`zh-academic`) is rejected here; pass it as `preset`.
            preset: Built-in preset name (see `list_presets` / `get_contract`).
                Only used when `format` is absent. A preset is a starting baseline; provide a format
                file or customize it for deliverable specs.
            generate_pdf: Whether to also generate a PDF (requires Word on macOS).
            lang: Message language only ('zh' or 'en'); auto-detected if omitted. The document
                language, default preset and default CSL follow the manuscript, never `lang`.
            base_template: Pre-existing .docx template (with cover pages, declarations, or front
                matter) to pour the generated body into while preserving its leading front-matter
                sections unchanged (nothing is written if verification fails). Pair with exactly one
                of `keep_until` / `cover_sections`. Document-wide layout settings (compatibility
                mode, mirror margins, punctuation compression, odd/even headers) must match the
                format; a mismatch is refused rather than silently changing the cover.
            cover_sections: Keep the base's first N sections as front matter.
            keep_until: Say it by content (recommended) — name the last line you want kept
                (inclusive), e.g. "作者签名". The paragraph containing it is the last kept
                paragraph; a section break is inserted after it and everything after is dropped.
                Text inside a table cannot be a cut point. To keep whole sections, use
                `cover_sections`.
            blind_review: Strip identifying document properties (author, company, custom
                properties, thumbnail, comment authors) from the final .docx. Cleans file
                metadata only; names in the body/cover/headers are not anonymised.

        Returns:
            Compilation status, output paths, the format source, warnings and errors.
        """
        in_path = None
        fmt_path = None
        in_is_tmp = fmt_is_tmp = False
        try:
            in_path, in_is_tmp = _resolve_markdown_source(markdown)
            fmt_path, fmt_is_tmp = _resolve_format_source(format)

            if output_path:
                out_docx = Path(output_path).expanduser().resolve()
            elif not in_is_tmp:
                out_docx = _default_output_path(in_path)
            else:
                out_docx = Path(tempfile.gettempdir()) / (
                    "md-to-word-%s.docx" % os.urandom(4).hex()
                )
            # 稿件不存在时不要先建输出目录：否则 `/missing/paper.md` 会把错误变成
            # 「只读文件系统」的内部异常，而真正的原因是 input_missing。
            if in_path.is_file():
                out_docx.parent.mkdir(parents=True, exist_ok=True)

            result = md_to_word.export(
                manuscript=in_path,
                output=out_docx,
                format=fmt_path,
                # `format` 与 `preset` 同时给时交给流水线当场拒绝。CLI 这么做，
                # MCP 旧行为是静默丢掉 preset——调用方以为预设生效了，拿到的却是
                # 另一份格式；两个入口对同一组参数不能有两个答案。
                preset=preset,
                pdf=generate_pdf,
                lang=lang,
                base_template=base_template,
                cover_sections=cover_sections,
                keep_until=keep_until,
                blind_review=blind_review,
            )

            # 失败时目标路径上可能还躺着上一次的成品；它的字节数不是本次产物，
            # 不能跟着 `success=false` 一起返回——客户端只看这两个字段就会误判。
            success = result.ok
            file_size = (
                out_docx.stat().st_size
                if success and out_docx.exists()
                else None
            )
            pdf_str = (
                str(result.output_pdf)
                if success and result.output_pdf and result.output_pdf.exists()
                else None
            )
            format_source = result.format_source or (
                "format" if fmt_path
                else ("preset:%s" % preset if preset else "none")
            )
            notice = ""
            if success and format_source.startswith("preset:"):
                used_preset = format_source.split(":", 1)[1]
                notice = t("mcp.preset_notice", result.lang, preset=used_preset)

            return {
                "success": success,
                "returncode": result.returncode,
                "output_docx": str(out_docx) if success else None,
                "output_pdf": pdf_str,
                # `returncode == 3` 只说「PDF 没做成」，不说为什么。CLI 的 `--json`
                # 已经把这个原因码交出去了（`no-word` / `word-error` / …），MCP 不能
                # 只留一个状态码让 Agent 去猜——同一个引擎的两个出口要能对上。
                "pdf_skip_reason": result.pdf_skip_reason or None,
                "file_size_bytes": file_size,
                "format_source": format_source,
                "notice": notice,
                "messages": result.messages,
                "warnings": result.warnings,
                "errors": result.errors,
                "diagnostics": [d.as_dict() for d in result.diagnostics],
                "lang": result.lang,
                "doc_lang": result.doc_lang,
            }
        except Exception as exc:
            logger.exception("Compilation failed: %s", exc)
            from md_to_word.diagnostics import Diagnostic

            message = str(exc)
            return {
                "success": False,
                "returncode": 1,
                "output_docx": None,
                "output_pdf": None,
                "pdf_skip_reason": None,
                "file_size_bytes": None,
                "format_source": "format" if fmt_path else "none",
                "notice": "",
                "messages": [],
                "warnings": [],
                "errors": [message],
                "diagnostics": [
                    Diagnostic("error", "mcp.internal_error", message).as_dict()
                ],
                "lang": lang or "zh",
                "doc_lang": "",
            }
        finally:
            if in_is_tmp and in_path is not None and in_path.exists():
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
                Raw content is compiled from a temporary directory, so relative `bibliography:`,
                `csl:` and image paths cannot resolve; pass the manuscript path when it uses them.
            format: A format file path OR raw format content; a preset name is rejected here.
            preset: Built-in preset to validate against when `format` is absent.
            lang: Message language only ('zh' or 'en'); auto-detected if omitted. The document
                language and default preset follow the manuscript.

        Returns:
            Dictionary with 'valid', 'errors', 'warnings', the format source, the message
            language (`lang`) and the manuscript language (`doc_lang`).
        """
        in_path = None
        fmt_path = None
        in_is_tmp = fmt_is_tmp = False
        try:
            in_path, in_is_tmp = _resolve_markdown_source(markdown)
            fmt_path, fmt_is_tmp = _resolve_format_source(format)

            # 校验与 CLI 共用 `run_validation`：读稿、选格式、预检、模板可生成性
            # 都在同一条路径上。这里若另写一套，空格式会被 MCP 说成“没问题”，
            # 真正编译却失败——对 Agent 是最糟的安全信号。
            from md_to_word.pipeline import ExportOptions, run_validation

            result = run_validation(ExportOptions(
                input_path=in_path, format_path=fmt_path, preset=preset, lang=lang,
            ))
            return {
                "valid": result.returncode == 0 and not result.errors,
                "errors": result.errors,
                "warnings": result.warnings,
                "diagnostics": [d.as_dict() for d in result.diagnostics],
                "format_source": result.format_source or (
                    "format" if fmt_path else "none"
                ),
                # 与 compile / CLI `--json` 同一语义：`lang` 是消息语言，
                # `doc_lang` 是文档语言。
                "lang": result.lang,
                "doc_lang": result.doc_lang,
            }
        except Exception as exc:
            logger.exception("Validation failed: %s", exc)
            from md_to_word.diagnostics import Diagnostic

            message = str(exc)
            return {
                "valid": False,
                "errors": [message],
                "warnings": [],
                "diagnostics": [
                    Diagnostic("error", "mcp.internal_error", message).as_dict()
                ],
                "format_source": "format" if fmt_path else "none",
                "lang": lang or "zh",
                "doc_lang": "",
            }
        finally:
            if in_is_tmp and in_path is not None and in_path.exists():
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
            "name, YAML key, equation rule, CSL preset and known limit, plus §9 for custom "
            "covers, front matter, section/page numbering, and `--base-template`."
        ),
    )
    def get_manual(lang: str = "zh") -> str:
        """Return the manual; `lang` is 'zh' or 'en'. §9 covers front matter and base templates."""
        return _read_manual(lang)

    @server.tool(
        name="get_contract",
        title="Read the machine-readable contract",
        description=(
            "Return the stable contract as one JSON object: version, agent guide and manual "
            "paths, built-in presets with sha256, accepted style names (Chinese and English), "
            "YAML keys, block markers, figure formats, exit codes and the --json result keys. "
            "Read this instead of parsing prose; keys and style names do not change between "
            "minor versions."
        ),
    )
    def get_contract(lang: str = "zh") -> dict[str, Any]:
        """Same payload as `md-to-word --contract --json`."""
        return contract_payload(lang if lang in ("zh", "en") else "zh")

    @server.tool(
        name="extract_format_from_docx",
        title="Reverse-engineer a format file from a .docx",
        description=(
            "Read a reference .docx template (institution, journal, or organization) and produce "
            "a draft format file. The draft writes every value it could determine and lists what "
            "it could read but cannot express. Direct formatting (hand-tuned spacing, indents, "
            "emphasis) lives outside styles and is neither read nor listed — compare the draft "
            "against the original before compiling. Files exported by this tool are refused: "
            "their styles are the compiler's own, not the reference template's."
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
        name="inspect_base_template",
        title="Inspect a school/base .docx template",
        description=(
            "Check a .docx template before passing it as `base_template`: whether it can be "
            "read, how many sections it has, the first text of each section, and its document-wide "
            "settings (compatibility mode, mirror margins, punctuation compression, odd/even headers, "
            "proofing language). A compatibility mode other than 15 is reported as blocking. Run this "
            "instead of trial-and-error compilation."
        ),
    )
    def inspect_base_template(docx_path: str, lang: str | None = None) -> dict[str, Any]:
        """Return readability, section count, settings and outline for a base template."""
        from md_to_word.template.base_inject import (
            BODY_COMPAT_MODE,
            _compat_mode,
            _effective_even,
            _effective_mirror,
            _effective_punctuation,
            _east_asia_lang,
            inspect_base,
            section_count,
            section_outline,
        )

        path = Path(docx_path).expanduser().resolve()
        message_lang = resolve_lang("", lang)
        if not path.is_file():
            return {
                "ok": False, "path": str(path), "section_count": None,
                "sections": [], "blocking": [f"File not found: {path}"], "notes": [],
                "compat_mode": None, "mirror_margins": None,
                "punctuation_compression": None, "odd_even_headers": None,
                "proofing_language": None,
            }
        report = inspect_base(path, lang=message_lang)
        compat = _compat_mode(path)
        mirror = punctuation = even = proofing = None
        if compat != BODY_COMPAT_MODE:
            key = "base.compat_unknown" if not compat else "base.compat_mismatch"
            report.blocking.append(t(
                key, message_lang,
                base=compat or t("base.common.unset", message_lang),
                body=BODY_COMPAT_MODE,
            ))
        sections: list[str] = []
        count = None
        if report.ok:
            try:
                from docx import Document

                doc = Document(str(path))
                count = section_count(path)
                sections = section_outline(path, message_lang)
                mirror = _effective_mirror(doc.settings.element)
                punctuation = _effective_punctuation(doc.settings.element)
                even = _effective_even(doc.settings.element)
                proofing = _east_asia_lang(doc.styles.element)
            except Exception as exc:  # 结构坏到读不出节：体检已经给过原因，这里不重复抛
                report.notes.append(str(exc))
        return {
            "ok": report.ok,
            "path": str(path),
            "section_count": count,
            "sections": sections,
            "blocking": report.blocking,
            "notes": report.notes,
            "compat_mode": compat or None,
            "mirror_margins": mirror,
            "punctuation_compression": punctuation,
            "odd_even_headers": even,
            "proofing_language": proofing,
        }

    @server.tool(
        name="list_presets",
        title="List Built-in Style Presets",
        description="List every preset that exists on disk, with its path, sha256 and typography summary. The preset directory is the only source of the list.",
    )
    def list_presets(lang: str | None = None) -> list[dict[str, Any]]:
        """List the presets that actually exist, with their fingerprints.

        The preset directory is the only source of the list; `PRESET_METADATA` adds a
        curated note for the built-ins but never invents a preset that is not on disk.
        `lang` picks the display language of the note (`zh` by default).
        """
        import hashlib

        message_lang = resolve_lang("", lang or "zh")
        result = []
        for pid in list_available_presets():
            path = resolve_preset_path(pid)
            if path is None:
                continue
            meta = PRESET_METADATA.get(pid) or {
                "name": f"自定义预设（{pid}）" if message_lang != "en" else f"Custom preset ({pid})",
                "name_en": f"Custom Preset ({pid})",
                "target": "自定义格式文件" if message_lang != "en" else "Custom specification",
                "target_en": "Custom specification",
                "description": f"Preset file at {path}",
                "typography": {},
                "typography_en": {},
            }
            item = _preset_view(meta, message_lang)
            item["id"] = pid
            item["path"] = str(path)
            item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            item["available_on_disk"] = True
            result.append(item)
        return result

    @server.tool(
        name="inspect_preset",
        title="Inspect Style Specification (format.txt)",
        description="Inspect the full format.txt typography specification for a given preset.",
    )
    def inspect_preset(preset: str) -> str:
        """Inspect the raw format.txt specification for a given preset name.

        Args:
            preset: Preset name (e.g. 'zh-academic', 'zh-tw-academic', 'zh-report', 'en-nature').

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
        """Access the manual: `manual://zh` or `manual://en`."""
        return _read_manual(lang)

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
            preset: Target style preset; see `list_presets` for the current names.
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
