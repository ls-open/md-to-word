"""md_to_word.pipeline — 现代学术 Word 导出总编排流水线（纯 Python 跨平台实现）。

串联 8 大解耦领域模块，接管原 bash 脚本编排逻辑，支持在 Windows、macOS 与 Linux 原生运行。
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from md_to_word.audit.inspector import audit_docx_against_spec
from md_to_word.audit.postflight import verify_numeric_integrity
from md_to_word.config import default_csl_path, get_csl_dir, resolve_preset_path
from md_to_word.i18n import resolve_lang, t
from md_to_word.preprocessor.cleaner import strip_html_comments
from md_to_word.template.builder import build_template
from md_to_word.validator.check import validate_manuscript
from md_to_word.visual_qa.word_pdf import render_pdf_via_word
from md_to_word.utils.skill_utils import split_frontmatter, resolve_manuscript_path

logger = logging.getLogger("md2word")


@dataclass
class ExportOptions:
    """导出配置选项。"""

    input_path: Path | str
    output_path: Optional[Path | str] = None
    requirements_path: Optional[Path | str] = None
    preset: Optional[str] = None
    template_path: Optional[Path | str] = None
    strip_comments: bool = False
    check_md: bool = True
    postflight: bool = True
    audit: bool = True
    make_pdf: bool = False
    eq_number_style: str = "asis"  # asis=(5.1) | cjk=（5-1）
    lang: Optional[str] = None  # 消息语言：None=按稿件语种 | "zh" | "en"


@dataclass
class ExportResult:
    """流水线执行结果。"""

    returncode: int  # 0=成功, 1=错误/门禁失败, 3=DOCX 成功但 PDF 抽查跳过
    output_docx: Optional[Path] = None
    output_pdf: Optional[Path] = None
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    lang: str = "zh"


def run_export_pipeline(options: ExportOptions) -> ExportResult:
    """执行完整的纯 Python 学术导出流水线。"""
    res = ExportResult(returncode=0)
    in_p = Path(options.input_path).resolve()
    if not in_p.is_file():
        res.returncode = 1
        res.errors.append(t("pipeline.input_missing", res.lang, path=in_p))
        return res
    try:
        manuscript_text = in_p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        manuscript_text = ""
    res.lang = resolve_lang(manuscript_text, options.lang)

    # 1. 确定最终输出路径
    if options.output_path:
        out_p = Path(options.output_path).resolve()
    else:
        out_p = in_p.with_suffix(".docx").resolve()
    res.output_docx = out_p

    # 2. 确定格式要求 (Requirements Spec)
    req_file: Optional[Path] = None
    req_content: Optional[str] = None

    if options.requirements_path:
        p_req = Path(options.requirements_path).resolve()
        if not p_req.is_file():
            res.returncode = 1
            res.errors.append(t("pipeline.requirements_missing", res.lang, path=p_req))
            return res
        req_file = p_req
        req_content = p_req.read_text(encoding="utf-8")
    elif options.preset:
        p_pre = resolve_preset_path(options.preset)
        if not p_pre or not p_pre.is_file():
            res.returncode = 1
            res.errors.append(t("pipeline.preset_missing", res.lang, name=options.preset))
            return res
        req_file = p_pre
        req_content = p_pre.read_text(encoding="utf-8")
    else:
        # 寻找同目录唯一 .txt
        txt_candidates = list(in_p.parent.glob("*.txt"))
        if len(txt_candidates) == 1 and txt_candidates[0].is_file():
            req_file = txt_candidates[0]
            req_content = req_file.read_text(encoding="utf-8")
        elif len(txt_candidates) > 1 and not options.template_path:
            res.returncode = 1
            res.errors.append(t("pipeline.many_txt", res.lang, dir=in_p.parent))
            return res
        elif not options.template_path:
            # 默认兜底走中文学术预设
            p_default = resolve_preset_path("zh-academic")
            if p_default and p_default.is_file():
                req_file = p_default
                req_content = p_default.read_text(encoding="utf-8")

    # 3. 模板解析
    custom_template: Optional[Path] = None
    if options.template_path:
        p_tpl = Path(options.template_path).resolve()
        if not p_tpl.is_file():
            res.returncode = 1
            res.errors.append(t("pipeline.template_missing", res.lang, path=p_tpl))
            return res
        custom_template = p_tpl

    # 按章编号 + 编号外观仍是默认 → 多半是漏带了 --eq-number-style cjk。
    # **这一项没有任何闸门能发现**：漏了就是静默产出 (5.1)（点号、半角括号），
    # 三道闸门全部照绿。只提醒、不阻断：英文稿开了 chapters 而用 (5.1) 是合法的。
    if options.eq_number_style == "asis":
        if re.search(r"^chapters:\s*true", manuscript_text, re.MULTILINE) and "{#eq-" in manuscript_text:
            res.messages.append(t("pipeline.eq_cjk_hint", res.lang))

    # 4. 导前预检门禁 (Validator)
    if options.check_md:
        logger.info("🔍 " + t("pipeline.precheck", res.lang))
        v_report = validate_manuscript(in_p, template_docx=custom_template, spec_path=req_file)
        if not v_report.valid:
            res.returncode = 1
            res.errors.append(t("pipeline.rejected", res.lang, count=len(v_report.errors)))
            res.errors.extend(v_report.errors)
            return res
        for w in v_report.warnings:
            logger.warning(f"⚠️ {w}")

    # 5. 准备工作环境与 CSL 解析
    temp_dir = tempfile.mkdtemp(prefix="md2word_")
    try:
        contract_text = in_p.read_text(encoding="utf-8")
        if options.strip_comments:
            contract_text = strip_html_comments(contract_text)

        # 引文样式：作者写了就按作者的（内置名或自己的路径），没写按语种取默认
        builtin_csl: Optional[Path] = None
        fm_data: dict = {}
        fm_raw, _ = split_frontmatter(contract_text)
        if fm_raw:
            import yaml
            try:
                fm_data = yaml.safe_load(fm_raw)
                if isinstance(fm_data, dict) and fm_data.get("csl"):
                    p, how = resolve_manuscript_path(
                        str(fm_data["csl"]), in_p, skill_csl_dir=get_csl_dir()
                    )
                    if how == "skill-builtin":
                        builtin_csl = p
            except Exception:
                pass

        # 未声明 csl: 时给一个确定的默认（中文稿 GB/T 数字制、其余 APA），
        # 让「什么都不写」也有可预期、可复现的结果。
        if (
            isinstance(fm_data, dict)
            and fm_data.get("bibliography")
            and not fm_data.get("csl")  # 作者声明的 csl 优先，哪怕它不是内置样式
        ):
            builtin_csl = default_csl_path(contract_text)

        # 临时模板生成
        tpl_for_render = custom_template
        if not tpl_for_render:
            if not req_content:
                res.returncode = 1
                res.errors.append(t("pipeline.no_spec", res.lang))
                return res
            temp_tpl_path = Path(temp_dir) / "template.docx"
            build_template(req_content, temp_tpl_path, lang=res.lang)
            tpl_for_render = temp_tpl_path

        # 6. 契约文本 → 文档模型 → OOXML
        from md_to_word.model.reader import read_markdown
        from md_to_word.utils.skill_utils import parse_bib_keys
        from md_to_word.writer import UnsupportedFeature, write_docx

        citation_keys: set[str] = set()
        bib_text = ""
        if isinstance(fm_data, dict) and fm_data.get("bibliography"):
            bib_path, how = resolve_manuscript_path(str(fm_data["bibliography"]), in_p)
            if how:
                try:
                    bib_text = Path(bib_path).read_text(encoding="utf-8")
                    citation_keys = parse_bib_keys(bib_text)
                except OSError:
                    citation_keys = set()

        engine = None
        if citation_keys:
            from md_to_word.transform.citations import CitationEngine, CitationError

            csl_path = builtin_csl
            if csl_path is None and isinstance(fm_data, dict) and fm_data.get("csl"):
                resolved, how = resolve_manuscript_path(
                    str(fm_data["csl"]), in_p, skill_csl_dir=get_csl_dir()
                )
                if how:
                    csl_path = resolved
            if csl_path is None:
                csl_path = default_csl_path(contract_text)
            try:
                engine = CitationEngine(bib_text, csl_path)
            except (CitationError, OSError) as exc:
                res.returncode = 1
                res.errors.append(t("pipeline.csl_error", res.lang, reason=exc))
                return res

        try:
            model = read_markdown(contract_text, citation_keys=citation_keys)
            write_docx(
                model,
                tpl_for_render,
                out_p,
                citations=engine,
                base_dir=in_p.parent,
                eq_number_style=options.eq_number_style,
            )
        except UnsupportedFeature as exc:
            res.returncode = 1
            res.errors.append(t("pipeline.unsupported", res.lang, reason=exc))
            return res

        # 8. 产物数值防丢检查 (Audit: Post-flight)
        if options.postflight:
            all_kept, missing = verify_numeric_integrity(in_p, out_p)
            if not all_kept:
                res.returncode = 1
                res.errors.append(
                    t("pipeline.numeric_failed", res.lang,
                      count=len(missing), sample=", ".join(missing[:5]))
                )
                return res
            logger.info("✓ " + t("pipeline.numeric_ok", res.lang))

        # 9. 格式要求逐条对账 (Audit: Inspector)
        if options.audit and req_file:
            matched, problems = audit_docx_against_spec(out_p, req_file)
            if not matched:
                res.returncode = 1
                res.errors.append(t("pipeline.audit_failed", res.lang, count=len(problems)))
                for cat, msg in problems:
                    res.errors.append(f"  [{cat}] {msg}")
                return res
            logger.info("✓ " + t("pipeline.audit_ok", res.lang))

        # 10. 可选 PDF 渲染 (Visual QA)
        if options.make_pdf:
            pdf_path = out_p.with_suffix(".pdf")
            success, reason = render_pdf_via_word(out_p, pdf_path)
            if success:
                res.output_pdf = pdf_path
                logger.info("🖨️ " + t("pipeline.pdf_ok", res.lang, path=pdf_path))
            else:
                res.messages.append(f"MD2WORD_SKIP kind=pdf-render reason={reason}")
                res.returncode = 3

        logger.info("✅ " + t("pipeline.success", res.lang, path=out_p))
        # 机器验得了文字与结构，验不了"看起来对不对"。表格行高列宽按内容自适应、公式与
        # 题注的实际落版、页眉页脚——这些只有拿真 Word 打开才知道。统一提醒一次，
        # 别让"门禁全绿"被当成"版面没问题"。
        res.messages.append(t("pipeline.reminder", res.lang))
        return res

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
