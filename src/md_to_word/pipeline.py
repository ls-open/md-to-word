"""md_to_word.pipeline — 导出总编排。

顺序固定：读稿 → 预检 → 生成样式模板 → 读成文档模型 → 写出 OOXML → 防丢数 → 对账 → 可选 PDF。
每一步失败都有明确的退出码与可读原因；跨平台，不依赖任何外部二进制。
"""

from __future__ import annotations

import logging
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
from md_to_word.spec.parser import parse_requirements
from md_to_word.template.builder import build_template
from md_to_word.status import EXIT_ERROR, EXIT_OK, EXIT_PDF_SKIPPED
from md_to_word.template.generator import TemplateError
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
    check_md: bool = True
    postflight: bool = True
    audit: bool = True
    make_pdf: bool = False
    lang: Optional[str] = None  # 消息语言：None=按稿件语种 | "zh" | "en"


@dataclass
class ExportResult:
    """流水线执行结果。"""

    returncode: int  # EXIT_OK / EXIT_ERROR / EXIT_PDF_SKIPPED（见 status.py）
    output_docx: Optional[Path] = None
    output_pdf: Optional[Path] = None
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # messages 里的提醒条目，供 CLI 加标记
    lang: str = "zh"

    @property
    def ok(self) -> bool:
        """docx 是否已经写出来了（`--pdf` 跳过不算失败）。"""
        return self.returncode in (EXIT_OK, EXIT_PDF_SKIPPED)


def _normalized_csl(path: Path, temp_dir: Path, res: ExportResult) -> Path:
    """把 CSL 里的 direct formatting 去掉，返回可用的路径（就地清理要写副本）。"""
    from md_to_word.transform.csl_clean import is_csl, strip_direct_formatting

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
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


def _prepare_custom_template(src: Path, dst: Path, lang: str = "zh") -> Path:
    """第三方模板入场前的清理：剥主题属性，并确认它只有一节。

    主题字体与主题色的优先级高于显式字体，外来的 `.docx`（期刊/学校下发）几乎都带着
    它们，不剥就会出现「要求文件写了字体，产物却没变」。多节模板则更直接：本工具只在
    正文那一节上写页眉页脚，多出来的节会全部走样，这里当场拒绝而不是产出一份错位的文档。
    """
    import zipfile

    from docx import Document

    from md_to_word.utils.skill_utils import strip_theme_attrs_from_xml

    # 不是 zip、zip 里缺 word/、磁盘上读不了：都在这里收成一句人话。
    # 一路漏到调用方就是 BadZipFile 的 traceback（`-t 一份 PDF` 会这么炸）。
    try:
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename in ("word/styles.xml", "word/stylesWithEffects.xml"):
                    data = strip_theme_attrs_from_xml(data)
                zout.writestr(item, data)
        sections = len(Document(str(dst)).sections)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise TemplateError(t("pipeline.template_unreadable", lang, path=src, err=exc)) from exc

    if sections != 1:
        raise TemplateError(t("pipeline.template_multiple_sections", lang, count=sections))
    return dst


