"""md_to_word.pipeline — 导出总编排。

顺序固定：读稿 → 定格式与底模切点 → 预检 → 生成样式模板与 CSL → 读成文档模型 →
写出 OOXML → 防丢内容 → 对账 →（可选）盲审清理与底模灌入 →（可选）PDF。
每一步失败都有明确的退出码与可读原因；核心导出跨平台，不依赖任何外部二进制，
只有可选的 `--pdf` 需要 macOS 上的 Microsoft Word。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from md_to_word.audit.inspector import audit_docx_against_spec
from md_to_word.audit.postflight import (
    verify_chinese_integrity, verify_latin_integrity, verify_numeric_integrity,
)
from md_to_word.config import (
    default_csl_path_for_lang, default_preset_name, get_csl_dir,
    lang_from_proofing, looks_traditional, resolve_preset_path,
)
from md_to_word.diagnostics import Diagnostic
from md_to_word.i18n import join_terms, resolve_lang, t
from md_to_word.preprocessor.cleaner import strip_html_comments
from md_to_word.spec.parser import parse_format
from md_to_word.template.builder import build_template
from md_to_word.status import EXIT_ERROR, EXIT_OK, EXIT_PDF_SKIPPED, EXIT_USAGE
from md_to_word.template.core import TemplateError, join_reasons as _join
from md_to_word.validator.check import validate_manuscript
from md_to_word.visual_qa.word_pdf import render_pdf_via_word
from md_to_word.utils.metadata import identifying_metadata, scrub_metadata
from md_to_word.utils.skill_utils import split_frontmatter, resolve_manuscript_path
from md_to_word.utils.textio import TextDecodeError, UTF8_ENCODINGS, read_text_file

logger = logging.getLogger("md2word")


@dataclass
class ExportOptions:
    """导出配置选项。"""

    input_path: Path | str
    output_path: Optional[Path | str] = None
    format_path: Optional[Path | str] = None
    preset: Optional[str] = None
    check_md: bool = True
    postflight: bool = True
    audit: bool = True
    make_pdf: bool = False
    lang: Optional[str] = None  # 消息语言：None=按稿件语种 | "zh" | "en"
    base_template: Optional[Path | str] = None  # 学校模板：把正文灌进它，保留它自己的封面版式
    cover_sections: int = 0  # 底模的前几节是前置件（封面、声明等），原样保留
    keep_until: str = ""  # 按内容说：这段文字所在的段落是最后一行
    blind_review: bool = False  # 清理文档属性：作者、单位、自定义属性、缩略图、批注作者


@dataclass
class ExportResult:
    """流水线执行结果。"""

    returncode: int  # EXIT_OK / EXIT_ERROR / EXIT_PDF_SKIPPED（见 status.py）
    output_docx: Optional[Path] = None
    output_pdf: Optional[Path] = None
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # messages 里的提醒条目，供 CLI 加标记
    lang: str = "zh"  # 消息语言
    doc_lang: str = ""  # 稿件语言：决定默认预设与默认 CSL，和消息语言分开
    format_source: str = ""  # file:/abs/path 或 preset:zh-academic
    pdf_skip_reason: str = ""  # `--pdf` 没做成的原因码，见 word_pdf.explain_unavailable
    diagnostics: list[Diagnostic] = field(default_factory=list)  # 与 errors/warnings 同源的机器视图

    @property
    def ok(self) -> bool:
        """docx 是否已经写出来了（`--pdf` 跳过不算失败）。"""
        return self.returncode in (EXIT_OK, EXIT_PDF_SKIPPED)


def _fail(
    res: ExportResult, code: str, message: str, *,
    line: Optional[int] = None, file: Optional[Path | str] = None,
) -> None:
    """记一条阻断项并结束本次调用：错误句子与诊断条目一次写入，不会只更新一边。"""
    res.returncode = EXIT_ERROR
    res.errors.append(message)
    res.diagnostics.append(Diagnostic(
        "error", code, message, file=str(file) if file else None, line=line,
    ))


def _warn(res: ExportResult, code: str, message: str, *, file: Optional[Path | str] = None) -> None:
    """记一条提醒：`messages` 给人、`warnings` 供 CLI 加标记、`diagnostics` 给程序。"""
    # 同一份底模会被体检两次，同一条提醒只说一遍。按 `(code, message)` 去重：
    # 两个不同来源恰好用了同一句话时，仍应各留一条。
    if any(d.severity == "warning" and d.code == code and d.message == message
           for d in res.diagnostics):
        return
    res.messages.append(message)
    res.warnings.append(message)
    res.diagnostics.append(Diagnostic(
        "warning", code, message, file=str(file) if file else None,
    ))


def _blind_review(res: ExportResult, target: Path, out_p: Path) -> bool:
    """在临时产物上清理文档属性；成功返回 True，失败记错误且不发布。"""
    try:
        scrub_metadata(target, res.lang)
    except Exception as exc:  # zip 坏了、磁盘满：都归「没清理干净」，不该带着身份发布
        _fail(res, "pipeline.blind_review_failed", t(
            "pipeline.blind_review_failed", res.lang,
            reason=f"{type(exc).__name__}: {exc}",
        ), file=out_p)
        return False
    done = t("pipeline.blind_review_done", res.lang)
    if done not in res.messages:
        res.messages.append(done)
    return True


def _inline_text(inline) -> str:
    """行内节点里真正的字。加粗、斜体是包着一层的容器，只读 `.value` 会漏掉整段加粗的开头。"""
    text = getattr(inline, "text", "") or getattr(inline, "value", "")
    if text:
        return text
    return "".join(_inline_text(child) for child in getattr(inline, "children", ()) or ())


def _first_texts(blocks, limit: int = 5, min_len: int = 4) -> list[str]:
    """正文前几段的开头，按顺序给一串。

    只用第一段会有个坑：很多学校模板的前置件里放了一份示例目录，「第一章 绪论」正好也
    在上面，拿它去定位正文起点就会落在封面上。多给几个候选，让验真那边把在前置件里出现
    过的剔掉，剩下的才用来定位。

    `min_len` 是「算一段有效开头」的最短长度：定位封面页数的哨兵（`_first_text`）需要
    接受不足 4 字的短首段，所以由调用方指定。
    """
    heads: list[str] = []
    for block in blocks:
        text = re.sub(r"\s+", "", "".join(
            _inline_text(inline) for inline in getattr(block, "inlines", []) or []))
        if len(text) >= min_len and text[:12] not in heads:
            heads.append(text[:12])
        if len(heads) >= limit:
            break
    return heads


def _note_encoding(
    label_key: str, encoding: str, res: ExportResult, *, file: Optional[Path | str] = None
) -> None:
    if encoding in UTF8_ENCODINGS:
        return
    _warn(
        res,
        "textio.fallback",
        t("textio.fallback", res.lang, label=t(label_key, res.lang), encoding=encoding),
        file=file,
    )


@dataclass
class PreparedManuscript:
    """读稿结果。`ok=False` 时 `res` 里已有阻断项，调用方直接返回即可。"""

    res: ExportResult
    path: Path
    text: str = ""
    encoding: str = ""
    doc_lang: str = ""
    ok: bool = True


def prepare_manuscript(options: ExportOptions) -> PreparedManuscript:
    """读稿、定语言、记编码：导出、导前预检、MCP 校验共用的第一步。

    三处各写一遍时，语言判定与编码提醒很容易只改到其中一处；这里统一之后，
    「同一份稿子换个入口报出不同语言」就不会再发生。
    """
    res = ExportResult(returncode=0)
    res.lang = resolve_lang("", options.lang)
    in_p = Path(options.input_path).resolve()
    if not in_p.is_file():
        # 目录确实存在、只是不是稿件：说「不存在」会让人对着一个看得见的文件夹发懵。
        key = "pipeline.input_not_file" if in_p.exists() else "pipeline.input_missing"
        _fail(res, key, t(key, res.lang, path=in_p), file=in_p)
        return PreparedManuscript(res, in_p, ok=False)
    # 把 Word 文档当稿件是第一次使用最常见的误解：按编码错误提示「另存为 UTF-8」
    # 永远修不好。按扩展名与二进制头认出来，直接给正确入口。
    try:
        with in_p.open("rb") as fh:
            head = fh.read(4)
    except OSError:
        head = b""
    if in_p.suffix.lower() in {".docx", ".docm", ".doc"} or head.startswith(
        (b"PK\x03\x04", b"\xd0\xcf\x11\xe0")
    ):
        _fail(res, "pipeline.input_word_document",
              t("pipeline.input_word_document", res.lang, suffix=in_p.suffix or "(none)"),
              file=in_p)
        return PreparedManuscript(res, in_p, ok=False)

    try:
        text, encoding = read_text_file(in_p)
    except TextDecodeError:
        _fail(res, "textio.unreadable", t(
            "textio.unreadable", res.lang,
            label=t("textio.label.manuscript", res.lang), path=in_p,
        ), file=in_p)
        return PreparedManuscript(res, in_p, ok=False)
    except OSError as exc:
        _fail(res, "pipeline.read_failed", t(
            "pipeline.read_failed", res.lang,
            label=t("textio.label.manuscript", res.lang), path=in_p, err=exc,
        ), file=in_p)
        return PreparedManuscript(res, in_p, ok=False)
    # 消息语言可以覆盖；**稿件语言**只按正文判，它决定默认预设与默认 CSL。
    res.lang = resolve_lang(text, options.lang)
    doc_lang = resolve_lang(text, None)
    res.doc_lang = doc_lang
    # 繁体稿在自动选预设时会落到简体 zh-academic；这不改变默认行为，但必须说一声。
    # 显式给了 --preset 或 -f 时用户已经做了选择，不再打扰。
    if (
        not options.preset
        and not options.format_path
        and not (in_p.parent / "format.txt").is_file()
        and looks_traditional(text)
    ):
        _warn(res, "pipeline.traditional_preset",
              t("pipeline.traditional_preset", res.lang), file=in_p)
    _note_encoding("textio.label.manuscript", encoding, res, file=in_p)
    return PreparedManuscript(res, in_p, text, encoding, doc_lang)


def _read_user_text(
    path: Path, label_key: str, res: ExportResult, *, warn_fallback: bool = True
) -> Optional[str]:
    """读格式/文献库等用户文本：编码不对时说清楚，不让 UnicodeDecodeError 冒成“工具缺陷”。

    稿件单独处理——它的编码可能决定消息语言，提醒必须等语言判定之后再出。
    """
    label = t(label_key, res.lang)
    try:
        text, encoding = read_text_file(path)
    except TextDecodeError:
        _fail(res, "textio.unreadable",
              t("textio.unreadable", res.lang, label=label, path=path), file=path)
        return None
    except OSError as exc:
        _fail(res, "pipeline.read_failed",
              t("pipeline.read_failed", res.lang, label=label, path=path, err=exc), file=path)
        return None
    if warn_fallback:
        _note_encoding(label_key, encoding, res, file=path)
    return text


def resolve_format(
    in_p: Path,
    res: ExportResult,
    *,
    format_path: Optional[Path | str],
    preset: Optional[str],
    doc_lang: str,
) -> tuple[Optional[Path], Optional[str]]:
    """确定这次导出用哪份格式文件，并读出内容。

    CLI 与“只校验”共用这一份判断：两边各写一套，迟早会出现“校验用预设 A、
    导出用预设 B”的分叉。
    """
    fmt_file: Optional[Path] = None
    fmt_content: Optional[str] = None

    if format_path and preset:
        # 同时给两个来源时旧行为是「-f 静默胜出」——调用方以为 preset 生效了，
        # 拿到的却是另一份格式。宁可当场拒绝，也不替人猜。
        _fail(res, "pipeline.format_preset_conflict",
              t("pipeline.format_preset_conflict", res.lang))
        res.returncode = EXIT_USAGE  # 参数写法错误，不是稿件/依赖问题
        return None, None

    if format_path:
        p_fmt = Path(format_path).resolve()
        if not p_fmt.is_file():
            _fail(res, "pipeline.format_missing",
                  t("pipeline.format_missing", res.lang, path=p_fmt), file=p_fmt)
            return None, None
        # 先记来源再读：读失败时诊断里仍能指出「用的是哪份」。
        fmt_file = p_fmt
        res.format_source = f"file:{p_fmt}"
        fmt_content = _read_user_text(p_fmt, "textio.label.format", res)
        if fmt_content is None:
            return None, None
    elif preset:
        p_pre = resolve_preset_path(preset)
        if not p_pre or not p_pre.is_file():
            _fail(res, "pipeline.preset_missing",
                  t("pipeline.preset_missing", res.lang, name=preset))
            return None, None
        fmt_file = p_pre
        res.format_source = f"preset:{preset}"
        fmt_content = _read_user_text(p_pre, "textio.label.format", res, warn_fallback=False)
        if fmt_content is None:
            return None, None
    else:
        # 只认一个固定名：稿件同目录的 `format.txt`。不去猜「旁边那个 .txt
        # 也许是要求文件」——猜错是静默用错格式，猜对了也换不来多少方便。
        named = in_p.parent / "format.txt"
        if named.is_file():
            fmt_content = _read_user_text(named, "textio.label.format", res)
            if fmt_content is None:
                return None, None
            fmt_file = named
            res.format_source = f"file:{named}"
            res.messages.append(t("pipeline.txt_named", res.lang, path=named.name))
        else:
            others = sorted(p.name for p in in_p.parent.glob("*.txt") if p.is_file())
            if others:
                shown = join_terms(others[:3], res.lang) + ("…" if len(others) > 3 else "")
                # 这是「你以为在用、其实没用」：必须进 warnings，Agent 才会转述。
                _warn(res, "pipeline.txt_ignored",
                      t("pipeline.txt_ignored", res.lang, names=shown))
            # 默认预设跟着**稿件语种**走，不跟 `--lang`（那是消息语言）：中文稿加
            # `--lang en` 只为读英文报错，不能因此套上英文期刊的版式。
            preset_name = default_preset_name(doc_lang)
            p_default = resolve_preset_path(preset_name)
            if p_default and p_default.is_file():
                fmt_file = p_default
                fmt_content = _read_user_text(
                    p_default, "textio.label.format", res, warn_fallback=False
                )
                if fmt_content is None:
                    return None, None
                res.format_source = f"preset:{preset_name}"
                res.messages.append(t("pipeline.preset_auto", res.lang, name=preset_name))
            else:
                # 包内预设缺失是安装损坏，不是“用户可以自己想办法”的情况。旧行为是
                # 什么也不说地返回空内容，调用方看到 returncode=0 却没有产物。
                _fail(res, "pipeline.preset_missing",
                      t("pipeline.preset_missing", res.lang, name=preset_name))
                return None, None
    return fmt_file, fmt_content


@dataclass
class BasePlan:
    """底模这件事在渲染前就能确定的全部结论。"""

    base: Path
    sections: int
    cut_at_paragraph: bool = False  # 导出时在命中段落之后插入分节符


def _prepare_base_plan(
    options: ExportOptions, res: ExportResult,
) -> tuple[bool, Optional[BasePlan]]:
    """渲染前把底模的前置条件全部查完，两个出口共用。

    返回 `(False, None)` 表示已经记下错误；`(True, None)` 表示没用底模。放在渲染前
    是刻意的：底模不存在、切点歧义、兼容模式不一致，都不该等整篇排完才说。
    """
    if options.cover_sections < 0:
        _fail(res, "pipeline.option_negative",
              t("pipeline.option_negative", res.lang))
        res.returncode = EXIT_USAGE
        return False, None
    if not options.base_template:
        used = [
            flag for flag, value in (
                ("--keep-until", options.keep_until),
                ("--cover-sections", options.cover_sections),
            ) if value
        ]
        if used:
            _warn(res, "pipeline.cut_without_base", t(
                "pipeline.cut_without_base", res.lang, flags=" / ".join(used)
            ))
        return True, None

    from md_to_word.template.base_inject import (
        BODY_COMPAT_MODE,
        BaseTemplateError,
        _compat_mode,
        inspect_base,
        paragraph_cut_section,
    )

    base_p = Path(options.base_template).resolve()
    if not base_p.is_file():
        _fail(res, "pipeline.base_missing",
              t("pipeline.base_missing", res.lang, path=base_p), file=base_p)
        return False, None

    report = inspect_base(base_p, lang=res.lang)
    if not report.ok:
        _fail(res, "pipeline.base_failed",
              t("pipeline.base_failed", res.lang, reason=_join(report.blocking, res.lang)),
              file=base_p)
        res.errors.extend(f"  {n}" for n in report.notes)
        return False, None

    # 兼容模式是文档级的，后面没法补救；先查，别等渲染完才发现。
    mode = _compat_mode(base_p)
    if mode != BODY_COMPAT_MODE:
        key = "base.compat_unknown" if not mode else "base.compat_mismatch"
        _fail(res, "pipeline.base_failed", t(
            key, res.lang,
            base=mode or t("base.common.unset", res.lang),
            body=BODY_COMPAT_MODE,
        ), file=base_p)
        return False, None

    # 底模的 docProps 会原样跟着成品走。没开盲审清理时至少要说一声——
    # 作者、单位、学号、封面缩略图都可能在这份文件里，交去盲审就是身份泄漏。
    if not options.blind_review:
        findings = identifying_metadata(base_p)
        if findings:
            sep = ": " if res.lang == "en" else "："
            fields = _join((
                t(f"metadata.field.{f.code}", res.lang)
                + (sep + f.detail[:40] if f.detail else "")
                for f in findings
            ), res.lang)
            _warn(res, "pipeline.base_metadata", t(
                "pipeline.base_metadata", res.lang, fields=fields,
            ), file=base_p)

    if options.cover_sections and options.keep_until:
        _fail(res, "pipeline.base_multi_cut",
              t("pipeline.base_multi_cut", res.lang), file=base_p)
        return False, None

    cut_at_paragraph = False
    if options.keep_until:
        try:
            sections = paragraph_cut_section(base_p, options.keep_until, res.lang)
        except BaseTemplateError as exc:
            _fail(res, "pipeline.base_failed",
                  t("pipeline.base_failed", res.lang, reason=exc.reason), file=base_p)
            res.errors.extend(f"  {n}" for n in exc.notes)
            return False, None
        res.messages.append(t(
            "pipeline.base_paragraph_cut", res.lang, text=options.keep_until))
        cut_at_paragraph = True
        # 原底模的最后一节也可能是切点；此时 paragraph_cut 会再克隆一个 sectPr 出来，
        # 所以不能拿 `sections == 总节数` 去判「全切走」。
        report = inspect_base(base_p, lang=res.lang)
    else:
        sections = options.cover_sections
        if not sections:
            _fail(res, "pipeline.base_need_sections",
                  t("pipeline.base_need_sections", res.lang), file=base_p)
            return False, None
        report = inspect_base(base_p, sections, res.lang)
    if not report.ok:
        _fail(res, "pipeline.base_failed",
              t("pipeline.base_failed", res.lang, reason=_join(report.blocking, res.lang)),
              file=base_p)
        res.errors.extend(f"  {n}" for n in report.notes)
        return False, None
    comment_note = t("base.inspect.comments", res.lang)
    for note in report.notes:
        if options.blind_review and note == comment_note:
            continue  # 盲审会把批注整件删掉，这时提示「会带批注气泡」是反的
        _warn(res, "pipeline.base_note", note, file=base_p)
    return True, BasePlan(base_p, sections, cut_at_paragraph)


def _trial_export(options: ExportOptions, fmt_file: Optional[Path], res: ExportResult) -> bool:
    """预检通过后，用同一套写出器往临时目录真导一次。

    词表与正则只能拦住一部分问题：`\\xrightarrow` 转 OMML、引用块里的标题、
    列表项里的代码块这些要走到写出器才知道。预检若在这里说 0，用户会带着一份
    注定失败的稿子去交付。`check_md` 关掉避免重复预检；`postflight`/`audit`
    关掉——这里只问「能不能写出来」，不重复做成品核对。
    """
    if fmt_file is None:
        return True
    with tempfile.TemporaryDirectory(prefix="md2word_trial_") as td:
        trial = ExportOptions(
            input_path=options.input_path,
            output_path=Path(td) / "trial.docx",
            format_path=fmt_file,
            preset=None,
            check_md=False,
            postflight=False,
            audit=False,
            make_pdf=False,
            lang=res.lang,
            base_template=options.base_template,
            cover_sections=options.cover_sections,
            keep_until=options.keep_until,
            blind_review=options.blind_review,
        )
        outcome = _run_export_pipeline(trial)
    if outcome.ok:
        return True
    res.returncode = EXIT_ERROR
    res.errors.extend(outcome.errors)
    res.diagnostics.extend(outcome.diagnostics)
    return False


def run_validation(options: ExportOptions) -> ExportResult:
    r"""预检 + 临时目录里的完整试导出：不写目标路径，但会生成模板并写临时 .docx。

    试导出用的就是正式写出器，用来发现词表检查覆盖不到的结构错误（`\xrightarrow` 转
    OMML、引用块里的标题、列表项里的代码块）；预检若说 0 而导出立刻失败，作者会收到
    错误的安全信号。与导出共用 `prepare_manuscript` 与 `resolve_format`，读稿与选格式
    不会分叉。
    """
    prep = prepare_manuscript(options)
    res = prep.res
    if not prep.ok:
        return res
    in_p = prep.path
    doc_lang = prep.doc_lang

    fmt_file, fmt_content = resolve_format(
        in_p,
        res,
        format_path=options.format_path,
        preset=options.preset,
        doc_lang=doc_lang,
    )
    if fmt_content is None:
        return res

    # 底模这条路不排版也能验的项：文件能不能读、切点是否唯一、节数够不够。
    # 与导出共用 `_prepare_base_plan`：两边各写一套，`--validate-only` 迟早会说
    # 「没问题」而真正导出立刻失败——对论文工作流是错误的安全信号。
    ok, _plan = _prepare_base_plan(options, res)
    if not ok:
        return res

    logger.info("🔍 " + t("pipeline.precheck", res.lang))
    report = validate_manuscript(in_p, spec_path=fmt_file, lang=res.lang)
    res.errors.extend(report.errors)
    res.diagnostics.extend(report.diagnostics)
    for warning in report.warnings:
        res.messages.append(warning)
        res.warnings.append(warning)
    if report.valid:
        # 稿件合规不等于格式能落成模板、更不等于写得出来：直接用正式写出器试跑一遍。
        # 空格式/只有注释的格式也会在这一步被 `build_template` 拦住。
        if not _trial_export(options, fmt_file, res):
            return res
        res.messages.append(t("pipeline.validate_ok", res.lang, count=len(report.warnings)))
    else:
        res.returncode = EXIT_ERROR
        res.messages.append(t("pipeline.validate_failed", res.lang, count=len(report.errors)))
    return res


def _normalized_csl(path: Path, temp_dir: Path, res: ExportResult) -> Path:
    """把 CSL 里的 direct formatting 去掉，返回可用的路径（就地清理要写副本）。"""
    from md_to_word.transform.csl_clean import is_csl, strip_direct_formatting

    try:
        text, _ = read_text_file(path)
    except (OSError, TextDecodeError):
        return path  # 读不出来就交给 CSL 引擎去报错，不在这里吞掉
    if not is_csl(text):
        return path
    cleaned, removed = strip_direct_formatting(text)
    if not removed:
        return path
    target = temp_dir / "csl-normalized.csl"
    target.write_text(cleaned, encoding="utf-8")
    res.messages.append(
        t("pipeline.csl_normalized", res.lang, name=path.name, attrs=", ".join(removed))
    )
    return target


def _provenance(fmt_file) -> str:
    """产物自证的出处：哪个版本、照哪份格式文件。内容哈希而不是路径——路径换了、
    机器换了，同一份格式文件还是同一个身份，而产物要能逐字节复现。"""
    from md_to_word import __version__   # 延迟导入：包初始化时本模块已经在导入途中

    if fmt_file is None:
        return f"md-to-word {__version__}"
    digest = hashlib.sha256(Path(fmt_file).read_bytes()).hexdigest()[:8]
    return f"md-to-word {__version__} · {Path(fmt_file).name} · sha256:{digest}"


def _postflight_failure(
    in_p: Path, target: Path, res: ExportResult,
    citation_keys: Optional[set[str]] = None,
) -> Optional[tuple[str, str]]:
    """防丢数字、汉字与英文词：通过返回 None，不通过返回 `(code, 错误消息)`。

    同一段检查在两个出口跑：验中间产物（`render_target`），以及灌了底模之后再验成品
    （`out_p`）。原来两处各抄一遍，消息键与取样长度都得改两次——一处走样，同一个问题
    就会有两个措辞。
    """
    all_kept, missing = verify_numeric_integrity(in_p, target, citation_keys)
    if not all_kept:
        return "pipeline.numeric_failed", t(
            "pipeline.numeric_failed", res.lang,
            count=len(missing), sample=", ".join(missing[:5]))
    all_kept, missing = verify_chinese_integrity(in_p, target)
    if not all_kept:
        return "pipeline.chinese_failed", t(
            "pipeline.chinese_failed", res.lang,
            count=len(missing), sample="".join(missing[:12]))
    all_kept, missing = verify_latin_integrity(in_p, target, citation_keys)
    if not all_kept:
        return "pipeline.latin_failed", t(
            "pipeline.latin_failed", res.lang,
            count=len(missing), sample=", ".join(missing[:8]))
    return None


def _resolved_output(options: ExportOptions) -> Path:
    """这次真正会写的 docx 路径（与流水线里的规则同一处）。"""
    if options.output_path:
        return Path(options.output_path).resolve()
    return Path(options.input_path).resolve().with_suffix(".docx")


def _file_snapshot(path: Optional[Path]) -> Optional[tuple[int, int, float]]:
    """文件的 (mtime_ns, size, mtime)；不存在或读不到就是 None。"""
    if path is None or not path.is_file():
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_mtime)


def _output_snapshot(path: Optional[Path]) -> Optional[tuple[int, int, float]]:
    """输出 docx 的快照；不是现存的 .docx 就是 None。"""
    if path is None or path.suffix.lower() != ".docx":
        return None
    return _file_snapshot(path)


def run_export_pipeline(options: ExportOptions) -> ExportResult:
    """执行导出；失败时若目标位置还躺着上一次的成品，明确提醒别拿错。"""
    out_p = _resolved_output(options)
    before = _output_snapshot(out_p)
    pdf_p = out_p.with_suffix(".pdf") if (options.make_pdf and out_p) else None
    before_pdf = _file_snapshot(pdf_p)
    res = _run_export_pipeline(options)
    if options.make_pdf and pdf_p is not None and before_pdf is not None:
        after_pdf = _file_snapshot(pdf_p)
        if res.returncode == EXIT_PDF_SKIPPED and after_pdf is not None and after_pdf[:2] == before_pdf[:2]:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(before_pdf[2]))
            _warn(res, "pipeline.stale_pdf",
                  t("pipeline.stale_pdf", res.lang, path=pdf_p, when=when), file=pdf_p)
    if res.ok or out_p is None or before is None:
        return res
    try:
        # 输出就是稿件本身时，流水线已经按「会覆盖原稿」拦下了；这里不用再补一句旧产物
        same_as_input = os.path.samefile(Path(options.input_path), out_p)
    except OSError:
        same_as_input = False
    if same_as_input:
        return res
    after = _output_snapshot(out_p)
    # 原子替换成功会同时改 mtime 和大小；两者都没动，说明这次根本没写到目标路径
    if after is not None and after[:2] == before[:2]:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(before[2]))
        _warn(res, "pipeline.stale_output",
              t("pipeline.stale_output", res.lang, path=out_p, when=when), file=out_p)
    return res


def _run_export_pipeline(options: ExportOptions) -> ExportResult:
    """执行完整的纯 Python 学术导出流水线。"""
    prep = prepare_manuscript(options)
    res = prep.res
    if not prep.ok:
        return res
    in_p = prep.path
    manuscript_text = prep.text
    doc_lang = prep.doc_lang

    # 1. 确定最终输出路径
    if options.output_path:
        out_p = Path(options.output_path).resolve()
    else:
        out_p = in_p.with_suffix(".docx").resolve()
    # 目录不存在时当场说清楚：否则要等整条流水线跑完、写文件那一刻才抛 FileNotFoundError，
    # 对着 traceback 的人不会想到是自己漏建了一个目录。
    if not out_p.parent.is_dir():
        _fail(res, "pipeline.output_dir_missing",
              t("pipeline.output_dir_missing", res.lang, dir=out_p.parent), file=out_p.parent)
        return res
    # `-o 某个目录` 是常见笔误（把目录当成文件名传进来），python-docx 会抛 IsADirectoryError，
    # 到时候看到的是 zipfile 的 traceback——这里先拦住。
    if out_p.is_dir():
        _fail(res, "pipeline.output_is_dir",
              t("pipeline.output_is_dir", res.lang, path=out_p), file=out_p)
        return res
    # `-o 稿件.md` 会把 Markdown 原地覆盖成 docx。这是不可恢复的数据损失，必须先拦。
    try:
        same_file = os.path.samefile(in_p, out_p)
    except OSError:
        same_file = out_p == in_p
    if same_file:
        _fail(res, "pipeline.output_is_input",
              t("pipeline.output_is_input", res.lang, path=in_p), file=out_p)
        return res
    # `.pdf` 是 `--pdf` 的产物名。把 OOXML 写进 `.pdf` 不只是扩展名难看：加 `--pdf`
    # 时渲染目标与 docx 目标会重合，PDF 会把刚写好的 docx 覆盖掉。
    if out_p.suffix.lower() != ".docx":
        _fail(res, "pipeline.output_not_docx",
              t("pipeline.output_not_docx", res.lang, path=out_p), file=out_p)
        return res

    # 2. 确定格式 (Format Spec)
    fmt_file, fmt_content = resolve_format(
        in_p,
        res,
        format_path=options.format_path,
        preset=options.preset,
        doc_lang=doc_lang,
    )
    if fmt_content is None:
        return res

    # 3. 底模的前置条件在渲染前查完：底模不存在、切点歧义、兼容模式不一致，
    #     都不该等整篇排完才说。与 `--validate-only` 共用同一份判断。
    ok, base_plan = _prepare_base_plan(options, res)
    if not ok:
        return res
    # 学校模板常常与稿件同名、同目录；不传 -o 时默认输出正好就是底模本身。
    # 这跟「-o 稿件.md」一样是不可恢复的数据损失，必须在写第一个字节前拦下。
    if base_plan is not None:
        try:
            same_base = os.path.samefile(base_plan.base, out_p)
        except OSError:
            same_base = base_plan.base.resolve() == out_p
        if same_base:
            _fail(res, "pipeline.output_is_dependency",
                  t("pipeline.output_is_dependency", res.lang, path=out_p), file=out_p)
            return res

    # 格式文件写错时预检会给出带行号的原因；这里读不出就用默认。
    # 顺带定下本次的**文档语言**：格式的 `校对语言：` 优先，没有才用正文判定。
    # 否则英文稿里一段长中文引文会把 CSL、交叉引用前缀、公式编号外观一起翻成中文，
    # 而 `--preset en-nature` 只换了版式，正文里却印着「式（1）」和 GB/T 文献表。
    try:
        spec = parse_format(fmt_content, lang=res.lang)
    except ValueError:
        spec = None
    # 个别规范字体（尤其公文的「方正小标宋简体」）不是系统自带。缺字体时 Word 会
    # 静默替换，用户只看「导出成功」发现不了；这里至少提前说一句。
    if spec:
        optional = [
            font for font in ("方正小标宋简体", "方正小标宋_GBK", "方正大标宋简体")
            if any(font in (s.get("font_name") or []) for s in spec.styles)
        ]
        for font in dict.fromkeys(optional):
            _warn(res, "pipeline.optional_font",
                  t("pipeline.optional_font", res.lang, font=font), file=fmt_file)
    fmt_lang = lang_from_proofing(spec.proofing_lang) if spec else None
    if fmt_lang:
        if fmt_lang != doc_lang:
            _warn(res, "pipeline.doc_lang_format", t(
                "pipeline.doc_lang_format", res.lang,
                fmt=fmt_lang, detected=doc_lang,
            ), file=fmt_file)
        doc_lang = fmt_lang
        res.doc_lang = doc_lang

    # 4. 导前预检门禁 (Validator)
    if options.check_md:
        logger.info("🔍 " + t("pipeline.precheck", res.lang))
        v_report = validate_manuscript(
            in_p, spec_path=fmt_file, lang=res.lang
        )
        # 预检的结构化诊断原样并入结果：`--json` 的消费方拿到的行号与 code
        # 与 `--validate-only` 是同一份，不在这里重新拼。提醒也要同时进
        # `messages/warnings`——否则 diagnostics 里有 warning、人读视图里没有，
        # 两个出口又成了各说各话。失败时同样如此：提醒对修稿仍然有用。
        res.diagnostics.extend(v_report.diagnostics)
        for w in v_report.warnings:
            res.messages.append(w)
            res.warnings.append(w)
        if not v_report.valid:
            _fail(res, "pipeline.rejected",
                  t("pipeline.rejected", res.lang, count=len(v_report.errors)))
            res.errors.extend(v_report.errors)
            return res

    # 5. 准备工作环境与 CSL 解析
    render_target: Optional[Path] = None
    injected_target: Optional[Path] = None
    temp_dir = tempfile.mkdtemp(prefix="md2word_")
    try:
        # HTML 注释是写给人看的编辑批注，任何 Markdown 渲染器都不显示；原样印进 Word
        # 属于把批注当正文。这里无条件剔除，不给开关——代码块里的内容不受影响。
        contract_text = strip_html_comments(manuscript_text)

        # frontmatter 只解析这一次；`csl:` 的路径解析放到真正建引文引擎时。
        # 预检正常时会先报 YAML 错误；`--no-check` 或直接调库时也要给出结构化失败，
        # 不能 `except Exception: pass` 后悄悄换默认样式。
        fm_data: dict = {}
        fm_raw, _ = split_frontmatter(contract_text)
        if fm_raw:
            import yaml
            try:
                loaded = yaml.safe_load(fm_raw)
            except yaml.YAMLError as exc:
                _fail(res, "gate.yaml.parse_failed",
                      t("gate.yaml.parse_failed", res.lang, err=exc), file=in_p)
                return res
            if loaded is not None and not isinstance(loaded, dict):
                # 与预检用同一条文案：`--no-check` 时这里是唯一的报错出口，
                # 两套措辞会让同一个问题在不同开关下有不同说法。
                _fail(res, "gate.yaml.not_mapping",
                      t("gate.yaml.not_mapping", res.lang,
                        kind=type(loaded).__name__), file=in_p)
                return res
            fm_data = loaded or {}

        # 临时模板生成
        if not fmt_content:
            _fail(res, "pipeline.no_spec", t("pipeline.no_spec", res.lang))
            return res
        # 产物先写到输出目录里的临时文件：所有门禁都在它上面跑，全通过才换到目标路径。
        # 这样门禁失败时目标位置要么没有文件、要么还是上一次的成品，不会留一份“看着能交”
        # 的坏文件。放在输出目录而不是系统临时目录，是为了最后一步能用原子替换。
        if options.base_template:
            render_target = Path(temp_dir) / "rendered.docx"
        else:
            try:
                fd, tmp_name = tempfile.mkstemp(
                    prefix=f".{out_p.stem}.", suffix=".docx", dir=out_p.parent
                )
            except OSError as exc:
                _fail(res, "pipeline.write_failed",
                      t("pipeline.write_failed", res.lang, path=out_p, err=exc), file=out_p)
                return res
            os.close(fd)
            render_target = Path(tmp_name)
        temp_tpl_path = Path(temp_dir) / "template.docx"
        try:
            build_template(fmt_content, temp_tpl_path, lang=res.lang, doc_lang=doc_lang)
        except TemplateError as exc:
            _fail(res, "pipeline.format_template_failed",
                  t("pipeline.format_template_failed", res.lang, reason=exc), file=fmt_file)
            return res
        tpl_for_render = temp_tpl_path

        # 6. 契约文本 → 文档模型 → OOXML
        from md_to_word.model.reader import MarkdownError, read_markdown
        from md_to_word.writer import UnsupportedFeature, write_docx

        citation_keys: set[str] = set()
        bib_text = ""
        if isinstance(fm_data, dict) and fm_data.get("bibliography"):
            bib_path, how = resolve_manuscript_path(str(fm_data["bibliography"]), in_p)
            if how:
                bib_text = _read_user_text(
                    Path(bib_path), "textio.label.bibliography", res
                )
                if bib_text is None:
                    return res
                from md_to_word.transform.biblio import bibliography_problem

                problem = bibliography_problem(bib_text, res.lang)
                if problem:
                    _fail(res, "gate.bib.json", problem, file=bib_path)
                    return res
                from md_to_word.transform.biblio import bibliography_keys

                citation_keys = bibliography_keys(bib_text)

        engine = None
        if citation_keys:
            from md_to_word.transform.citations import CitationEngine, CitationError

            csl_path = None
            if fm_data.get("csl"):
                resolved, how = resolve_manuscript_path(
                    str(fm_data["csl"]), in_p, skill_csl_dir=get_csl_dir()
                )
                if how:
                    csl_path = resolved
            if csl_path is None:
                csl_path = default_csl_path_for_lang(doc_lang)
            # 用户自带的 CSL：现场剥掉会覆盖模板的 direct formatting（内置样式发布前已规范化）。
            # 不这么做的话，同一份要求文件换个 CSL，悬挂缩进与行距就跟着变。
            csl_path = _normalized_csl(csl_path, Path(temp_dir), res)
            from md_to_word.transform.bibtex import crossref_keys

            inherited = crossref_keys(bib_text)
            if inherited:
                _warn(res, "bib.crossref_not_inherited", t(
                    "bib.crossref_not_inherited", res.lang,
                    keys=join_terms(inherited[:5], res.lang),
                ))
            try:
                engine = CitationEngine(bib_text, csl_path, res.lang, citation_lang=doc_lang)
            except (CitationError, OSError) as exc:
                _fail(res, "pipeline.csl_error",
                      t("pipeline.csl_error", res.lang, reason=exc), file=csl_path)
                return res

        try:
            model = read_markdown(contract_text, citation_keys=citation_keys)
            if engine is not None:
                # 年份后缀要在第一次渲染之前定下来（同作者同年的多条文献编 a/b/c），
                # 而引擎是在模型读出来之前建的，所以这里把真正引用到的 key 交回去
                from md_to_word.transform.citations import cited_keys

                keys = cited_keys(model)
                engine.reserve(keys)
                # 兜底：预检本该拦下「引了不存在的 key」，但只要有一条漏过去，
                # 渲染期就会从 citeproc 深处抛 CitationError，被兜底成
                # 「未预料到的内部错误…请把 traceback 发给维护者」——那是错的归因。
                missing_keys = [k for k in dict.fromkeys(keys) if not engine.has(k)]
                if missing_keys:
                    _fail(res, "pipeline.citation_failed", t(
                        "pipeline.citation_failed", res.lang,
                        reason=join_terms(missing_keys[:5], res.lang),
                    ), file=in_p)
                    return res
            write_docx(
                model,
                tpl_for_render,
                render_target,
                citations=engine,
                base_dir=in_p.parent,
                equation_number_format=spec.equation_number_format if spec else "",
                appendix_equation_number_format=(
                    spec.appendix_equation_number_format if spec else ""
                ),
                equation_number_placement=spec.equation_number if spec else "right",
                no_row_split=bool(spec and spec.table.get("no_row_split")),
                # 「跨页重复」写在「表头：」那一行，落在 spec.table_header，不是 spec.table
                repeat_header=bool(spec and spec.table_header
                                  and spec.table_header.get("repeat_header")),
                # 「表后间距」写在「表格：」那一行：表格没有段前段后，留白由垫片撑
                table_space_after=float(spec.table.get("space_after_pt") or 0) if spec else 0.0,
                provenance=_provenance(fmt_file),
                header_styles=(
                    {r["style_name"] for r in spec.styles if r.get("join_header")}
                    if spec
                    else None
                ),
                lang=res.lang,
                doc_lang=doc_lang,
                section_roles=spec.section_roles if spec else None,
            )
        except MarkdownError as exc:
            _fail(res, "pipeline.markdown_error", t(
                "pipeline.markdown_error", res.lang,
                reason=t(exc.code, res.lang, line=exc.line, **exc.params),
            ), line=exc.line, file=in_p)
            return res
        except UnsupportedFeature as exc:
            _fail(res, "pipeline.unsupported",
                  t("pipeline.unsupported", res.lang, reason=exc), file=in_p)
            return res
        except OSError as exc:
            # 目录只读、磁盘满、文件被 Word 占着：都是"写不进去"，不该甩 traceback。
            _fail(res, "pipeline.write_failed",
                  t("pipeline.write_failed", res.lang, path=out_p, err=exc), file=out_p)
            return res

        # 7. 产物数值防丢检查 (Audit: Post-flight)
        if options.postflight:
            failure = _postflight_failure(in_p, render_target, res, citation_keys)
            if failure:
                _fail(res, failure[0], failure[1], file=out_p)
                return res
            logger.info("✓ " + t("pipeline.numeric_ok", res.lang))

        # 8. 格式要求逐条对账 (Audit: Inspector)
        if options.audit and fmt_file:
            matched, problems = audit_docx_against_spec(render_target, fmt_file, res.lang)
            if not matched:
                _fail(res, "pipeline.audit_failed",
                      t("pipeline.audit_failed", res.lang, count=len(problems)),
                      file=fmt_file)
                for cat, msg in problems:
                    res.errors.append(f"  [{cat}] {msg}")
                return res
            logger.info("✓ " + t("pipeline.audit_ok", res.lang))

        # 9. 盲审清理：在临时产物上做，清理失败不发布
        if options.blind_review and not _blind_review(res, render_target, out_p):
            return res

        # 10. 普通导出：门禁全过之后才把临时产物换到目标路径
        if not options.base_template:
            try:
                os.replace(render_target, out_p)
            except OSError as exc:
                _fail(res, "pipeline.write_failed",
                      t("pipeline.write_failed", res.lang, path=out_p, err=exc), file=out_p)
                return res
            render_target = None
            res.output_docx = out_p

        # 11. 灌进学校模板：封面原样保留，正文换成我们排的
        if options.base_template and base_plan is not None:
            from md_to_word.template.base_inject import (
                BaseTemplateError,
                apply_base_template,
                inspect_base,
            )

            base_p = base_plan.base
            origin_base = base_p
            sections = base_plan.sections
            if base_plan.cut_at_paragraph:
                # 命中段落是最后一行：先在它之后插一个分节符，再把切出来的底模按
                # 「保留 sections 节」灌入。单节和多节走同一条路。
                derived = Path(temp_dir) / "base-cut.docx"
                try:
                    from md_to_word.template.base_inject import paragraph_cut

                    sections = paragraph_cut(base_p, options.keep_until, derived, res.lang)
                except BaseTemplateError as exc:
                    _fail(res, "pipeline.base_failed",
                          t("pipeline.base_failed", res.lang, reason=exc.reason), file=base_p)
                    return res
                base_p = derived
                report = inspect_base(base_p, sections, res.lang)
                if not report.ok:
                    _fail(res, "pipeline.base_failed",
                          t("pipeline.base_failed", res.lang,
                            reason=_join(report.blocking, res.lang)), file=base_p)
                    return res
            try:
                # 注入也先落到输出目录里的临时文件：注入后的完整性检查不过，目标位置的
                # 上一份成品仍然完好。
                try:
                    fd, tmp_name = tempfile.mkstemp(
                        prefix=f".{out_p.stem}.", suffix=".docx", dir=out_p.parent
                    )
                except OSError as exc:
                    _fail(res, "pipeline.write_failed",
                          t("pipeline.write_failed", res.lang, path=out_p, err=exc), file=out_p)
                    return res
                os.close(fd)
                injected_target = Path(tmp_name)
                outcome = apply_base_template(
                    base_p, render_target, sections, injected_target,
                    _first_texts(model.blocks), res.lang,
                    blind_review=options.blind_review,
                    origin=origin_base,
                )
            except BaseTemplateError as exc:
                _fail(res, "pipeline.base_failed",
                      t("pipeline.base_failed", res.lang, reason=exc.reason), file=base_p)
                res.errors.extend(f"  {n}" for n in exc.notes)
                return res
            for note in outcome.notes:
                _warn(res, "pipeline.base_note", note, file=base_p)
            # 上面第 8、9 步验的是 `render_target`——灌底模时那是临时目录里的中间产物。
            # 用户拿到的是 `out_p`；注入本身可能丢字（前几节被切、关系被重写），所以防丢内容
            # 要在成品上再跑一遍。格式对账不重跑：成品里混着学校的前置件与它自己的样式，
            # 逐条对账会把它判成「不合规」，那些本来就不是我们排的。
            if options.postflight:
                failure = _postflight_failure(in_p, injected_target, res, citation_keys)
                if failure:
                    _fail(res, failure[0], failure[1], file=out_p)
                    return res
                logger.info("✓ " + t("pipeline.numeric_ok", res.lang))
            if options.blind_review and not _blind_review(res, injected_target, out_p):
                return res
            try:
                os.replace(injected_target, out_p)
            except OSError as exc:
                _fail(res, "pipeline.write_failed",
                      t("pipeline.write_failed", res.lang, path=out_p, err=exc), file=out_p)
                return res
            injected_target = None
            res.output_docx = out_p
            # 「逐页一致」只有真排过版才说得出口
            key = "pipeline.base_ok" if outcome.layout_verified else "pipeline.base_ok_structure"
            logger.info("✓ " + t(key, res.lang, pages=outcome.cover_sections))

        # 12. 可选 PDF 渲染 (Visual QA)
        if options.make_pdf:
            pdf_path = out_p.with_suffix(".pdf")
            # 先渲染到临时文件、成功后再替换：Word/AppleScript 中途失败时，不能把
            # 一半的 PDF 留在最终路径上，也不能让上一次的旧 PDF 混进来。
            # 临时文件必须和成品同盘（`out_p.parent`），不能放系统临时目录：
            # 输出到外接盘/独立挂载卷时，`os.replace` 会因 EXDEV 失败，渲染成功却报跳过。
            staged_pdf: Path | None = None
            try:
                fd, staged_name = tempfile.mkstemp(
                    dir=out_p.parent, prefix=".md-to-word-pdf-", suffix=".pdf")
                os.close(fd)
                staged_pdf = Path(staged_name)
                staged_pdf.unlink()  # 交给 Word 新建；空文件可能被 AppleScript 拒绝
                success, reason = render_pdf_via_word(out_p, staged_pdf)
                if success:
                    os.replace(staged_pdf, pdf_path)
                    staged_pdf = None
            except OSError as exc:
                # 输出目录不可写、Word 正在占用目标文件……都只是「PDF 没做成」，
                # 不能连已经写好的 .docx 一起判失败，更不能留下隐藏临时文件。
                success, reason = False, str(exc)
            finally:
                if staged_pdf is not None:
                    staged_pdf.unlink(missing_ok=True)
            if success:
                res.output_pdf = pdf_path
                logger.info("🖨️ " + t("pipeline.pdf_ok", res.lang, path=pdf_path))
            else:
                res.messages.append(f"MD2WORD_SKIP kind=pdf-render reason={reason}")
                res.pdf_skip_reason = str(reason or "")
                res.returncode = EXIT_PDF_SKIPPED

        logger.info("✅ " + t("pipeline.success", res.lang, path=out_p))
        # 机器验得了文字与结构，验不了"看起来对不对"。表格行高列宽按内容自适应、公式与
        # 题注的实际落版、页眉页脚——这些只有拿真 Word 打开才知道。统一提醒一次，
        # 别让"门禁全绿"被当成"版面没问题"。
        res.messages.append(t("pipeline.reminder", res.lang))
        return res

    finally:
        # 门禁失败或中途异常时，清理输出目录里的临时产物；目标路径保持原样。
        for leftover in (render_target, injected_target):
            if leftover is not None:
                try:
                    Path(leftover).unlink(missing_ok=True)
                except OSError:
                    pass
        shutil.rmtree(temp_dir, ignore_errors=True)
