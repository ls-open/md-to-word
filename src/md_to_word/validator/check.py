"""md_to_word.validator.check — 稿件导前校验门禁。

按后果分两级，判据只有一条：

- **阻断（error）**：产物会静默出错，而且错了看不出来——内容丢字、变成乱码、格式静默不生效。
- **提醒（warning）**：产物看得见，只是不合规——多出一页、宽度被钳、题注离得远、标题跳级。

提醒不阻塞导出：作者可能是有意为之，也可能打算在 Word 里收尾。把这类情况做成硬失败，
只会把人逼去用 `--no-check`，连真正的阻断也一起关掉。
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
from md_to_word.preprocessor.blocks import split_style_line, style_line_issues, style_line_names
from md_to_word.preprocessor.blocks import resolve_style_name
from md_to_word.template.generator import PAGE_SIZES_CM, missing_styles_for_body

# 复用 utils 中的基础文本解析工具
from md_to_word.utils.skill_utils import (
    block_marker_issues,
    soft_wrap_issues,
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


def caption_adjacency_issues(md_text: str) -> list[tuple[int, str]]:
    """题注是否紧邻其实体（表格/图片）——孤立题注在成稿里很明显，提醒即可。

    题注是独立段落（`%% 表题 …` / `%% 图片题注 …`），所以"紧邻"要跨过空行与表注：
    中间只要夹了一句正文，就认为断开。
    """
    masked = mask_code_fences(md_text)
    cleaned = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), masked, flags=re.DOTALL)
    lines = cleaned.split("\n")

    def is_table_row(line: str) -> bool:
        s = line.strip()
        return (s.startswith("|") and s.endswith("|")) or s.startswith("|---")

    def is_image_entity(line: str) -> bool:
        return bool(re.search(r"!\[[^\]]*\]\([^)]*\)", line))

    def kind_of(line: str) -> str | None:
        split = split_style_line(line)
        if split is None:
            return None
        resolved = resolve_style_name(split[0])
        return {
            "Table Caption": "table",
            "Image Caption": "image",
            "Table Note": "note",
        }.get(resolved)

    def scan(start: int, step: int) -> tuple[bool, bool]:
        """从 start 出发单向扫描，遇到正文就停；返回 (见到表格, 见到图片)。"""
        table = image = False
        i = start
        while 0 <= i < len(lines):
            line = lines[i].strip()
            if not line:
                i += step
                continue
            if kind_of(line) == "note":  # 表注夹在题注与表格之间是正常排版
                i += step
                continue
            if is_table_row(line):
                return True, image
            if is_image_entity(line):
                return table, True
            if kind_of(line) is not None:  # 另一条题注：继续，不算断开
                i += step
                continue
            break
        return table, image

    issues: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        kind = kind_of(line)
        if kind not in ("table", "image"):
            continue
        table_near = scan(i - 1, -1)[0] or scan(i + 1, 1)[0]
        image_near = scan(i - 1, -1)[1] or scan(i + 1, 1)[1]
        if kind == "table" and not table_near:
            issues.append((i + 1, "表格题注未紧邻表格（上下均未检测到表格实体），会被排成孤立题注。"))
        elif kind == "image" and not image_near:
            issues.append((i + 1, "图片题注未紧邻图片（上下均未检测到图片实体），会被排成孤立题注。"))
    return issues


def latex_tag_issues(md_text: str) -> list[tuple[int, str]]:
    """`\\tag{}` 不是本技能支持的编号写法，整条公式会退化成字面文本。

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
        ):
            if fm_data.get(key) and en not in declared and en not in reported:
                reported.add(en)
                issues.append((1, f"{feat}，要求文件缺少「{cn}」（{en}）定义，将静默回退默认样式"))
    return issues