def run_export_pipeline(options: ExportOptions) -> ExportResult:
    """执行完整的纯 Python 学术导出流水线。"""
    res = ExportResult(returncode=0)
    in_p = Path(options.input_path).resolve()
    if not in_p.is_file():
        res.returncode = EXIT_ERROR
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
    # 目录不存在时当场说清楚：否则要等整条流水线跑完、写文件那一刻才抛 FileNotFoundError，
    # 对着 traceback 的人不会想到是自己漏建了一个目录。
    if not out_p.parent.is_dir():
        res.returncode = EXIT_ERROR
        res.errors.append(t("pipeline.output_dir_missing", res.lang, dir=out_p.parent))
        return res
    # `-o 某个目录` 是常见笔误（把目录当成文件名传进来），python-docx 会抛 IsADirectoryError，
    # 到时候看到的是 zipfile 的 traceback——这里先拦住。
    if out_p.is_dir():
        res.returncode = EXIT_ERROR
        res.errors.append(t("pipeline.output_is_dir", res.lang, path=out_p))
        return res

    # 2. 确定格式要求 (Requirements Spec)
    req_file: Optional[Path] = None
    req_content: Optional[str] = None

    if options.requirements_path:
        p_req = Path(options.requirements_path).resolve()
        if not p_req.is_file():
            res.returncode = EXIT_ERROR
            res.errors.append(t("pipeline.requirements_missing", res.lang, path=p_req))
            return res
        req_file = p_req
        req_content = p_req.read_text(encoding="utf-8")
    elif options.preset:
        p_pre = resolve_preset_path(options.preset)
        if not p_pre or not p_pre.is_file():
            res.returncode = EXIT_ERROR
            res.errors.append(t("pipeline.preset_missing", res.lang, name=options.preset))
            return res
        req_file = p_pre
        req_content = p_pre.read_text(encoding="utf-8")
    else:
        # 不带 `-r` 时只认一个固定名：稿件同目录的 `format.txt`。不去猜「旁边那个 .txt
        # 也许是要求文件」——猜错是静默用错格式，猜对了也换不来多少方便。旁边确实另有
        # .txt 却没用上时提醒一句，免得用户以为它生效了。
        named = in_p.parent / "format.txt"
        if named.is_file():
            req_file = named
            req_content = named.read_text(encoding="utf-8")
            res.messages.append(t("pipeline.txt_named", res.lang, path=named.name))
        else:
            others = sorted(p.name for p in in_p.parent.glob("*.txt") if p.is_file())
            if others:
                shown = "、".join(others[:3]) + ("…" if len(others) > 3 else "")
                res.messages.append(t("pipeline.txt_ignored", res.lang, names=shown))
            # 默认预设跟着稿件语种走：英文稿拿中文学位论文的格式（首行缩进两字符、
            # 宋体 fallback）是错的。判据与默认 CSL 用的是同一个 `looks_chinese`。
            preset_name = "zh-academic" if res.lang == "zh" else "en-nature"
            p_default = resolve_preset_path(preset_name)
            if p_default and p_default.is_file():
                req_file = p_default
                req_content = p_default.read_text(encoding="utf-8")
                res.messages.append(t("pipeline.preset_auto", res.lang, name=preset_name))

    # 3. 模板解析
    custom_template: Optional[Path] = None
    if options.template_path:
        p_tpl = Path(options.template_path).resolve()
        if not p_tpl.is_file():
            res.returncode = EXIT_ERROR
            res.errors.append(t("pipeline.template_missing", res.lang, path=p_tpl))
            return res
        custom_template = p_tpl

    # 要求文件写错时预检会给出带行号的原因；这里只取公式编号这一项，读不出就用默认
    try:
        spec = parse_requirements(req_content) if req_content else None
    except ValueError:
        spec = None

    # 4. 导前预检门禁 (Validator)
    if options.check_md:
        logger.info("🔍 " + t("pipeline.precheck", res.lang))
        v_report = validate_manuscript(
            in_p, template_docx=custom_template, spec_path=req_file, lang=res.lang
        )
        if not v_report.valid:
            res.returncode = EXIT_ERROR
            res.errors.append(t("pipeline.rejected", res.lang, count=len(v_report.errors)))
            res.errors.extend(v_report.errors)
            return res
        # 提醒进 `result.messages`：`--json` 的消费方（技能、脚本）只有拿到结构化结果才能
        # 转述，靠正则去刮 stderr 是另一种脆弱。人看的那一份由 CLI 统一加 ⚠️ 打印。
        for w in v_report.warnings:
            res.messages.append(w)
            res.warnings.append(w)

    # 5. 准备工作环境与 CSL 解析
    temp_dir = tempfile.mkdtemp(prefix="md2word_")
    try:
        # HTML 注释是写给人看的编辑批注，任何 Markdown 渲染器都不显示；原样印进 Word
        # 属于把批注当正文。这里无条件剔除，不给开关——代码块里的内容不受影响。
        contract_text = strip_html_comments(in_p.read_text(encoding="utf-8"))

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
        if tpl_for_render:
            try:
                tpl_for_render = _prepare_custom_template(
                    tpl_for_render, Path(temp_dir) / "template.docx", res.lang
                )
            except TemplateError as exc:
                res.returncode = EXIT_ERROR
                res.errors.append(str(exc))
                return res
        if not tpl_for_render:
            if not req_content:
                res.returncode = EXIT_ERROR
                res.errors.append(t("pipeline.no_spec", res.lang))
                return res
            temp_tpl_path = Path(temp_dir) / "template.docx"
            try:
                build_template(req_content, temp_tpl_path, lang=res.lang)
            except TemplateError as exc:
                res.returncode = EXIT_ERROR
                res.errors.append(
                    t("pipeline.requirements_template_failed", res.lang, reason=exc)
                )
                return res
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
            # 用户自带的 CSL：现场剥掉会覆盖模板的 direct formatting（内置样式发布前已规范化）。
            # 不这么做的话，同一份要求文件换个 CSL，悬挂缩进与行距就跟着变。
            csl_path = _normalized_csl(csl_path, Path(temp_dir), res)
            try:
                engine = CitationEngine(bib_text, csl_path, res.lang)
            except (CitationError, OSError) as exc:
                res.returncode = EXIT_ERROR
                res.errors.append(t("pipeline.csl_error", res.lang, reason=exc))
                return res

        try:
            model = read_markdown(contract_text, citation_keys=citation_keys)
            if engine is not None:
                # 年份后缀要在第一次渲染之前定下来（同作者同年的多条文献编 a/b/c），
                # 而引擎是在模型读出来之前建的，所以这里把真正引用到的 key 交回去
                from md_to_word.transform.citations import cited_keys

                engine.reserve(cited_keys(model))
            write_docx(
                model,
                tpl_for_render,
                out_p,
                citations=engine,
                base_dir=in_p.parent,
                equation_number_format=spec.equation_number_format if spec else "",
                equation_number_placement=spec.equation_number if spec else "right",
                no_row_split=bool(spec and spec.table.get("no_row_split")),
                lang=res.lang,
            )
        except UnsupportedFeature as exc:
            res.returncode = EXIT_ERROR
            res.errors.append(t("pipeline.unsupported", res.lang, reason=exc))
            return res
        except OSError as exc:
            # 目录只读、磁盘满、文件被 Word 占着：都是"写不进去"，不该甩 traceback。
            res.returncode = EXIT_ERROR
            res.errors.append(t("pipeline.write_failed", res.lang, path=out_p, err=exc))
            return res

        # 8. 产物数值防丢检查 (Audit: Post-flight)
        if options.postflight:
            all_kept, missing = verify_numeric_integrity(in_p, out_p)
            if not all_kept:
                res.returncode = EXIT_ERROR
                res.errors.append(
                    t("pipeline.numeric_failed", res.lang,
                      count=len(missing), sample=", ".join(missing[:5]))
                )
                return res
            logger.info("✓ " + t("pipeline.numeric_ok", res.lang))

        # 9. 格式要求逐条对账 (Audit: Inspector)
        if options.audit and req_file:
            matched, problems = audit_docx_against_spec(out_p, req_file, res.lang)
            if not matched:
                res.returncode = EXIT_ERROR
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
