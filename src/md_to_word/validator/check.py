"""md_to_word.validator.check — 稿件导前校验门禁。

按后果分两级，判据只有一条：

- **阻断（error）**：产物会静默出错，而且错了看不出来——内容丢字、变成乱码、格式静默不生效。
- **提醒（warning）**：产物看得见，只是不合规——多出一页、宽度被钳、题注离得远、标题跳级。

提醒不阻塞导出：作者可能是有意为之，也可能打算在 Word 里收尾。把这类情况做成硬失败，
只会把人逼去用 `--no-check`，连真正的阻断也一起关掉。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml
from docx.image.exceptions import (
    InvalidImageStreamError,
    UnexpectedEndOfFileError,
    UnrecognizedImageError,
)
from docx.image.image import Image as DocxImage

from md_to_word.config import get_csl_dir
from md_to_word.diagnostics import Diagnostic
from md_to_word.i18n import style_name, t
# 残符提醒与解析器共用同一条行内判据：预检另写一套，迟早对不上。
from md_to_word.model.reader import inline_residue
from md_to_word.spec.constants import BIBLIOGRAPHY_TITLES, ROW_NAME_EN, YAML_KEYS
from md_to_word.utils.section_syntax import SectionSyntaxError, parse_section_arg
from md_to_word.spec.models import TemplateSpec
from md_to_word.spec.parser import parse_format
from md_to_word.preprocessor.blocks import split_style_line, style_line_issues, style_line_names
from md_to_word.preprocessor.blocks import resolve_style_name
from md_to_word.template.generator import (
    PAGE_SIZES_CM,
    _has_heading_styleref,
    max_doc_grid_lines,
    missing_styles_for_body,
)
from md_to_word.utils.pdf_figure import PDF_SUFFIX, RASTER_SUFFIXES, PdfFigureError, page_count
from md_to_word.utils.textio import TextDecodeError, read_text_file

# 复用 utils 中的基础文本解析工具
from md_to_word.utils.masking import mask_html_comments
from md_to_word.utils.skill_utils import (
    block_marker_issues,
    soft_wrap_issues,
    bracketed_crossref_issues,
    citation_key_issues,
    citations_without_bibliography,
    dialect_issues,
    has_declared_image_width,
    heading_issues,
    image_width_issues,
    malformed_table_issues,
    mask_code,
    mask_code_fences,
    parse_bib_keys,
    resolve_manuscript_path,
    section_pagebreak_issues,
    split_frontmatter,
    unbalanced_math_issues,
    math_comment_issues,
    undefined_crossref_issues,
    unknown_shortcode_issues,
)


_GROUP_LIMIT = 8  # 一类提醒最多列这么多个行号，其余只报数量


def _group_warn(
    report: ValidationReport,
    code: str,
    tag: str,
    items: list[tuple[int, str]],
    lang: str,
) -> None:
    """同一类提醒合并成一条：一处照旧逐行说，多处只列行号。

    门禁的提醒是按行产生的，一稿折行三十处就会刷三十行，真正要紧的东西被冲掉。
    合并后每类只有一条，行号照给，改起来一样清楚。`code` 是给程序读的类别名，
    合并后仍带首个行号。
    """
    if not items:
        return
    if len(items) == 1:
        report.warning(
            code,
            t("gate.line", lang, line=items[0][0], tag=tag, why=items[0][1]),
            line=items[0][0],
        )
        return
    sep = t("gate.list_sep", lang)
    lines = sep.join(str(line_no) for line_no, _ in items[:_GROUP_LIMIT])
    if len(items) > _GROUP_LIMIT:
        lines += t("gate.line_more", lang, count=len(items) - _GROUP_LIMIT)
    report.warning(
        code,
        t("gate.line_grouped", lang, tag=tag, count=len(items), lines=lines, why=items[0][1]),
        line=items[0][0],
    )

@dataclass
class ValidationReport:
    """导前校验结果报告。

    `errors` / `warnings` 给人读，`diagnostics` 给程序读——同一条问题只产生一次，
    两个视图由 `error()` / `warning()` 同时写入，避免两套判据各说各话。
    """

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    source_file: str = ""  # 没显式给 `file=` 的诊断默认指向这份稿件

    def error(
        self, code: str, message: str, *, line: Optional[int] = None,
        file: Optional[str] = None,
    ) -> None:
        """记一条阻断项。`code` 是稳定标识，`message` 是已按语言排版好的句子。"""
        self.valid = False
        self.errors.append(message)
        self.diagnostics.append(Diagnostic(
            "error", code, message, file=file or self.source_file or None, line=line,
        ))

    def warning(
        self, code: str, message: str, *, line: Optional[int] = None,
        file: Optional[str] = None,
    ) -> None:
        """记一条提醒。提醒不影响 `valid`。"""
        self.warnings.append(message)
        self.diagnostics.append(Diagnostic(
            "warning", code, message, file=file or self.source_file or None, line=line,
        ))


def caption_adjacency_issues(md_text: str, lang: str = "zh") -> list[tuple[int, str]]:
    """题注是否紧邻其实体（表格/图片）——孤立题注在成稿里很明显，提醒即可。

    题注是独立段落（`%% 表题 …` / `%% 图片题注 …`），所以"紧邻"要跨过空行与表注：
    中间只要夹了一句正文，就认为断开。
    """
    masked = mask_code_fences(md_text)
    cleaned = mask_html_comments(masked)
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


# 「像强调、却没解析成强调」的配对：`*` 后不是空白、`*` 前不是空白，中间也不带空白——
# 与解析器的开/闭符规则同形，所以落成字面才可疑。加粗那一条同理。
_RESIDUE_EMPHASIS_RE = re.compile(
    r"\*(?=[^\s*])[^\s*]+?(?<=[^\s*])\*"
    r"|\*\*(?=[^\s*])[^\s*]+?(?<=[^\s*])\*\*"
)


def _residue_hit(residue: str, spans: list[tuple[int, int]]) -> Optional[tuple[int, int]]:
    """残符里可疑的星号区间：形态像强调的配对，或紧贴着已解析标记的孤星。

    孤星那一条专治「三颗星连写切不开」：`*a **b***` 里解析器吃掉 `**b**`，剩下的星号贴在
    它两侧——形态上就是没解析完的标记，不能无声印出去。
    """
    hit = _RESIDUE_EMPHASIS_RE.search(residue)
    if hit:
        return hit.span()
    for i, ch in enumerate(residue):
        if ch == "*" and any(i == end or i + 1 == start for start, end in spans):
            return (i, i + 1)
    return None


def literal_asterisk_issues(md_text: str) -> list[tuple[int, str]]:
    """形态像强调、却没被解析成强调的星号 → [(行号, 片段)]。

    这些星号会原样印进正文。判据只用解析器自己那份（`unparsed_stars`）：已经被当作语法
    的星号、`\\*` 转义、代码与公式里的星号都留不下来。所以符号注 `* P<0.05，** P<0.01`
    （开符后就是空格）与 `3*4` 这种孤立星号不会被报；报的是 `2*3*4`、`a*b*c` 这类词内
    乘号，以及历史上 `(1*S*,2*R*)` 那类漏解析。

    只提醒、不阻断：词内乘号的本意就是字面星号，写成 `\\*` 即可消掉本条。
    """
    issues: list[tuple[int, str]] = []
    masked = mask_code_fences(md_text)
    masked = mask_html_comments(masked)
    for line_no, line in enumerate(masked.split("\n"), 1):
        if "*" not in line:
            continue
        hit = _residue_hit(*inline_residue(line))
        if hit:
            # 片段回原行取（残符与 `spans` 都按原行下标）：残符里被吃掉的位置是空格，
            # 拿它当片段会出现「与 (1 ,」这种半截字。
            snippet = re.sub(r"\s+", " ", line[max(0, hit[0] - 6) : hit[1] + 6]).strip()
            issues.append((line_no, snippet))
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

    # `%% 样式名 …` 是稿件真正使用的样式入口。`missing_styles_for_body` 只认标题、
    # 列表、表格、图片这些结构触发，样式行必须单独对一遍；否则格式文件漏写「摘要」
    # 或「表注」时，写出器会静默回退到底模的空壳样式，预检却是绿的。
    for line_no, style in style_line_names(mask_code_fences(body)):
        if style in declared or style in reported:
            continue
        reported.add(style)
        issues.append((
            line_no + start_line - 1,
            t("gate.style.style_line_missing", lang, name=style_name(style, lang)),
        ))

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


def validate_manuscript(
    md_path: Path | str,
    *,
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
    report = ValidationReport(source_file=str(md_path))

    if not md_path.exists():
        report.valid = False
        report.error(
            "gate.manuscript.missing",
            t("gate.manuscript.missing", lang, path=md_path),
            line=None,
        )
        return report

    try:
        md_text, _ = read_text_file(md_path)
    except TextDecodeError:
        report.valid = False
        report.error(
            "textio.unreadable",
            t(
                "textio.unreadable", lang,
                label=t("textio.label.manuscript", lang), path=md_path,
            ),
            line=None,
        )
        return report
    except OSError as e:
        report.valid = False
        report.error(
            "gate.manuscript.unreadable",
            t("gate.manuscript.unreadable", lang, path=md_path, err=e),
            line=None,
        )
        return report

    # 注释在导出时会被无条件剔除；预检若还拿原文字面量去查图片、脚注、引文、样式行，
    # 合法稿件会被误拦。先挖掉、保留换行与行号，后面所有判据共用这一份。
    md_text = mask_html_comments(md_text)

    csl_dir = csl_dir or get_csl_dir()

    # 只看「作者真写的正文」的那几条判据用这个：围栏代码块与行内代码都掩成点号，
    # 行号与长度不变。稿件里用反引号演示语法（``` 里的 `![x](y.png)`、`%%注释`、
    # 重复的 `{#eq-x}`）是正当写法，不该被当成真内容去查磁盘或判重复。
    visible = mask_code(md_text)

    # 0. 格式要求（有要求文件才谈得上「稿件结构是否有对应样式」）
    if spec is None and spec_path is not None:
        fmt_file = Path(spec_path)
        if not fmt_file.is_file():
            report.valid = False
            report.error(
                "gate.format.missing",
                t("gate.format.missing", lang, path=fmt_file),
                line=None,
                file=str(fmt_file),
            )
            return report
        try:
            fmt_text, _ = read_text_file(fmt_file)
        except TextDecodeError:
            report.valid = False
            report.error(
                "textio.unreadable",
                t(
                    "textio.unreadable", lang,
                    label=t("textio.label.format", lang), path=fmt_file,
                ),
                line=None,
                file=str(fmt_file),
            )
            return report
        except OSError as e:
            report.valid = False
            report.error(
                "gate.format.parse_failed",
                t("gate.format.parse_failed", lang, path=fmt_file, err=e),
                line=None,
                file=str(fmt_file),
            )
            return report
        try:
            spec = parse_format(fmt_text)
        except Exception as e:
            report.valid = False
            report.error(
                "gate.format.parse_failed",
                t("gate.format.parse_failed", lang, path=fmt_file, err=e),
                line=None,
                file=str(fmt_file),
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
            report.error(
                "gate.yaml.parse_failed",
                t("gate.yaml.parse_failed", lang, err=e),
                line=None,
            )

    if isinstance(fm_data, dict):
        # 1a. bibliography 路径
        bib_value = fm_data.get("bibliography")
        if isinstance(bib_value, list) and len(bib_value) > 1:
            report.valid = False
            report.error(
                "gate.bib.multiple",
                t("gate.bib.multiple", lang, count=len(bib_value)),
                line=None,
            )
        elif bib_value:
            single = bib_value[0] if isinstance(bib_value, list) else bib_value
            bib_path, how = resolve_manuscript_path(str(single), md_path)
            if not how:
                report.valid = False
                report.error(
                    "gate.bib.missing",
                    t("gate.bib.missing", lang, path=single),
                    line=None,
                )

        # 1b. csl 路径
        if fm_data.get("csl"):
            csl_path, how = resolve_manuscript_path(str(fm_data["csl"]), md_path, csl_dir)
            if not how:
                report.valid = False
                report.error(
                    "gate.csl.missing",
                    t("gate.csl.missing", lang, path=fm_data["csl"]),
                    line=None,
                )

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
                    report.warning("gate.yaml.key_unused", message, line=None)
                else:
                    report.valid = False
                    report.error("gate.yaml.key_unused", message, line=None)

        # 1c. 未写 csl 的提示（默认样式由 config.default_csl_path 决定）
        if fm_data.get("bibliography") and not fm_data.get("csl"):
            from md_to_word.config import default_csl_path

            report.warning(
                "gate.csl.default",
                t("gate.csl.default", lang, name=default_csl_path(md_text).name),
                line=None,
            )

        # 1c2. `[-@key]`（只出年份）：引擎不实现，静默当普通引用就等于改写了作者的话。
        # 判据是「方括号组里任意一条引用带了 `-` 前缀」，不是「方括号紧跟 `-@`」：
        # `[@a; -@b]` 是 Pandoc 的标准写法，只看开头会把它整组放行，渲染结果与不带 `-`
        # 逐字相同——正是这条注释要防的「改写作者的话」。
        for line_no, line in enumerate(visible.split("\n"), 1):
            for group in re.findall(r"\[[^\]\n]*\]", line):
                if re.search(r"(?:^|[\s;,\[])-\s*@[\w:.-]+", group):
                    report.valid = False
                    report.error(
                        "gate.citation.suppress_author",
                        t("gate.citation.suppress_author", lang, line=line_no),
                        line=line_no,
                    )
                    break

        known = set(YAML_KEYS)
        blocked = {"title", "subtitle", "author", "date", "abstract", "keywords"}
        unknown = [
            key for key in (fm_data or {})
            if key not in known and key not in blocked and not str(key).startswith("reference-section")
        ]
        if unknown:
            report.warning(
                "gate.yaml.unknown",
                t("gate.yaml.unknown", lang, keys=", ".join(sorted(map(str, unknown)))),
                line=None,
            )

        # 1d. 正文引用的 key 是否在文献库里
        if fm_data.get("bibliography"):
            bib_path, how = resolve_manuscript_path(str(fm_data["bibliography"]), md_path)
            if how:
                from md_to_word.transform.biblio import bibliography_problem

                problem = None
                try:
                    bib_text, _ = read_text_file(bib_path)
                except TextDecodeError:
                    report.valid = False
                    report.error(
                        "textio.unreadable",
                        t(
                            "textio.unreadable", lang,
                            label=t("textio.label.bibliography", lang), path=bib_path,
                        ),
                        line=None,
                    )
                    bib_text = ""
                except OSError:
                    bib_text = ""
                # 坏 JSON 与「文献库为空」是两回事：前者要说清楚哪一行读不了，
                # 后者是作者确实没给条目。混成一句「没有可用条目」会把人指向错误的方向。
                problem = bibliography_problem(bib_text, lang)
                if problem:
                    report.error("gate.bib.json", problem, file=str(bib_path))
                    bib_text = ""
                known_keys = parse_bib_keys(bib_text)
                if not known_keys and not problem:
                    bare = citations_without_bibliography(body_text, fm_offset)
                    if bare:
                        report.valid = False
                        report.error(
                            "gate.bib.empty",
                            t("gate.bib.empty", lang,
                              name=Path(bib_path).name, count=len(bare)),
                            line=None,
                        )
                cite_issues = citation_key_issues(body_text, known_keys, fm_offset, lang)
                if cite_issues:
                    report.valid = False
                    for line_no, why in cite_issues:
                        report.error(
                            "gate.citation.key",
                            t("gate.line", lang,
                              line=line_no, tag=t("gate.tag.citation_key", lang), why=why),
                            line=line_no,
                        )
        else:
            bare_cites = citations_without_bibliography(body_text, fm_offset)
            if bare_cites:
                report.valid = False
                sep = t("gate.list_sep", lang)
                shown = sep.join(t("gate.line_item", lang, line=n) for n in bare_cites[:5])
                report.error(
                    "gate.citation.no_bibliography",
                    t("gate.citation.no_bibliography", lang,
                      count=len(bare_cites), shown=shown),
                    line=None,
                )

    # 1e. 编号格式用了 {c}（章号），稿件却没说按章编号：两个文件各写一半，等式不成立
    #     正文与附录两行都要查：附录里「按附录标识编号」同样依赖 {c}。
    for attr, name_key in (
        ("equation_number_format", "spec.line.equation_format"),
        ("appendix_equation_number_format", "spec.line.appendix_equation_format"),
    ):
        eq_format = getattr(spec, attr, "") or ""
        if "{c}" not in eq_format:
            continue
        crossref = fm_data.get("crossref") if isinstance(fm_data, dict) else None
        by_chapter = isinstance(crossref, dict) and bool(crossref.get("chapters"))
        if not by_chapter:
            report.valid = False
            report.error(
                "gate.equation.chapters",
                t("gate.equation.chapters", lang, fmt=eq_format, name=t(name_key, lang)),
                line=None,
            )

    # 1f. 文档网格：声明的行数超过版心能放下的行数时兑现不了，而且结果比不声明还差
    if spec and spec.doc_grid_lines:
        limit = max_doc_grid_lines(spec)
        if limit and spec.doc_grid_lines > limit:
            report.warning(
                "gate.doc_grid.unreachable",
                t("gate.doc_grid.unreachable", lang, want=spec.doc_grid_lines, limit=limit),
                line=None,
            )

    # 2. 图片路径空格与存在性
    for i, line in enumerate(visible.split("\n"), 1):
        for m in re.finditer(r"!\[(.*?)\]\((.*?)\)", line):
            raw_path = m.group(2).strip()
            # 远程图片本引擎不下载：放过去只会在写出阶段把它当本地路径，报成"磁盘满"
            if raw_path.startswith(("http://", "https://", "data:")):
                report.valid = False
                report.error(
                    "gate.image.remote",
                    t("gate.image.remote", lang, line=i, path=raw_path[:60]),
                    line=i,
                )
                continue
            # 空格检查
            if " " in raw_path and not raw_path.startswith("<") and not re.search(r'["\'].*["\']', raw_path):
                report.valid = False
                report.error(
                    "gate.image.path_space",
                    t("gate.image.path_space", lang, line=i, path=raw_path),
                    line=i,
                )
            # 存在性检查
            clean_path = raw_path.split()[0].strip("<>\"'")
            img_file = md_path.parent / clean_path
            if not img_file.exists():
                report.valid = False
                report.error(
                    "gate.image.missing",
                    t("gate.image.missing", lang, line=i, path=clean_path),
                    line=i,
                )
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
                    report.error(
                        "gate.image.pdf_unreadable",
                        t("gate.image.pdf_unreadable", lang, line=i, path=clean_path, err=exc),
                        line=i,
                    )
                else:
                    if pages > 1:
                        report.warning(
                            "gate.image.pdf_multipage",
                            t("gate.image.pdf_multipage", lang, line=i, path=clean_path, pages=pages),
                            line=i,
                        )
            elif suffix not in RASTER_SUFFIXES:
                report.valid = False
                report.error(
                    "gate.image.unsupported",
                    t("gate.image.unsupported", lang, line=i, path=clean_path, ext=suffix or t("common.no_suffix", lang)),
                    line=i,
                )
            else:
                # 扩展名对不代表文件能解码：把 txt 改名成 .png 很常见，python-docx
                # 会在写出阶段抛 UnrecognizedImageError，最后被误报成“工具缺陷”。
                try:
                    DocxImage.from_file(str(img_file))
                except (
                    UnrecognizedImageError, InvalidImageStreamError,
                    UnexpectedEndOfFileError, OSError, ValueError,
                ) as exc:
                    report.valid = False
                    report.error(
                        "gate.image.unreadable",
                        t(
                            "gate.image.unreadable", lang,
                            line=i, path=clean_path, err=type(exc).__name__,
                        ),
                        line=i,
                    )

    # 2b. 图片必须独立成行：行内图片不会落成图段，只会印出一个 `!`
    for i, line in enumerate(visible.split("\n"), 1):
        stripped = line.strip()
        if not re.search(r"!\[.*?\]\(", line):
            continue
        if not re.fullmatch(r"!\[[^\]]*\]\([^)]*\)(?:\{[^}]*\})?", stripped):
            report.valid = False
            report.error("gate.image.inline", t("gate.image.inline", lang, line=i), line=i)

    # 2c. 脚注引用必须有定义：缺定义的脚注会印成空号，整段注释丢字
    defined = set(re.findall(r"^\s*\[\^([^\]]+)\]:", visible, re.M))
    for i, line in enumerate(visible.split("\n"), 1):
        for label in re.findall(r"\[\^([^\]]+)\](?!:)", line):
            if label not in defined:
                report.valid = False
                report.error(
                    "gate.footnote.undefined",
                    t("gate.footnote.undefined", lang, line=i, label=label),
                    line=i,
                )

    # 2d. 表格行缺少行尾竖线：那一行会掉出表格、变成正文，竖线原样印出来
    for i, line in enumerate(visible.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("|") and not stripped.endswith("|"):
            report.valid = False
            report.error(
                "gate.table.row_unclosed",
                t("gate.table.row_unclosed", lang, line=i),
                line=i,
            )

    # 2e. 样式行 `%%` 后面必须有空格，否则整行原样印成正文
    for i, line in enumerate(visible.split("\n"), 1):
        if line.startswith("%%") and not line.startswith("%% "):
            report.valid = False
            report.error(
                "gate.style_line.no_space",
                t("gate.style_line.no_space", lang, line=i),
                line=i,
            )

    # 2f. 分节标记只接受一个节名；节名必须是格式文件声明过的角色。
    #     写法不对或名字不存在时，读取器/写出器就没法给这一节定外观，必须在导前拦下。
    declared_roles = list(spec.section_roles) if spec is not None else []
    for i, line in enumerate(visible.split("\n"), 1):
        m = re.search(r"\{\{<\s*section\b([^>]*)>\}\}", line)
        if not m:
            continue
        try:
            role = parse_section_arg(m.group(1))
        except SectionSyntaxError as exc:
            report.valid = False
            report.error(
                "gate.section.argument",
                t("gate.section.argument", lang, line=i, arg=exc.arg),
                line=i,
            )
            continue
        if role is None or spec is None or role in spec.section_roles:
            continue
        report.valid = False
        report.error(
            "gate.section.role_unknown",
            t("gate.section.role_unknown", lang, line=i, role=role,
              roles=(", " if lang == "en" else "、").join(declared_roles)
              or t("common.none", lang)),
            line=i,
        )

    # 3. Obsidian WikiLinks 与 4. LaTeX 分页符：代码块里是数据，不是写法
    for i, line in enumerate(mask_code_fences(md_text).split("\n"), 1):
        if re.search(r"!\[\[.*?\]\]|\[\[.*?\]\]", line):
            report.valid = False
            report.error("gate.wikilink", t("gate.wikilink", lang, line=i), line=i)
        elif re.search(r"\\(?:newpage|pagebreak|clearpage)", line):
            report.valid = False
            report.error("gate.latex.pagebreak", t("gate.latex.pagebreak", lang, line=i), line=i)

    # 4b. 本引擎没实现的 Markdown 方言：写了不会报错，只会把原始语法印进成品
    for line_no, why in dialect_issues(md_text, lang):
        report.valid = False
        report.error(
            "gate.tag.unsupported_syntax",
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.unsupported_syntax", lang), why=why),
            line=line_no,
        )

    # 4c. 交叉引用写成了引文方括号：`[@eq-x]` 会被当条目去查，渲染期才炸
    for line_no, why in bracketed_crossref_issues(md_text, lang=lang):
        report.valid = False
        report.error(
            "gate.crossref.syntax",
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.crossref_syntax", lang), why=why),
            line=line_no,
        )

    # 5. 块级标记空行分隔
    for line_no, why in block_marker_issues(md_text, lang):
        report.valid = False
        report.error(
            "gate.block_marker",
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.block_marker", lang), why=why),
            line=line_no,
        )

    # 6. 未知短代码
    for line_no, why in unknown_shortcode_issues(md_text):
        report.valid = False
        report.error(
            "gate.shortcode.unknown",
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.unknown_shortcode", lang), why=why),
            line=line_no,
        )

    # 7. 分节符后又写分页：多顶出一页空白。看得见，只提醒
    _group_warn(report, "gate.section.pagebreak_after", t("gate.tag.section_marker", lang),
                section_pagebreak_issues(md_text, lang), lang)

    # 8. 标题层级：跳级会让大纲级别错位，但内容与样式都还在，提醒即可
    _group_warn(report, "gate.heading.level", t("gate.tag.heading", lang), heading_issues(md_text, lang), lang)

    # 9. 未定义交叉引用标签
    for line_no, why in undefined_crossref_issues(md_text, lang=lang):
        report.valid = False
        report.error(
            "gate.crossref.undefined",
            t("gate.line", lang, line=line_no, tag=t("gate.tag.crossref", lang), why=why),
            line=line_no,
        )

    # 10. 畸变表格
    for line_no, why in malformed_table_issues(md_text, lang):
        report.valid = False
        report.error(
            "gate.table.malformed",
            t("gate.line", lang, line=line_no, tag=t("gate.tag.table", lang), why=why),
            line=line_no,
        )

    # 10b. 公式标签重复：两条公式共用一个标签，后面那条的编号会盖掉前面，引用只能指到一条
    labels_seen: dict[str, int] = {}
    for i, line in enumerate(visible.split("\n"), 1):
        for label in re.findall(r"\{#(eq-[\w:.\-]+)\}", line):
            if label in labels_seen:
                report.valid = False
                report.error(
                    "gate.equation.duplicate_label",
                    t("gate.equation.duplicate_label", lang, label=label,
                      first=labels_seen[label], line=i),
                    line=i,
                )
            else:
                labels_seen[label] = i

    # 10c. 按章编号时，第一个一级标题之前的公式会编成「0-1」
    crossref = fm_data.get("crossref") if isinstance(fm_data, dict) else None
    if isinstance(crossref, dict) and crossref.get("chapters"):
        seen_heading = False
        for i, line in enumerate(md_text.split("\n"), 1):
            if re.match(r"^#\s+", line):
                seen_heading = True
            elif not seen_heading and re.search(r"\$\$.*\{#(eq-[\w:.\-]+)\}", line):
                report.warning(
                    "gate.equation.before_chapter",
                    t("gate.equation.before_chapter", lang, line=i),
                    line=i,
                )

    # 11. 图表题注邻近性：题注离表格/图片远了，样式仍会生效，只是位置不对，提醒即可
    _group_warn(report, "gate.caption.adjacency", t("gate.tag.caption_adjacency", lang),
                caption_adjacency_issues(md_text, lang), lang)

    # 11b. 折行段落：按「一行一段」读取会拆成几段，每段都吃一次首行缩进，看得见但内容没丢
    _group_warn(report, "gate.paragraph.soft_wrap", t("gate.tag.soft_wrap", lang),
                [(line_no, t("gate.soft_wrap", lang, snippet=snippet))
                 for line_no, snippet in soft_wrap_issues(md_text)], lang)

    # 11c. 公式里的裸 `%`：LaTeX 当注释起始，后面整段静默消失
    for line_no, snippet in math_comment_issues(md_text):
        report.valid = False
        report.error(
            "gate.math.comment",
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.math_comment", lang),
              why=t("gate.math.comment", lang, snippet=snippet)),
            line=line_no,
        )

    # 11d. 公式花括号不配对：转换器不报错，只会静默丢内容
    for line_no, snippet in unbalanced_math_issues(md_text):
        report.valid = False
        report.error(
            "gate.equation.brace",
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.equation_brace", lang),
              why=t("gate.equation.brace", lang, snippet=snippet)),
            line=line_no,
        )

    # 11d. 星号形态像强调、却没被解析成强调：这些星号会原样印出。词内乘号本来就是字面
    # 星号，只提醒不阻断，并给出去路
    _group_warn(report, "gate.emphasis.literal_asterisk", t("gate.tag.literal_asterisk", lang),
                [(line_no, t("gate.literal_asterisk", lang, snippet=snippet))
                 for line_no, snippet in literal_asterisk_issues(md_text)], lang)

    # 12. `\tag{}` 公式编号（不认这个写法，整条公式退化成字面文本）
    for line_no, snippet in latex_tag_issues(md_text):
        report.valid = False
        report.error(
            "gate.equation.latex_tag",
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.equation_number", lang),
              why=t("gate.latex.tag", lang, snippet=snippet)),
            line=line_no,
        )

    # 13/14. 依赖格式要求文件的两道门禁
    if spec is not None:
        # 13. 图片声明宽度超过版心：会被钳到版心宽，但图还在页内，提醒即可
        width_cm = content_width_cm(spec)
        if width_cm:
            _group_warn(report, "gate.image.width", t("gate.tag.image_width", lang),
                        image_width_issues(md_text, width_cm, lang), lang)
        elif has_declared_image_width(md_text):
            report.warning(
                "gate.image_width.no_margins",
                t("gate.image_width.no_margins", lang),
                line=None,
            )

        # 14. 稿件结构 vs 要求文件声明的样式（缺一条就静默回退默认样式）
        for line_no, why in required_style_issues(md_text, spec, fm_data, lang):
            report.valid = False
            report.error(
                "gate.style.missing",
                t("gate.line", lang, line=line_no,
                  tag=t("gate.tag.style_missing", lang), why=why),
                line=line_no,
            )

        # 14a. {.unlisted} / {不入目录} 与 {样式标题:Heading ...} 并用提醒（非阻断）
        if _has_heading_styleref(spec):
            _, body = split_frontmatter(md_text)
            body_start = md_text.count("\n") - body.count("\n") + 1
            for offset_idx, raw_line in enumerate(mask_code_fences(body).split("\n")):
                m_unlisted = re.match(
                    r"^\s*(#{1,6})\s+(.*?)\s*\{(?:\.unlisted|不入目录)\}\s*$",
                    raw_line,
                )
                if m_unlisted:
                    title = m_unlisted.group(2).rstrip().rstrip("#").rstrip()
                    if title:
                        report.warning(
                            "gate.heading.unlisted_with_styleref",
                            t("gate.heading.unlisted_with_styleref", lang,
                              line=body_start + offset_idx, title=title[:30]),
                            line=body_start + offset_idx,
                        )

    # 14b. `:::` 不是本工具的写法
    for line_no, line in enumerate(mask_code_fences(md_text).split("\n"), 1):
        if re.match(r"^\s*:::", line):
            report.valid = False
            report.error(
                "gate.style.triple_colon",
                t("gate.line", lang, line=line_no,
                  tag=t("gate.tag.style_line", lang),
                  why=t("gate.style.triple_colon", lang)),
                line=line_no,
            )

    # 14c. 题注写进图片的方括号里：方括号只放无障碍替代文字
    for line_no, line in enumerate(mask_code_fences(md_text).split("\n"), 1):
        m = re.search(r"!\[([^\]]+)\]\(", line)
        if m and re.match(r"^\s*(?:图|圖|表|Figure|Table)\s*\d", m.group(1)):
            report.valid = False
            report.error(
                "gate.caption.in_alt",
                t("gate.line", lang, line=line_no,
                  tag=t("gate.tag.caption_image", lang),
                  why=t("gate.caption.in_alt", lang, text=m.group(1).strip())),
                line=line_no,
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
            re.search(
                r"^#{1,6}\s*(?:"
                + "|".join(map(re.escape, BIBLIOGRAPHY_TITLES))
                + r")(?:\s*\{(?:\.unlisted|不入目录)\})?\s*$",
                md_text,
                re.M,
            )
        )
        if not (has_style_title or has_heading):
            report.warning(
                "gate.bib.title_missing",
                t("gate.bib.title_missing", lang),
                line=None,
            )

    # 15. 段落样式行 `%% 样式名 内容`
    for line_no, why in style_line_issues(md_text, lang):
        report.valid = False
        report.error(
            "gate.style_line.invalid",
            t("gate.line", lang, line=line_no,
              tag=t("gate.tag.style_line", lang), why=why),
            line=line_no,
        )

    return report
