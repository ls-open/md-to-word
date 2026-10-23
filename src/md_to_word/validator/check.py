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
from md_to_word.i18n import t
from md_to_word.spec.constants import ROW_NAME_EN
from md_to_word.spec.models import TemplateSpec
from md_to_word.spec.parser import parse_requirements
from md_to_word.preprocessor.blocks import split_style_line, style_line_issues, style_line_names
from md_to_word.preprocessor.blocks import resolve_style_name
from md_to_word.template.generator import PAGE_SIZES_CM, missing_styles_for_body
from md_to_word.utils.pdf_figure import PDF_SUFFIX, RASTER_SUFFIXES, PdfFigureError, page_count

# 复用 utils 中的基础文本解析工具
from md_to_word.utils.skill_utils import (
    block_marker_issues,
    soft_wrap_issues,
    citation_key_issues,
    citations_without_bibliography,
    dialect_issues,
    has_declared_image_width,
    heading_issues,
    image_width_issues,
    malformed_table_issues,
    mask_code_fences,
    parse_bib_keys,
    resolve_manuscript_path,
    section_pagebreak_issues,
    split_frontmatter,
    unbalanced_math_issues,
    undefined_crossref_issues,
    unknown_shortcode_issues,
)


_GROUP_LIMIT = 8  # 一类提醒最多列这么多个行号，其余只报数量


def _group_warn(report: ValidationReport, tag: str, items: list[tuple[int, str]], lang: str) -> None:
    """同一类提醒合并成一条：一处照旧逐行说，多处只列行号。

    门禁的提醒是按行产生的，一稿折行三十处就会刷三十行，真正要紧的东西被冲掉。
    合并后每类只有一条，行号照给，改起来一样清楚。
    """
    if not items:
        return
    if len(items) == 1:
        report.warnings.append(
            t("gate.line", lang, line=items[0][0], tag=tag, why=items[0][1])
        )
        return
    sep = t("gate.list_sep", lang)
    lines = sep.join(str(line_no) for line_no, _ in items[:_GROUP_LIMIT])
    if len(items) > _GROUP_LIMIT:
        lines += t("gate.line_more", lang, count=len(items) - _GROUP_LIMIT)
    report.warnings.append(
        t("gate.line_grouped", lang, tag=tag, count=len(items), lines=lines, why=items[0][1])
    )

@dataclass
class ValidationReport:
    """导前校验结果报告。"""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def caption_adjacency_issues(md_text: str, lang: str = "zh") -> list[tuple[int, str]]:
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
            issues.append((i + 1, t("gate.caption.table_far", lang)))
        elif kind == "image" and not image_near:
            issues.append((i + 1, t("gate.caption.image_far", lang)))
    return issues


def latex_tag_issues(md_text: str) -> list[tuple[int, str]]:
    """`\\tag{}` 不是本工具支持的编号写法，整条公式会退化成字面文本。

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


def required_style_issues(
    md_text: str, spec: TemplateSpec, fm_data, lang: str = "zh"
) -> list[tuple[int, str]]:
    """稿件用到了结构、要求文件却没声明对应样式 → 导出会静默回退默认样式。

    这是本工具最要紧的一道门禁：产物外观正常，但格式根本没映射上。
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
        mask_code_fences(body), declared, start_line=start_line, lang=lang
    ):
        reported.add(en)
        label = (
            # 配置行（「表格：…」/「表头：…」）没有 Word 样式名可回显，英文稿另给一份名字
            t("gate.label.row_settings", lang, name=cn if lang != "en" else ROW_NAME_EN.get(cn, cn))
            if en.startswith("__ROW_")
            else t("gate.label.style_def", lang, cn=cn, en=en)
        )
        issues.append((line_no, t("gate.style.required_missing", lang, feat=feat, label=label)))

    if isinstance(fm_data, dict):
        for key, cn, en, feat_key in (
            ("bibliography", "参考文献", "Bibliography", "gate.feat.bibliography_yaml"),
        ):
            if fm_data.get(key) and en not in declared and en not in reported:
                reported.add(en)
                issues.append((
                    1,
                    t("gate.bib.required_missing", lang, cn=cn, en=en, feat=t(feat_key, lang)),
                ))
    return issues


