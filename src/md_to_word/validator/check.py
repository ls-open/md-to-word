"""md_to_word.validator.check — 稿件导前硬校验门禁。

导出前检查 Markdown 稿件中可能导致静默失败、样式丢失或格式错位的结构性问题。
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from lxml import etree
import yaml

from md_to_word.config import get_csl_dir
from md_to_word.spec.models import TemplateSpec
from md_to_word.spec.parser import parse_requirements

# 复用 skill_utils 中的基础文本解析工具
from skill_utils import (
    block_marker_issues,
    citation_key_issues,
    citations_without_bibliography,
    crossref_prefix_issues,
    has_declared_image_width,
    heading_and_div_issues,
    image_width_issues,
    malformed_table_issues,
    mask_code_fences,
    parse_bib_keys,
    resolve_manuscript_path,
    section_pagebreak_issues,
    split_frontmatter,
    undefined_crossref_issues,
    unknown_shortcode_issues,
)


@dataclass
class ValidationReport:
    """导前校验结果报告。"""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def extract_custom_styles(md_text: str) -> dict[str, list[int]]:
    """提取 MD 里所有 custom-style="X" 的样式名（去重，保留出现行号）。"""
    found: dict[str, list[int]] = {}
    in_code_block = False
    for i, line in enumerate(md_text.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
        if in_code_block:
            continue
        for match in re.finditer(r'custom-style=["\']([^"\']+)["\']', line):
            style = match.group(1)
            found.setdefault(style, []).append(i)
    return found


def validate_manuscript(
    md_path: Path | str,
    *,
    template_docx: Optional[Path | str] = None,
    spec: Optional[TemplateSpec] = None,
    spec_path: Optional[Path | str] = None,
    csl_dir: Optional[Path] = None,
) -> ValidationReport:
    """对稿件进行全套严格校验，返回 ValidationReport。"""
    md_path = Path(md_path)
    report = ValidationReport()

    if not md_path.exists():
        report.valid = False
        report.errors.append(f"稿件文件不存在: {md_path}")
        return report

    try:
        md_text = md_path.read_text(encoding="utf-8")
    except Exception as e:
        report.valid = False
        report.errors.append(f"无法读取稿件 {md_path}: {e}")
        return report

    csl_dir = csl_dir or get_csl_dir()

    # 1. Frontmatter 检查
    fm_raw, body_text = split_frontmatter(md_text)
    fm_offset = md_text.count("\n") - body_text.count("\n")
    fm_data = {}
    if fm_raw:
        try:
            fm_data = yaml.safe_load(fm_raw) or {}
        except Exception as e:
            report.valid = False
            report.errors.append(f"YAML frontmatter 解析失败: {e}")

    if isinstance(fm_data, dict):
        # 1a. bibliography 路径
        if fm_data.get("bibliography"):
            bib_path, how = resolve_manuscript_path(str(fm_data["bibliography"]), md_path)
            if not how:
                report.valid = False
                report.errors.append(f"文献库不存在: {fm_data['bibliography']}")

        # 1b. csl 路径
        if fm_data.get("csl"):
            csl_path, how = resolve_manuscript_path(str(fm_data["csl"]), md_path, csl_dir)
            if not how:
                report.valid = False
                report.errors.append(f"CSL 样式文件不存在: {fm_data['csl']}")

        # 1c. 未写 csl 的提示
        if fm_data.get("bibliography") and not fm_data.get("csl"):
            report.warnings.append(
                "未写 csl:，参考文献将走 Pandoc 默认的作者-年份制（如 (Smith, 2024)）；"
                "中文稿如需 [1] 编号，请写 csl: chinese-gb7714-2015-numeric.csl。"
            )

        # 1d. 正文引用的 key 是否在 .bib 里
        if fm_data.get("bibliography"):
            bib_path, how = resolve_manuscript_path(str(fm_data["bibliography"]), md_path)
            if how:
                try:
                    bib_text = Path(bib_path).read_text(encoding="utf-8")
                except Exception:
                    bib_text = ""
                known_keys = parse_bib_keys(bib_text)
                if not known_keys:
                    bare = citations_without_bibliography(body_text, fm_offset)
                    if bare:
                        report.valid = False
                        report.errors.append(
                            f"文献库 {Path(bib_path).name} 里一条条目都没有，但正文有 {len(bare)} 处引用"
                        )
                cite_issues = citation_key_issues(body_text, known_keys, fm_offset)
                if cite_issues:
                    report.valid = False
                    for line_no, why in cite_issues:
                        report.errors.append(f"行 {line_no} [引文 key 缺失]: {why}")
        else:
            bare_cites = citations_without_bibliography(body_text, fm_offset)
            if bare_cites:
                report.valid = False
                shown = "、".join(f"行 {n}" for n in bare_cites[:5])
                report.errors.append(
                    f"正文有 {len(bare_cites)} 处 `[@key]` 引用语法，但稿件未声明 `bibliography:`（{shown}）。"
                )

    # 2. 图片路径空格与存在性
    in_code = False
    for i, line in enumerate(md_text.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code = not in_code
        if in_code:
            continue
        for m in re.finditer(r"!\[(.*?)\]\((.*?)\)", line):
            raw_path = m.group(2).strip()
            # 过滤网络链接
            if raw_path.startswith(("http://", "https://", "data:")):
                continue
            # 空格检查
            if " " in raw_path and not raw_path.startswith("<") and not re.search(r'["\'].*["\']', raw_path):
                report.valid = False
                report.errors.append(f"行 {i}: 图片路径含未转义空格「{raw_path}」")
            # 存在性检查
            clean_path = raw_path.split()[0].strip("<>\"'")
            img_file = md_path.parent / clean_path
            if not img_file.exists():
                report.valid = False
                report.errors.append(f"行 {i}: 图片文件不存在「{clean_path}」")

    # 3. Obsidian WikiLinks
    for i, line in enumerate(md_text.split("\n"), 1):
        if re.search(r"!\[\[.*?\]\]|\[\[.*?\]\]", line):
            report.valid = False
            report.errors.append(f"行 {i}: 发现未转换的 Obsidian WikiLink 语法（请改用标准 Markdown 链接）")

    # 4. LaTeX 分页符
    for i, line in enumerate(md_text.split("\n"), 1):
        if re.search(r"\\(?:newpage|pagebreak|clearpage)", line):
            report.valid = False
            report.errors.append(f"行 {i}: 发现 LaTeX 分页命令（请改用 `{{{{< pagebreak >}}}}`）")

    # 5. 块级标记空行分隔
    for line_no, why in block_marker_issues(md_text):
        report.valid = False
        report.errors.append(f"行 {line_no} [块级标记空行缺失]: {why}")

    # 6. 未知短代码
    for line_no, why in unknown_shortcode_issues(md_text):
        report.valid = False
        report.errors.append(f"行 {line_no} [未知短代码]: {why}")

    # 7. 分节符前后页码
    for line_no, why in section_pagebreak_issues(md_text):
        report.valid = False
        report.errors.append(f"行 {line_no} [分节标记]: {why}")

    # 8. 标题层级与 custom-style 容器
    for line_no, why in heading_and_div_issues(md_text):
        report.valid = False
        report.errors.append(f"行 {line_no} [标题/分级]: {why}")

    # 9. 交叉引用前缀
    for line_no, why in crossref_prefix_issues(md_text, fm_data):
        report.valid = False
        report.errors.append(f"行 {line_no} [交叉引用前缀]: {why}")

    # 10. 未定义交叉引用标签
    for line_no, why in undefined_crossref_issues(md_text):
        report.valid = False
        report.errors.append(f"行 {line_no} [交叉引用缺失目标]: {why}")

    # 11. 畸变表格
    for line_no, why in malformed_table_issues(md_text):
        report.valid = False
        report.errors.append(f"行 {line_no} [表格格式异常]: {why}")

    return report
