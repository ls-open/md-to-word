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
from md_to_word.template.generator import PAGE_SIZES_CM, missing_styles_for_body

# 复用 utils 中的基础文本解析工具
from md_to_word.utils.skill_utils import (
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


def caption_adjacency_issues(md_text: str) -> list[tuple[int, str]]:
    """检查表格题注与图片题注是否紧邻其实体（表格/图片），防止孤立题注。"""
    masked = mask_code_fences(md_text)

    # 屏蔽多行 HTML 注释（用等量换行符保持行号对齐）
    def _repl_comment(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")

    cleaned = re.sub(r"<!--.*?-->", _repl_comment, masked, flags=re.DOTALL)
    lines = cleaned.split("\n")
    n = len(lines)
    issues: list[tuple[int, str]] = []

    def is_table_row(line: str) -> bool:
        s = line.strip()
        return (s.startswith("|") and s.endswith("|")) or s.startswith("|---") or bool(re.match(r"^\+[-=+]+\+$", s))

    def is_image_entity(line: str) -> bool:
        s = line.strip()
        return bool(re.search(r"!\[.*?\]\(.*?\)", s) or re.search(r"<img\s+[^>]*src=", s, re.I))

    def is_structural_wrapper(line: str) -> bool:
        s = line.strip()
        if not s or s == ":::":
            return True
        if re.match(r"^:::\s*\{.*\}$", s):
            return True
        if re.match(r"^\{#tbl-[^}]+\}$", s) or re.match(r"^\{#fig-[^}]+\}$", s):
            return True
        return False

    def skip_table_note_backward(curr_idx: int) -> int:
        idx = curr_idx
        if lines[idx].strip() == ":::":
            k = idx - 1
            while k >= 0:
                l_str = lines[k].strip()
                if "Table Note" in l_str or "表注" in l_str or "表格附注" in l_str:
                    return k - 1
                if l_str.startswith("#") or is_table_row(l_str):
                    break
                k -= 1
        return curr_idx

    def skip_table_note_forward(curr_idx: int) -> int:
        l_str = lines[curr_idx].strip()
        if "Table Note" in l_str or "表注" in l_str or "表格附注" in l_str:
            k = curr_idx + 1
            while k < n:
                if lines[k].strip() == ":::":
                    return k + 1
                k += 1
        return curr_idx

    def look_back(start_idx: int) -> tuple[bool, bool]:
        found_table = False
        found_image = False
        i = start_idx - 1
        while i >= 0:
            line = lines[i].strip()
            if not line:
                i -= 1
                continue
            new_i = skip_table_note_backward(i)
            if new_i != i:
                i = new_i
                continue
            if is_table_row(line):
                found_table = True
                break
            if is_image_entity(line):
                found_image = True
                break
            if is_structural_wrapper(line):
                i -= 1
                continue
            # 普通正文/标题等非容器结构，立即停止，严禁穿透正文
            break
        return found_table, found_image

    def look_forward(end_idx: int) -> tuple[bool, bool]:
        found_table = False
        found_image = False
        i = end_idx + 1
        while i < n:
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            new_i = skip_table_note_forward(i)
            if new_i != i:
                i = new_i
                continue
            if is_table_row(line):
                found_table = True
                break
            if is_image_entity(line):
                found_image = True
                break
            if is_structural_wrapper(line):
                i += 1
                continue
            # 普通正文/标题等非容器结构，立即停止
            break
        return found_table, found_image

    i = 0
    while i < n:
        line = lines[i].strip()
        m_tbl = re.search(r'custom-style=["\'](Table Caption|表格题注|表名|表题)["\']', line, re.I)
        m_img = re.search(r'custom-style=["\'](Image Caption|图片题注|图名|图题)["\']', line, re.I)
        m_pandoc_tbl = re.search(r"^:\s+.*\{#tbl-", line)

        if m_tbl or m_img or m_pandoc_tbl:
            start_i = i
            end_i = i
            if m_tbl or m_img:
                j = i + 1
                while j < n:
                    if lines[j].strip() == ":::":
                        end_i = j
                        break
                    j += 1

            if m_tbl or m_pandoc_tbl:
                tbl_before, _ = look_back(start_i)
                tbl_after, _ = look_forward(end_i)
                if not (tbl_before or tbl_after):
                    issues.append(
                        (
                            start_i + 1,
                            "表格题注未紧邻表格（上下均未检测到表格实体）。表格题注必须置于对应表格紧邻的上方或下方。",
                        )
                    )
            elif m_img:
                _, img_before = look_back(start_i)
                _, img_after = look_forward(end_i)
                if not (img_before or img_after):
                    issues.append(
                        (
                            start_i + 1,
                            "图片题注未紧邻图片（上下均未检测到图片实体）。图片题注必须置于对应图片紧邻的下方或上方。",
                        )
                    )
            i = end_i + 1
            continue
        i += 1

    return issues


def latex_tag_issues(md_text: str) -> list[tuple[int, str]]:
    """`\\tag{}` 不是 Pandoc 语法，整条公式会退化成字面文本。

    公式编号只有 `{#eq-xxx}` 一种写法；写错就拦下，不做自动转换。
    """
    issues: list[tuple[int, str]] = []
    for i, line in enumerate(mask_code_fences(md_text).split("\n"), 1):
        if re.search(r"\\tag\s*\{", line):
            issues.append((i, line.strip()[:80]))
    return issues


def content_width_cm(spec: TemplateSpec) -> Optional[float]:
    """版心宽度（cm）= 纸张宽 − 左页边距 − 右页边距 − 装订线。取不到页边距时返回 None。"""
    if not spec.margins:
        return None
    width = PAGE_SIZES_CM.get(spec.page_size, PAGE_SIZES_CM["a4"])[0]
    return width - spec.margins["left"] - spec.margins["right"] - (spec.gutter_cm or 0)


def required_style_issues(md_text: str, spec: TemplateSpec, fm_data) -> list[tuple[int, str]]:
    """稿件用到了结构、要求文件却没声明对应样式 → 导出会静默回退默认样式。

    这是本技能最要紧的一道门禁：产物外观正常，但格式根本没映射上。
    """
    declared = {s.get("style_name") for s in spec.styles}
    if spec.table:
        declared.add("__ROW_table__")
    if spec.table_header:
        declared.add("__ROW_table_header__")

    _, body = split_frontmatter(md_text)
    start_line = md_text.count("\n") - body.count("\n") + 1
    issues: list[tuple[int, str]] = []
    reported: set[str] = set()
    for line_no, feat, cn, en in missing_styles_for_body(
        mask_code_fences(body), declared, start_line=start_line
    ):
        reported.add(en)
        label = f"「{cn}：…」配置行" if en.startswith("__ROW_") else f"「{cn}」（{en}）定义"
        issues.append((line_no, f"用到了 {feat}，要求文件缺少 {label}，将静默回退默认样式"))

    if isinstance(fm_data, dict):
        for key, cn, en, feat in (
            ("bibliography", "参考文献", "Bibliography", "YAML bibliography 文献库"),
            ("abstract", "摘要", "Abstract", "YAML abstract 摘要"),
        ):
            if fm_data.get(key) and en not in declared and en not in reported:
                reported.add(en)
                issues.append((1, f"{feat}，要求文件缺少「{cn}」（{en}）定义，将静默回退默认样式"))
    return issues


def template_style_issues(
    styles_used: dict[str, list[int]], template_path: Path | str
) -> tuple[list[str], list[str]]:
    """`custom-style="X"` 用到的样式是否真的存在于模板 → (errors, warnings)。

    模板里没有该样式时 Quarto **静默建一个空壳样式**，格式不生效。
    """
    template = Path(template_path)
    if not template.is_file():
        return [f"模板不存在: {template}"], []
    try:
        with zipfile.ZipFile(template) as archive:
            root = etree.fromstring(archive.read("word/styles.xml"))
    except (KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        return [f"模板存在但读不出样式表（{exc}）: {template}"], []

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    names: set[str] = set()
    ids: set[str] = set()
    for style in root.findall(f"{ns}style"):
        style_id = style.get(f"{ns}styleId")
        if style_id:
            ids.add(style_id)
        name = style.find(f"{ns}name")
        if name is not None and name.get(f"{ns}val"):
            names.add(name.get(f"{ns}val"))

    errors: list[str] = []
    for style_name, lines in sorted(styles_used.items()):
        if style_name in names or style_name in ids:
            continue
        errors.append(
            f"行 {lines[0]} custom-style「{style_name}」在模板中不存在，"
            f"Quarto 会静默建空壳样式，格式不生效；请在模板中创建该样式或核对拼写"
        )
    return errors, []


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

    # 0. 格式要求（有要求文件才谈得上「稿件结构是否有对应样式」）
    if spec is None and spec_path is not None:
        req_file = Path(spec_path)
        if not req_file.is_file():
            report.valid = False
            report.errors.append(f"格式要求文件不存在: {req_file}")
            return report
        try:
            spec = parse_requirements(req_file.read_text(encoding="utf-8"))
        except Exception as e:
            report.valid = False
            report.errors.append(f"格式要求文件解析失败（{req_file}）: {e}")
            return report

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
                    f"正文有 {len(bare_cites)} 处 `[@key]` 引用语法，但稿件未声明 `bibliography:`（{shown}）；"
                    f"不处理会把这几个字符原样印进 docx。三种处理方式（按现有习惯选其一）："
                    f"① 在 YAML 加 `bibliography: refs.bib`；"
                    f"② 改为手写编号（如 `[1]`），文末按手写文献排版；"
                    f"③ 仅需展示语法字面量时用反引号包成行内代码"
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

    # 12. 图表题注邻近性检查（防止孤立题注与表格/图片脱节）
    for line_no, why in caption_adjacency_issues(md_text):
        report.valid = False
        report.errors.append(f"行 {line_no} [图表题注邻近性]: {why}")

    # 13. `\tag{}` 公式编号（Pandoc 不认，整条公式退化成字面文本）
    for line_no, snippet in latex_tag_issues(md_text):
        report.valid = False
        report.errors.append(
            f"行 {line_no} [公式编号]: 发现 `\\tag{{}}`，Pandoc 不认这个语法，整条公式会退化成字面文本（{snippet}）；"
            f"删掉 `\\tag{{X}}`，改写成 `$$…$$ {{#eq-标签}}`，编号由 crossref 生成"
        )

    # 14/15. 依赖格式要求文件的两道门禁
    if spec is not None:
        # 14. 图片声明宽度超过版心（导出时被静默钳到版心宽，不报错）
        width_cm = content_width_cm(spec)
        if width_cm:
            for line_no, why in image_width_issues(md_text, width_cm):
                report.valid = False
                report.errors.append(f"行 {line_no} [图片宽度超过版心]: {why}")
        elif has_declared_image_width(md_text):
            report.warnings.append("要求文件没写页边距，算不出版心，图片宽度未校验")

        # 15. 稿件结构 vs 要求文件声明的样式（缺一条就静默回退默认样式）
        for line_no, why in required_style_issues(md_text, spec, fm_data):
            report.valid = False
            report.errors.append(f"行 {line_no} [结构样式缺失]: {why}")

    # 16. custom-style 是否真的存在于模板（没给模板就跳过，由对账阶段兜底）
    styles_used = extract_custom_styles(md_text)
    if styles_used and template_docx is not None:
        errors, warnings = template_style_issues(styles_used, template_docx)
        if errors:
            report.valid = False
            report.errors.extend(f"[custom-style] {e}" for e in errors)
        report.warnings.extend(warnings)

    return report