def template_style_issues(
    styles_used: dict[str, list[int]], template_path: Path | str, lang: str = "zh"
) -> tuple[list[str], list[str]]:
    """稿件用到的段落样式是否真的存在于模板 → (errors, warnings)。

    模板里没有该样式时，写出器只能退成普通段落，格式**静默不生效**。
    """
    template = Path(template_path)
    if not template.is_file():
        return [t("gate.template.missing", lang, path=template)], []
    try:
        with zipfile.ZipFile(template) as archive:
            root = etree.fromstring(archive.read("word/styles.xml"))
    except (KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        return [t("gate.template.unreadable", lang, err=exc, path=template)], []

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    names: set[str] = set()
    ids: set[str] = set()
    for style in root.findall(f"{ns}style"):
        style_id = style.get(f"{ns}styleId")
        if style_id:
            ids.add(style_id.casefold())
        name = style.find(f"{ns}name")
        if name is not None and name.get(f"{ns}val"):
            names.add(name.get(f"{ns}val").casefold())

    errors: list[str] = []
    for style_name, lines in sorted(styles_used.items()):
        if style_name.casefold() in names or style_name.casefold() in ids:
            continue
        errors.append(
            t("gate.template.style_absent", lang, line=lines[0], name=style_name)
        )
    return errors, []


def validate_manuscript(
    md_path: Path | str,
    *,
    template_docx: Optional[Path | str] = None,
    spec: Optional[TemplateSpec] = None,
    spec_path: Optional[Path | str] = None,
    csl_dir: Optional[Path] = None,
    lang: str = "zh",
) -> ValidationReport:
    """对稿件进行全套严格校验，返回 ValidationReport。

    `lang` 决定报错语言（"zh"/"en"），默认中文——中文串是既有测试与既有用户的契约，
    英文只是新增的一条路径。判据、阈值、阻断/提醒的划分与语言无关。
    """
    md_path = Path(md_path)
    report = ValidationReport()

    if not md_path.exists():
        report.valid = False
        report.errors.append(t("gate.manuscript.missing", lang, path=md_path))
        return report

    try:
        md_text = md_path.read_text(encoding="utf-8")
    except Exception as e:
        report.valid = False
        report.errors.append(t("gate.manuscript.unreadable", lang, path=md_path, err=e))
        return report

    csl_dir = csl_dir or get_csl_dir()

    # 0. 格式要求（有要求文件才谈得上「稿件结构是否有对应样式」）
    if spec is None and spec_path is not None:
        req_file = Path(spec_path)
        if not req_file.is_file():
            report.valid = False
            report.errors.append(t("gate.requirements.missing", lang, path=req_file))
            return report
        try:
            spec = parse_requirements(req_file.read_text(encoding="utf-8"))
        except Exception as e:
            report.valid = False
            report.errors.append(
                t("gate.requirements.parse_failed", lang, path=req_file, err=e)
            )
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
            report.errors.append(t("gate.yaml.parse_failed", lang, err=e))

    if isinstance(fm_data, dict):
        # 1a. bibliography 路径
        if fm_data.get("bibliography"):
            bib_path, how = resolve_manuscript_path(str(fm_data["bibliography"]), md_path)
            if not how:
                report.valid = False
                report.errors.append(
                    t("gate.bib.missing", lang, path=fm_data["bibliography"])
                )

        # 1b. csl 路径
        if fm_data.get("csl"):
            csl_path, how = resolve_manuscript_path(str(fm_data["csl"]), md_path, csl_dir)
            if not how:
                report.valid = False
                report.errors.append(t("gate.csl.missing", lang, path=fm_data["csl"]))

        # 1b2. 写在 YAML 里的内容性字段：引擎只认正文的样式行，这里不静默丢。
        # 判据是「位置」——标题、副标题、作者、日期、摘要、关键词各自该落在哪一页哪一段，
        # 由作者决定；YAML 没有位置，写在那里等于被钉死在正文最前面。
        for key, form_key in (
            ("title", "gate.yaml.form.title"),
            ("subtitle", "gate.yaml.form.subtitle"),
            ("author", "gate.yaml.form.author"),
            ("date", "gate.yaml.form.date"),
            ("abstract", "gate.yaml.form.abstract"),
            ("keywords", "gate.yaml.form.keywords"),
            ("reference-section-title", "gate.yaml.form.reference_section_title"),
        ):
            if fm_data.get(key):
                message = t("gate.yaml.key_unused", lang, key=key, form=t(form_key, lang))
                if key == "reference-section-title":
                    report.warnings.append(message)
                else:
                    report.valid = False
                    report.errors.append(message)

        # 1c. 未写 csl 的提示（默认样式由 config.default_csl_path 决定）
        if fm_data.get("bibliography") and not fm_data.get("csl"):
            from md_to_word.config import default_csl_path

            report.warnings.append(
                t("gate.csl.default", lang, name=default_csl_path(md_text).name)
            )

        # 1c2. `[-@key]`（只出年份）：引擎不实现，静默当普通引用就等于改写了作者的话
        for line_no, line in enumerate(mask_code_fences(md_text).split("\n"), 1):
            if re.search(r"\[-@[\w:.-]+", line):
                report.valid = False
                report.errors.append(t("gate.citation.suppress_author", lang, line=line_no))

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
                            t("gate.bib.empty", lang,
                              name=Path(bib_path).name, count=len(bare))
                        )
                cite_issues = citation_key_issues(body_text, known_keys, fm_offset, lang)
                if cite_issues:
                    report.valid = False
                    for line_no, why in cite_issues:
                        report.errors.append(
                            t("gate.line", lang,
                              line=line_no, tag=t("gate.tag.citation_key", lang), why=why)
                        )
        else:
            bare_cites = citations_without_bibliography(body_text, fm_offset)
            if bare_cites:
                report.valid = False
                sep = t("gate.list_sep", lang)
                shown = sep.join(t("gate.line_item", lang, line=n) for n in bare_cites[:5])
                report.errors.append(
                    t("gate.citation.no_bibliography", lang,
                      count=len(bare_cites), shown=shown)
                )

    # 1e. 编号格式用了 {c}（章号），稿件却没说按章编号：两个文件各写一半，等式不成立
    eq_format = getattr(spec, "equation_number_format", "") or ""
    if "{c}" in eq_format:
        crossref = fm_data.get("crossref") if isinstance(fm_data, dict) else None
        by_chapter = isinstance(crossref, dict) and bool(crossref.get("chapters"))
        if not by_chapter:
            report.valid = False
            report.errors.append(t("gate.equation.chapters", lang, fmt=eq_format))

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
                report.errors.append(t("gate.image.path_space", lang, line=i, path=raw_path))
            # 存在性检查
            clean_path = raw_path.split()[0].strip("<>\"'")
            img_file = md_path.parent / clean_path
            if not img_file.exists():
                report.valid = False
                report.errors.append(t("gate.image.missing", lang, line=i, path=clean_path))
                continue
            # 格式检查：Word 的内联图片只认位图，PDF 由导出流程在渲染阶段转成位图。
            # 其余格式（svg、webp、eps…）python-docx 会抛 UnrecognizedImageError——
            # 一屏 traceback、没有行号，所以在这里拦下并给出改法。
            suffix = img_file.suffix.lower()
            if suffix == PDF_SUFFIX:
                try:
                    pages = page_count(img_file)
                except PdfFigureError as exc:
                    report.valid = False
                    report.errors.append(
                        t("gate.image.pdf_unreadable", lang, line=i, path=clean_path, err=exc)
                    )
                else:
                    if pages > 1:
                        report.warnings.append(
                            t("gate.image.pdf_multipage", lang, line=i, path=clean_path, pages=pages)
                        )
            elif suffix not in RASTER_SUFFIXES:
                report.valid = False
                report.errors.append(
                    t("gate.image.unsupported", lang, line=i, path=clean_path, ext=suffix or "（无扩展名）")
                )

    # 3. Obsidian WikiLinks
    for i, line in enumerate(md_text.split("\n"), 1):
        if re.search(r"!\[\[.*?\]\]|\[\[.*?\]\]", line):
            report.valid = False
            report.errors.append(t("gate.wikilink", lang, line=i))

    # 4. LaTeX 分页符
    for i, line in enumerate(md_text.split("\n"), 1):
        if re.search(r"\\(?:newpage|pagebreak|clearpage)", line):
            report.valid = False
            report.errors.append(t("gate.latex.pagebreak", lang, line=i))

    # 4b. 本引擎没实现的 Markdown 方言：写了不会报错，只会把原始语法印进成品
    for line_no, why in dialect_issues(md_text, lang):
        report.valid = False
        report.errors.append(
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.unsupported_syntax", lang), why=why)
        )

    # 5. 块级标记空行分隔
    for line_no, why in block_marker_issues(md_text, lang):
        report.valid = False
        report.errors.append(
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.block_marker", lang), why=why)
        )

    # 6. 未知短代码
    for line_no, why in unknown_shortcode_issues(md_text):
        report.valid = False
        report.errors.append(
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.unknown_shortcode", lang), why=why)
        )

    # 7. 分节符后又写分页：多顶出一页空白。看得见，只提醒
    _group_warn(report, t("gate.tag.section_marker", lang),
                section_pagebreak_issues(md_text, lang), lang)

    # 8. 标题层级：跳级会让大纲级别错位，但内容与样式都还在，提醒即可
    _group_warn(report, t("gate.tag.heading", lang), heading_issues(md_text, lang), lang)

    # 9. 未定义交叉引用标签
    for line_no, why in undefined_crossref_issues(md_text, lang=lang):
        report.valid = False
        report.errors.append(
            t("gate.line", lang, line=line_no, tag=t("gate.tag.crossref", lang), why=why)
        )

    # 10. 畸变表格
    for line_no, why in malformed_table_issues(md_text, lang):
        report.valid = False
        report.errors.append(
            t("gate.line", lang, line=line_no, tag=t("gate.tag.table", lang), why=why)
        )

    # 11. 图表题注邻近性：题注离表格/图片远了，样式仍会生效，只是位置不对，提醒即可
    _group_warn(report, t("gate.tag.caption_adjacency", lang),
                caption_adjacency_issues(md_text, lang), lang)

    # 11b. 折行段落：按「一行一段」读取会拆成几段，每段都吃一次首行缩进，看得见但内容没丢
    _group_warn(report, t("gate.tag.soft_wrap", lang),
                [(line_no, t("gate.soft_wrap", lang, snippet=snippet))
                 for line_no, snippet in soft_wrap_issues(md_text)], lang)

    # 11c. 公式花括号不配对：转换器不报错，只会静默丢内容
    for line_no, snippet in unbalanced_math_issues(md_text):
        report.valid = False
        report.errors.append(
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.equation_brace", lang),
              why=t("gate.equation.brace", lang, snippet=snippet))
        )

    # 12. `\tag{}` 公式编号（不认这个写法，整条公式退化成字面文本）
    for line_no, snippet in latex_tag_issues(md_text):
        report.valid = False
        report.errors.append(
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.equation_number", lang),
              why=t("gate.latex.tag", lang, snippet=snippet))
        )

    # 13/14. 依赖格式要求文件的两道门禁
    if spec is not None:
        # 13. 图片声明宽度超过版心：会被钳到版心宽，但图还在页内，提醒即可
        width_cm = content_width_cm(spec)
        if width_cm:
            _group_warn(report, t("gate.tag.image_width", lang),
                        image_width_issues(md_text, width_cm, lang), lang)
        elif has_declared_image_width(md_text):
            report.warnings.append(t("gate.image_width.no_margins", lang))

        # 14. 稿件结构 vs 要求文件声明的样式（缺一条就静默回退默认样式）
        for line_no, why in required_style_issues(md_text, spec, fm_data, lang):
            report.valid = False
            report.errors.append(
                t("gate.line", lang, line=line_no,
                  tag=t("gate.tag.style_missing", lang), why=why)
            )

    # 14b. `:::` 不是本工具的写法
    for line_no, line in enumerate(mask_code_fences(md_text).split("\n"), 1):
        if re.match(r"^\s*:::", line):
            report.valid = False
            report.errors.append(
                t("gate.line", lang, line=line_no,
                  tag=t("gate.tag.style_line", lang),
                  why=t("gate.style.triple_colon", lang))
            )

    # 14c. 题注写进图片的方括号里：方括号只放无障碍替代文字
    for line_no, line in enumerate(mask_code_fences(md_text).split("\n"), 1):
        m = re.search(r"!\[([^\]]+)\]\(", line)
        if m and re.match(r"^\s*(?:图|表|Figure|Table)\s*\d", m.group(1)):
            report.valid = False
            report.errors.append(
                t("gate.line", lang, line=line_no,
                  tag=t("gate.tag.caption_image", lang),
                  why=t("gate.caption.in_alt", lang, text=m.group(1).strip()))
            )

    # 14d. 文献区标题：列表是引擎生成的，标题得稿子里写，两种写法都认
    if isinstance(fm_data, dict) and fm_data.get("bibliography"):
        # 认名字走词表：`参考文献标题` / `References Title` / `Bibliography Title` 都指向
        # 同一个样式。写成中文字面量正则，英文稿写了 `%% References Title …` 照样被提醒
        # 「没写抬头」——而让他补的正是他已经写了的那一行，按提示改也清不掉。
        has_style_title = any(
            resolved == "References Title" for _, resolved in style_line_names(md_text)
        )
        has_heading = bool(
            re.search(r"^#{1,6}\s*(?:参考文献|参考书目|References|Bibliography)\s*$", md_text, re.M)
        )
        if not (has_style_title or has_heading):
            report.warnings.append(t("gate.bib.title_missing", lang))

    # 15. 段落样式行 `%% 样式名 内容`
    for line_no, why in style_line_issues(md_text, lang):
        report.valid = False
        report.errors.append(
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.style_line", lang), why=why)
        )

    # 16. custom-style 是否真的存在于模板（没给模板就跳过，由对账阶段兜底）
    styles_used: dict[str, list[int]] = {}
    for line_no, resolved in style_line_names(md_text):
        if resolved:
            styles_used.setdefault(resolved, []).append(line_no)
    if styles_used and template_docx is not None:
        errors, warnings = template_style_issues(styles_used, template_docx, lang)
        if errors:
            report.valid = False
            report.errors.extend(f"[custom-style] {e}" for e in errors)
        report.warnings.extend(warnings)

    return report