def template_style_issues(
    styles_used: dict[str, list[int]], template_path: Path | str
) -> tuple[list[str], list[str]]:
    """稿件用到的段落样式是否真的存在于模板 → (errors, warnings)。

    模板里没有该样式时，写出器只能退成普通段落，格式**静默不生效**。
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
            f"行 {lines[0]} 样式「{style_name}」在模板中不存在，格式不会生效；"
            f"请在格式要求文件里补上这一条，或核对写法"
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

        # 1b2. 写在 YAML 里的内容性字段：引擎只认正文的样式行，这里不静默丢
        for key, form in (
            ("abstract", "`%% 摘要标题 摘要` + 每段一行 `%% 摘要 正文…`"),
            ("keywords", "一行 `%% 关键词 词一；词二`"),
            ("reference-section-title", "一行 `%% 参考文献标题 参考文献`"),
        ):
            if fm_data.get(key):
                message = (
                    f"YAML 的 `{key}` 不参与排版（YAML 管不住位置），正文要写成：{form}。"
                    f"请把内容移到正文，或删掉这个键。"
                )
                if key == "reference-section-title":
                    report.warnings.append(message)
                else:
                    report.valid = False
                    report.errors.append(message)

        # 1c. 未写 csl 的提示（默认样式由 config.default_csl_path 定，两条通道共用）
        if fm_data.get("bibliography") and not fm_data.get("csl"):
            from md_to_word.config import default_csl_path

            report.warnings.append(
                f"未写 csl:，将按默认样式排版：{default_csl_path(md_text).name}"
                "（中文稿 GB/T 7714 数字制，英文稿 APA）；如需其他样式请写 csl:。"
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
                    f"不处理会把这几个字符原样印进 docx。本技能只支持由 .bib 生成文献列表："
                    f"在 YAML 里加 `bibliography: refs.bib`（配合 `csl:` 选样式），"
                    f"若只是想展示语法字面量，用反引号包起来"
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

    # 7. 分节符后又写分页：多顶出一页空白。看得见，只提醒
    for line_no, why in section_pagebreak_issues(md_text):
        report.warnings.append(f"行 {line_no} [分节标记]: {why}")

    # 8. 标题层级：跳级会让大纲级别错位，但内容与样式都还在，提醒即可
    for line_no, why in heading_and_div_issues(md_text):
        report.warnings.append(f"行 {line_no} [标题/分级]: {why}")

    # 9. 交叉引用前缀：要求文件声明了中文校对语言时，导出阶段会补默认前缀，
    #    这里只提示、不阻断（否则「自动补」永远走不到渲染那一步）
    auto_prefix = spec is not None and (spec.proofing_lang or "").lower().startswith("zh")
    for line_no, why in crossref_prefix_issues(md_text, fm_data):
        if auto_prefix:
            report.warnings.append(
                f"行 {line_no} [交叉引用前缀]: {why}；导出时会按「式/图/表」自动补上"
            )
        else:
            # 不写前缀会渲染成 Equation 1（中英混排），但内容没错，提醒即可
            report.warnings.append(
                f"行 {line_no} [交叉引用前缀]: {why}；不加要求文件里声明中文校对语言即可自动补"
            )

    # 10. 未定义交叉引用标签
    for line_no, why in undefined_crossref_issues(md_text):
        report.valid = False
        report.errors.append(f"行 {line_no} [交叉引用缺失目标]: {why}")

    # 11. 畸变表格
    for line_no, why in malformed_table_issues(md_text):
        report.valid = False
        report.errors.append(f"行 {line_no} [表格格式异常]: {why}")

    # 12. 图表题注邻近性：题注离表格/图片远了，样式仍会生效，只是位置不对，提醒即可
    for line_no, why in caption_adjacency_issues(md_text):
        report.warnings.append(f"行 {line_no} [图表题注邻近性]: {why}")

    # 12b. 折行段落：按「一行一段」读取会拆成几段，每段都吃一次首行缩进，看得见但内容没丢
    for line_no, snippet in soft_wrap_issues(md_text):
        report.warnings.append(
            f"行 {line_no} [折行段落]: 上一行没有句末标点而本行紧随其后（「{snippet}」）；"
            f"本引擎按「一行一段」读取，会拆成两段。若本意是同一段，请合并到一行"
        )

    # 13. `\tag{}` 公式编号（不认这个写法，整条公式退化成字面文本）
    for line_no, snippet in latex_tag_issues(md_text):
        report.valid = False
        report.errors.append(
            f"行 {line_no} [公式编号]: 发现 `\\tag{{}}`，这不是本技能的编号写法，整条公式会退化成字面文本（{snippet}）；"
            f"删掉 `\\tag{{X}}`，改写成 `$$…$$ {{#eq-标签}}`，编号由 crossref 生成"
        )

    # 14/15. 依赖格式要求文件的两道门禁
    if spec is not None:
        # 14. 图片声明宽度超过版心：会被钳到版心宽，但图还在页内，提醒即可
        width_cm = content_width_cm(spec)
        if width_cm:
            for line_no, why in image_width_issues(md_text, width_cm):
                report.warnings.append(f"行 {line_no} [图片宽度超过版心]: {why}")
        elif has_declared_image_width(md_text):
            report.warnings.append("要求文件没写页边距，算不出版心，图片宽度未校验")

        # 15. 稿件结构 vs 要求文件声明的样式（缺一条就静默回退默认样式）
        for line_no, why in required_style_issues(md_text, spec, fm_data):
            report.valid = False
            report.errors.append(f"行 {line_no} [结构样式缺失]: {why}")

    # 15b. `:::` 不是本技能的写法
    for line_no, line in enumerate(mask_code_fences(md_text).split("\n"), 1):
        if re.match(r"^\s*:::", line):
            report.valid = False
            report.errors.append(
                f"行 {line_no} [段落样式]: `:::` 不是本技能的写法。"
                f"需要段落样式就写成一行 `%% 样式名 内容`；文献列表由引擎放在文末，不需要定位标记。"
            )

    # 15c. 题注写进图片的方括号里：方括号只放无障碍替代文字
    for line_no, line in enumerate(mask_code_fences(md_text).split("\n"), 1):
        m = re.search(r"!\[([^\]]+)\]\(", line)
        if m and re.match(r"^\s*(?:图|表|Figure|Table)\s*\d", m.group(1)):
            report.valid = False
            report.errors.append(
                f"行 {line_no} [图片题注]: 方括号里的文字是无障碍替代文字，不会被排成题注。"
                f"题注另起一行：`%% 图片题注 {m.group(1).strip()}`（写在图片上方或下方都可），"
                f"`![](…)` 的方括号留空或写一句替代文字"
            )

    # 15d. 文献区标题：列表是引擎生成的，标题得稿子里写，两种写法都认
    if isinstance(fm_data, dict) and fm_data.get("bibliography"):
        has_style_title = bool(re.search(r"^%%\s*参考文献标题\s", md_text, re.M))
        has_heading = bool(
            re.search(r"^#{1,6}\s*(?:参考文献|参考书目|References|Bibliography)\s*$", md_text, re.M)
        )
        if not (has_style_title or has_heading):
            report.warnings.append(
                "有 bibliography 但正文没写文献区标题：在文末补一行 `%% 参考文献标题 参考文献`"
                "（或 `# 参考文献` 标题），否则生成的文献列表没有抬头"
            )

    # 16. 段落样式行 `%% 样式名 内容`
    for line_no, why in style_line_issues(md_text):
        report.valid = False
        report.errors.append(f"行 {line_no} [段落样式]: {why}")

    # 17. custom-style 是否真的存在于模板（没给模板就跳过，由对账阶段兜底）
    styles_used: dict[str, list[int]] = {}
    for line_no, resolved in style_line_names(md_text):
        if resolved:
            styles_used.setdefault(resolved, []).append(line_no)
    if styles_used and template_docx is not None:
        errors, warnings = template_style_issues(styles_used, template_docx)
        if errors:
            report.valid = False
            report.errors.extend(f"[custom-style] {e}" for e in errors)
        report.warnings.extend(warnings)

    return report
