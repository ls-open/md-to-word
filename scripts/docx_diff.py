#!/usr/bin/env python3
"""scripts/docx_diff.py — OOXML 语义级对账与对比工具。

直接对比两个 .docx（如 git diff）只会得到 "Binary files differ"；
直接解压对比 XML 会被 Word 随机生成的 `w:rsid*`、`w14:paraId` 和单行压缩格式刷屏。

本脚本：
1. 解压两份 .docx 的目标 XML 部件（默认 word/document.xml，也可选 styles.xml 等）；
2. 递归剥离与排版语义无关的追踪 ID（w:rsid*, w14:paraId, w14:textId 等）；
3. 执行 XML 规范化格式重排（pretty-print）；
4. 输出高可读性的统一差异（Unified Diff）或差异摘要。

用法：
  python3 scripts/docx_diff.py doc1.docx doc2.docx
  python3 scripts/docx_diff.py doc1.docx doc2.docx --part word/styles.xml
  python3 scripts/docx_diff.py doc1.docx doc2.docx --summary
"""

from __future__ import annotations

import argparse
import difflib
import sys
import zipfile
from pathlib import Path
from lxml import etree

# Word 生成的修订与会话追踪属性，对最终版面与内容无任何排版影响
EPHEMERAL_ATTR_PREFIXES = (
    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rsid",
    "{http://schemas.microsoft.com/office/word/2010/wordml}paraId",
    "{http://schemas.microsoft.com/office/word/2010/wordml}textId",
)


def _strip_ephemeral_attrs(elem: etree._Element) -> None:
    """递归移除无排版语义的临时追踪属性。"""
    for key in list(elem.attrib.keys()):
        for prefix in EPHEMERAL_ATTR_PREFIXES:
            if key.startswith(prefix):
                del elem.attrib[key]
                break
    for child in elem:
        _strip_ephemeral_attrs(child)


def normalize_part_xml(docx_path: Path, part_name: str) -> str:
    """读取 docx 内的特定部件，清洗噪声属性并返回规范缩进的 XML 字符串。"""
    try:
        with zipfile.ZipFile(docx_path) as z:
            if part_name not in z.namelist():
                return f"<!-- Part {part_name} not found in {docx_path.name} -->\n"
            data = z.read(part_name)
    except Exception as exc:
        raise RuntimeError(f"无法解压 {docx_path}: {exc}") from exc

    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.fromstring(data, parser)
    _strip_ephemeral_attrs(tree)
    return etree.tostring(tree, pretty_print=True, encoding="utf-8").decode("utf-8")


def colorize_diff(diff_lines: list[str]) -> str:
    """在支持终端输出的 ANSI 彩色 diff。"""
    out = []
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            out.append(f"\033[1m{line}\033[0m")
        elif line.startswith("@@"):
            out.append(f"\033[36m{line}\033[0m")
        elif line.startswith("+"):
            out.append(f"\033[32m{line}\033[0m")
        elif line.startswith("-"):
            out.append(f"\033[31m{line}\033[0m")
        else:
            out.append(line)
    return "\n".join(out)


def diff_docx(
    file_a: Path,
    file_b: Path,
    part_name: str = "word/document.xml",
    summary_only: bool = False,
    color: bool = True,
) -> int:
    """对比两个 docx 的指定 XML 部件。相同返回 0，有差异返回 1。"""
    xml_a = normalize_part_xml(file_a, part_name)
    xml_b = normalize_part_xml(file_b, part_name)

    lines_a = xml_a.splitlines()
    lines_b = xml_b.splitlines()

    diff = list(
        difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=f"{file_a.name}:{part_name}",
            tofile=f"{file_b.name}:{part_name}",
            lineterm="",
        )
    )

    if not diff:
        print(f"✓ [{part_name}] 两份文档规范化后语义完全一致。")
        return 0

    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

    print(f"⚠️ [{part_name}] 发现差异: +{added} 行, -{removed} 行")

    if summary_only:
        return 1

    diff_text = colorize_diff(diff) if (color and sys.stdout.isatty()) else "\n".join(diff)
    print(diff_text)
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OOXML 语义级文档差异对比工具（过滤 Word 随机追踪 ID）"
    )
    parser.add_argument("doc_a", type=Path, help="第一份 .docx 文件路径")
    parser.add_argument("doc_b", type=Path, help="第二份 .docx 文件路径")
    parser.add_argument(
        "--part",
        default="word/document.xml",
        help="待比对的 XML 部件路径（默认 word/document.xml，也可为 word/styles.xml 等）",
    )
    parser.add_argument(
        "--summary", action="store_true", help="只输出差异统计，不打印具体 XML diff"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="禁用彩色高亮输出"
    )

    args = parser.parse_args()

    if not args.doc_a.is_file():
        sys.exit(f"错误: 找不到文件 {args.doc_a}")
    if not args.doc_b.is_file():
        sys.exit(f"错误: 找不到文件 {args.doc_b}")

    code = diff_docx(
        args.doc_a,
        args.doc_b,
        part_name=args.part,
        summary_only=args.summary,
        color=not args.no_color,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
