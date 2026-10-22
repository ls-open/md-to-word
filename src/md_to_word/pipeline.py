"""md_to_word.pipeline — 现代学术 Word 导出总编排流水线（纯 Python 跨平台实现）。

串联 8 大解耦领域模块，接管原 bash 脚本编排逻辑，支持在 Windows、macOS 与 Linux 原生运行。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from md_to_word.audit.inspector import audit_docx_against_spec
from md_to_word.audit.postflight import verify_numeric_integrity
from md_to_word.config import resolve_preset_path
from md_to_word.postprocessor.equations import postprocess_docx
from md_to_word.preprocessor.blocks import expand_style_lines
from md_to_word.preprocessor.cleaner import strip_html_comments
from md_to_word.preprocessor.markers import expand_markers
from md_to_word.renderer.quarto import QuartoRenderer, check_quarto_environment
from md_to_word.spec.parser import parse_requirements
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
    eq_number_style: str = "asis"  # asis | cjk
    writer: str = "pandoc"  # pandoc（默认，成熟通道）| native（自研写出器）


@dataclass
class ExportResult:
    """流水线执行结果。"""

    returncode: int  # 0=成功, 1=错误/门禁失败, 3=DOCX成功但PDF抽查跳过
    output_docx: Optional[Path] = None
    output_pdf: Optional[Path] = None
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_export_pipeline(options: ExportOptions) -> ExportResult:
    """执行完整的纯 Python 学术导出流水线。"""
    res = ExportResult(returncode=0)
    in_p = Path(options.input_path).resolve()
    if not in_p.is_file():
        res.returncode = 1
        res.errors.append(f"输入稿件不存在: {in_p}")
        return res

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
            res.errors.append(f"指定的格式要求文件不存在: {p_req}")
            return res
        req_file = p_req
        req_content = p_req.read_text(encoding="utf-8")
    elif options.preset:
        p_pre = resolve_preset_path(options.preset)
        if not p_pre or not p_pre.is_file():
            res.returncode = 1
            res.errors.append(f"未找到预设: {options.preset}")
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
            res.errors.append(
                f"在 {in_p.parent} 下找到多个 .txt 文件，无法判断哪份是格式要求。\n"
                f"  建议加 -r 指定其中一份，或使用 --preset zh-academic/en-nature。"
            )
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
            res.errors.append(f"指定的模板文件不存在: {p_tpl}")
            return res
        custom_template = p_tpl

    spec = None
    if req_content:
        try:
            spec = parse_requirements(req_content)
        except ValueError:
            spec = None  # 要求文件写法有问题时，预检会给出带行号的原因

    # 3.5 渲染引擎体检：只有走 Pandoc 通道才需要 Quarto。
    # 自研写出器不碰 Quarto，装了没装与它无关——这正是「内化」的意义。
    if options.writer != "native":
        quarto_version, env_errors, env_warnings = check_quarto_environment()
        if env_errors:
            res.returncode = 2
            res.errors.extend(env_errors)
            return res
        res.messages.extend(env_warnings)
        if quarto_version:
            res.messages.append(f"渲染引擎: Quarto {'.'.join(map(str, quarto_version))}")

    # 按章编号 + 编号外观仍是默认 → 多半是漏带了 --eq-number-style cjk。
    # **这一项没有任何闸门能发现**：漏了就是静默产出 (5.1)（点号、半角括号），
    # 三道闸门全部照绿。只提醒、不阻断：英文稿开了 chapters 而用 (5.1) 是合法的。
    if options.eq_number_style == "asis":
        _text = in_p.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^chapters:\s*true", _text, re.MULTILINE) and "{#eq-" in _text:
            res.messages.append(
                "提示: 稿件 YAML 开了 crossref.chapters（按章编号），但公式编号外观是默认的 (5.1)。"
                "中文学位论文通常写作 （5-1）——需要的话加 --eq-number-style cjk。"
            )

    # 4. 导前预检门禁 (Validator)
    if options.check_md:
        logger.info("🔍 执行导出前语法与排版契约预检...")
        v_report = validate_manuscript(in_p, template_docx=custom_template, spec_path=req_file)
        if not v_report.valid:
            res.returncode = 1
            res.errors.extend(v_report.errors)
            return res
        for w in v_report.warnings:
            logger.warning(f"⚠️ {w}")

    # 5. 准备工作环境与 CSL 解析
    temp_dir = tempfile.mkdtemp(prefix="md2word_")
    expanded_md_file: Optional[Path] = None
    try:
        raw_text = in_p.read_text(encoding="utf-8")
        if options.strip_comments:
            raw_text = strip_html_comments(raw_text)
        # `%% 摘要 …` 这类段落样式行先翻译成 Pandoc 的 fenced div，再交给标记展开
        raw_text = expand_style_lines(raw_text)

        # 解析 CSL 路径（若是内置 CSL 自动转为绝对路径）
        builtin_csl: Optional[Path] = None
        fm_data: dict = {}
        fm_raw, _ = split_frontmatter(raw_text)
        if fm_raw:
            import yaml
            try:
                fm_data = yaml.safe_load(fm_raw)
                if isinstance(fm_data, dict) and fm_data.get("csl"):
                    from md_to_word.config import get_csl_dir
                    p, how = resolve_manuscript_path(
                        str(fm_data["csl"]), in_p, skill_csl_dir=get_csl_dir()
                    )
                    if how == "skill-builtin":
                        builtin_csl = p
            except Exception:
                pass

        # 中文稿的交叉引用前缀：要求文件声明了中文校对语言时，替用户补上默认值。
        # 用 --metadata-file 而不是改稿：Pandoc 里稿件 YAML 优先级更高，用户写了就以用户的为准。
        meta_file: Optional[Path] = None
        if spec is not None and (spec.proofing_lang or "").lower().startswith("zh"):
            declared = isinstance(fm_data, dict) and isinstance(fm_data.get("crossref"), dict)
            has_labels = bool(re.search(r"\{#(?:eq|fig|tbl)-", raw_text))
            if has_labels and not declared:
                meta_file = Path(temp_dir) / "defaults.yml"
                meta_file.write_text(
                    'crossref:\n  eq-prefix: "式"\n  fig-prefix: "图"\n  tbl-prefix: "表"\n',
                    encoding="utf-8",
                )
                res.messages.append("中文稿未写 crossref 前缀，已按「式/图/表」补默认值（稿件里写了则以稿件为准）。")

        # 临时模板生成
        tpl_for_render = custom_template
        if not tpl_for_render:
            if not req_content:
                res.returncode = 1
                res.errors.append("未提供格式要求或模板，无法生成样式文档。")
                return res
            temp_tpl_path = Path(temp_dir) / "template.docx"
            build_template(req_content, temp_tpl_path)
            tpl_for_render = temp_tpl_path

        # v3 自研写出器：模型 → OOXML，跳过 Quarto 渲染与后处理
        if options.writer == "native":
            from md_to_word.model.reader import read_markdown
            from md_to_word.utils.skill_utils import parse_bib_keys
            from md_to_word.writer import UnsupportedFeature, write_docx

            citation_keys: set[str] = set()
            if isinstance(fm_data, dict) and fm_data.get("bibliography"):
                bib_path, how = resolve_manuscript_path(str(fm_data["bibliography"]), in_p)
                if how:
                    try:
                        citation_keys = parse_bib_keys(Path(bib_path).read_text(encoding="utf-8"))
                    except Exception:
                        citation_keys = set()
            try:
                model = read_markdown(raw_text, citation_keys=citation_keys)
                write_docx(model, tpl_for_render, out_p)
            except UnsupportedFeature as exc:
                res.returncode = 1
                res.errors.append(
                    f"自研写出器尚不支持该结构：{exc}\n"
                    f"  可加 --writer pandoc 走成熟通道，或在 Word 里补完这一处。"
                )
                return res
            res.messages.append("写出后端: 自研（native）")
        else:
            # 标记展开副本必须落在原稿同目录，以保持图片与文献的相对路径生效
            expanded_text, marker_counts = expand_markers(raw_text, template_path=tpl_for_render)
            expanded_md_file = in_p.parent / f"._{in_p.stem}_expanded_{os.getpid()}.md"
            expanded_md_file.write_text(expanded_text, encoding="utf-8")

            # 6. 编译渲染 (Renderer)
            logger.info("⚙️ 调用渲染引擎编译 Markdown 到 Word DOCX...")
            renderer = QuartoRenderer()
            try:
                renderer.render(
                    expanded_md_file,
                    tpl_for_render,
                    out_p,
                    csl_path=builtin_csl,
                    link_citations=True,
                    metadata_file=meta_file,
                )
            except Exception as exc:  # 渲染器缺失/调用失败属于环境问题，不是稿件问题
                res.returncode = 2
                res.errors.append(f"渲染引擎不可用：{exc}")
                return res

            # 7. XML 深度后处理 (Postprocessor: 公式居中靠右编号 + 三线表)
            logger.info("📐 执行公式排版优化与主题深度清理...")
            postprocess_docx(out_p, manuscript_path=in_p, eq_number_style=options.eq_number_style)

        # 8. 产物数值防丢检查 (Audit: Post-flight)
        if options.postflight:
            all_kept, missing = verify_numeric_integrity(in_p, out_p)
            if not all_kept:
                res.returncode = 1
                res.errors.append(
                    f"产物完整性检查未通过：原稿中 {len(missing)} 处数值未在最终产物中找到（{', '.join(missing[:5])}）。"
                )
                return res
            logger.info("✓ 产物数值完整性检查通过。")

        # 9. 格式要求逐条对账 (Audit: Inspector)
        if options.audit and req_file:
            matched, problems = audit_docx_against_spec(out_p, req_file)
            if not matched:
                res.returncode = 1
                res.errors.append(f"导出后抽查未通过：产物与格式要求存在 {len(problems)} 处不符。")
                for cat, msg in problems:
                    res.errors.append(f"  [{cat}] {msg}")
                return res
            logger.info("✓ 产物与格式要求逐条对账通过。")

        # 10. 可选 PDF 渲染 (Visual QA)
        if options.make_pdf:
            pdf_path = out_p.with_suffix(".pdf")
            success, reason = render_pdf_via_word(out_p, pdf_path)
            if success:
                res.output_pdf = pdf_path
                logger.info(f"🖨️ PDF 抽查版本已生成: {pdf_path}")
            else:
                res.messages.append(f"MD2WORD_SKIP kind=pdf-render reason={reason}")
                res.returncode = 3

        logger.info(f"✅ Word 文档导出成功: {out_p}")
        return res

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if expanded_md_file and expanded_md_file.exists():
            try:
                expanded_md_file.unlink()
            except OSError:
                pass
