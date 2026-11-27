#!/usr/bin/env python3
"""
生成学术 Word 模板 (docx)

从纯净现代 Word 365 基础母版出发，根据 format.txt 格式要求修改样式，
输出是只含样式与页面设置的 template.docx，写出器直接用它。

模板生成按环节拆在 core / checks / decor / tables / footnotes 里；本文件只保留编排与
对外入口。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import RGBColor

from md_to_word.config import get_base_template_path
from md_to_word.i18n import t
from md_to_word.spec.constants import W, page_size_cm
from md_to_word.spec.parser import parse_format

from md_to_word.template.checks import _check_required_fields
from md_to_word.template.core import (
    TemplateError, _SECTPR_ORDER, _props_from_req,
    apply_mirror_margins, apply_proofing_language, apply_punctuation_compression,
    content_width, doc_grid_pitch, ensure_ordered_child, logger, modify_style,
)
from md_to_word.template.decor import apply_page_decorations, write_header_styles_meta
from md_to_word.template.footnotes import apply_footnote_format
from md_to_word.template.tables import apply_table_format
from md_to_word.utils.skill_utils import (
    clear_color_theme_attrs, clear_font_theme_attrs, get_logger, strip_theme_attrs_from_xml,
)

def get_default_template(lang: str = "zh"):
    """取纯净现代 Word 365 基底模板（resources/pure_modern_base.docx）。"""
    local_base = get_base_template_path()
    if not local_base.exists():
        raise TemplateError(t('template.base_template_missing', lang, path=local_base))
    logger.debug(f"使用内置纯净现代 Word 365 基底模板: {local_base}")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    shutil.copyfile(str(local_base), tmp.name)
    tmp.close()
    return tmp.name


def cleanup_temp(path: str):
    try:
        os.unlink(path)
    except OSError:
        pass


# ── 所有文档无条件必填的基础样式骨架 ──
# 无论导出普通文档/报告还是学术论文，标题、一级章节与正文三态（Body Text / First Paragraph / Normal）
# 都是必现基础段落；其余结构（二级及以上标题、摘要、关键词、图表、参考文献、目录、引用块）
# 均通过下方 STRUCT_TRIGGERS 按「稿件实际用到即必填」精确拦截。

def generate_template(format_text, output_path, margins=None, lang="zh"):
    """主流程：生成模板"""
    output_path = str(output_path)
    logger.debug('生成学术 Word 模板')

    try:
        spec = parse_format(format_text, lang=lang)
    except ValueError as exc:
        # 预检被 --no-check 跳过时，这里就是唯一一道格式解析。原样抛 ValueError
        # 会冒到 CLI，被误报成“本工具的缺陷”；转成 TemplateError 才能归因到格式文件。
        raise TemplateError(str(exc)) from exc
    page_size = spec.page_size
    reqs, default_latin = spec.styles, spec.default_latin
    if not reqs:
        raise TemplateError(t('template.no_styles_parsed', lang))

    if spec.margins:
        margins = spec.margins
    if not margins:
        margins = {'top': 2.54, 'bottom': 2.54, 'left': 2.54, 'right': 2.54}

    logger.debug(f'解析到 {len(reqs)} 个样式定义:')
    for r in reqs:
        desc = f'{r["style_name"]}'
        if 'font_name' in r:
            desc += f' {", ".join(r["font_name"])}'
        if 'font_size' in r:
            desc += f' {r["font_size"].pt}pt'
        logger.debug(f' - {desc}')
    if default_latin:
        logger.debug(f' 全局西文字体: {default_latin}')

    # 必填项的明细一直只进日志：CLI 的人看得到，`--json` 与 MCP 的调用方只拿到
    # 一句「详见上方逐条提示」。检查函数顺手把同一条消息写进 `details`，两个出口
    # 都能读——不再临时抬高 logger 级别、挂 handler；那是进程级状态，并发导出会串。
    details: list[str] = []
    has_errors, linkage_errors = _check_required_fields(
        spec, lang, format_text, sink=details)

    if has_errors:
        msg = t('template.required_missing', lang)
        if linkage_errors:
            # 联动错误**只**随异常一起给出（不再单独打日志）：打一遍再贴一遍，
            # 用户会以为有两处问题；而只打日志的话，`--json` / MCP 这条路读不到。
            msg = msg + "\n" + "\n".join(linkage_errors)
        details = [line for line in details if line.strip()]
        if details:
            msg = msg + "\n" + "\n".join(details[:24])
        raise TemplateError(msg)

    logger.debug('加载纯净现代 Word 365 底模...')
    tmp_path = get_default_template(lang)
    doc = Document(tmp_path)
    cleanup_temp(tmp_path)

    if spec.proofing_lang:
        apply_proofing_language(doc, spec.proofing_lang)
        logger.debug(f' ✓ 校对语言: {spec.proofing_lang}')
    if spec.punctuation_compression is not None or spec.proofing_lang is not None:
        csc_val = apply_punctuation_compression(doc, spec.punctuation_compression, spec.proofing_lang)
        logger.debug(f' ✓ 标点压缩: {csc_val}')
    apply_mirror_margins(doc, spec.mirror_margins)
    if spec.mirror_margins:
        logger.debug(' ✓ 对称页边距: 开')

    for req in reqs:
        style_name = req.get('style_name')
        if not style_name:
            continue
        modify_style(
            doc,
            style_name,
            _props_from_req(req, page_size, margins, gutter_cm=spec.gutter_cm),
            default_latin=default_latin,
        )

    apply_table_format(doc, spec, default_latin=default_latin, lang=lang)
    apply_page_decorations(doc, spec, lang=lang)
    apply_footnote_format(doc, spec, page_size, margins,
                          default_latin=default_latin, gutter_cm=spec.gutter_cm)

    try:
        hyperlink_style = doc.styles['Hyperlink']
        hyperlink_style.font.color.rgb = RGBColor(0, 0, 0)
        hyperlink_style.font.underline = False
        rpr = hyperlink_style.element.find(W('rPr'))
        if rpr is not None:
            color_el = rpr.find(W('color'))
            if color_el is not None:
                clear_color_theme_attrs(color_el)
        logger.debug(' ✓ Hyperlink: 已设为黑色（取消下划线）')
    except KeyError:
        pass

    # 清除 Caption 基样式的斜体：底模的 Caption 基样式带 italic，
    # Image Caption 和 Table Caption 继承它，导致 bold+italic 叠加
    try:
        caption_style = doc.styles['Caption']
        caption_style.font.italic = False
        logger.debug(' ✓ Caption: 已清除斜体（影响 Image Caption / Table Caption）')
    except KeyError:
        pass

    # 清除 Abstract 样式的 keepNext/keepLines：
    # 结构化摘要分段后，各段 keepNext 串成"必须同页"的传递链（AbstractTitle → 各段 → Keywords），
    # 链高超过首页剩余空间时 Word 把整链下移，首页只剩标题。清除后摘要按普通段落流排版。
    try:
        abstract_style = doc.styles['Abstract']
        ppr = abstract_style.element.find(W('pPr'))
        if ppr is not None:
            removed = []
            for tag in ('keepNext', 'keepLines'):
                el = ppr.find(W(tag))
                if el is not None:
                    ppr.remove(el)
                    removed.append(tag)
            if removed:
                logger.debug(f' ✓ Abstract: 已清除 {" / ".join(removed)}（结构化摘要分段不再触发首页分页）')
    except KeyError:
        pass

    for style_el in doc.styles._element:
        style_id = style_el.get(W('styleId'))
        if not style_id:
            continue

        is_char_style = 'Char' in style_id and any(
            style_id.startswith(p) for p in ('Title', 'Subtitle', 'Heading')
        )
        is_unused_heading = style_id in ('Subtitle', 'TOCHeading') or (
            style_id and style_id.startswith('Heading') and style_id[-1] in '456789'
        )

        if is_char_style or is_unused_heading:
            rpr = style_el.find(W('rPr'))
            if rpr is not None:
                rfonts = rpr.find(W('rFonts'))
                color_el = rpr.find(W('color'))
                had_font = rfonts is not None and clear_font_theme_attrs(rfonts)
                had_color = color_el is not None and clear_color_theme_attrs(color_el)
                if color_el is not None and color_el.get(W('val')) not in ('000000', 'auto'):
                    color_el.set(W('val'), '000000')
                    had_color = True
                if had_font and is_char_style:
                    logger.debug(f' ✓ {style_id}: 已清除主题字体')
                if had_color and is_char_style:
                    logger.debug(f' ✓ {style_id}: 已清除主题色')

    from docx.shared import Cm
    w_cm, h_cm = page_size_cm(page_size)
    pg_w, pg_h = Cm(w_cm), Cm(h_cm)

    # 原生装订线（pgMar/@w:gutter）：左边距保持 declared margins['left']，
    # 装订线单独写入 pgMar/@w:gutter；若开启对称页边距，Word 会自动将装订线放在内侧（奇数页左、偶数页右）。
    # 写出器（_content_width_twips / _clamp）与校验器均把 w:gutter 从版心宽度中减去。
    for section in doc.sections:
        section.page_width = pg_w
        section.page_height = pg_h
        section.top_margin = Cm(margins['top'])
        section.bottom_margin = Cm(margins['bottom'])
        section.left_margin = Cm(margins['left'])
        section.right_margin = Cm(margins['right'])
        section.gutter = Cm(spec.gutter_cm or 0)
        if spec.header_distance is not None:
            section.header_distance = Cm(spec.header_distance)
        if spec.footer_distance is not None:
            section.footer_distance = Cm(spec.footer_distance)
        # 文档网格：每页 N 行 → 每行占多少 twips，由版心高度除以行数算
        if spec.doc_grid_lines:
            grid = ensure_ordered_child(section._sectPr, 'docGrid', _SECTPR_ORDER)
            grid.set(W('type'), 'lines')
            grid.set(W('linePitch'), str(doc_grid_pitch(spec, margins)))
        w_cm = round(pg_w.inches * 2.54, 1)
        h_cm = round(pg_h.inches * 2.54, 1)
        content_w = round(content_width(w_cm, margins['left'], margins['right'], spec.gutter_cm), 1)
        decor_cm = ''
        if spec.header_distance is not None or spec.footer_distance is not None:
            decor_cm = (f'，页眉距边界 {spec.header_distance}cm 页脚距边界 {spec.footer_distance}cm')
        extra = ''
        if spec.gutter_cm:
            extra += f'，装订线 {spec.gutter_cm}cm'
        if spec.mirror_margins:
            extra += '，对称页边距 开'
        if spec.doc_grid_lines:
            extra += f'，文档网格 每页 {spec.doc_grid_lines} 行'
        logger.debug(
            f' ✓ 页面: {page_size} ({w_cm}×{h_cm}cm)，边距 上{margins["top"]}cm '
            f'下{margins["bottom"]}cm 左{margins["left"]}cm 右{margins["right"]}cm，'
            f'内容宽 {content_w}cm{decor_cm}{extra}'
        )

    try:
        doc.styles['Block Text']
    except KeyError:
        doc.styles.add_style('Block Text', WD_STYLE_TYPE.PARAGRAPH)
        logger.debug(' ✓ Block Text: 已创建')

    try:
        code_style = doc.styles['Source Code']
    except KeyError:
        code_style = doc.styles.add_style('Source Code', WD_STYLE_TYPE.PARAGRAPH)
        logger.debug(' ✓ Source Code: 已创建')
    # 代码块一律左对齐：它继承正文的「两端对齐」，长行会被拉伸到版心右边界——
    # 代码的换行位置本身就是作者写的，再拉伸只会让人以为是排版错了。
    code_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    write_header_styles_meta(
        doc, {r['style_name'] for r in reqs if r.get('join_header')}, kind="template")
    doc.save(output_path)

    # 保存后重新打包：只做一件事——清除 styles.xml 里的全部主题字体/颜色属性。
    # settings.xml 不在这里动：compatMode 与 mathPr 由底模写好，再注入一遍就是
    # 同一个事实写两处。
    try:
        import zipfile
        with zipfile.ZipFile(output_path, 'r') as zin:
            styles_xml = zin.read('word/styles.xml')
            has_styles_with_effects = 'word/stylesWithEffects.xml' in zin.namelist()
            other_items = {item.filename: zin.read(item.filename) for item in zin.infolist()
                           if item.filename not in ('word/styles.xml', 'word/stylesWithEffects.xml')}

        cleaned_styles_xml = strip_theme_attrs_from_xml(styles_xml)

        tmp_out = output_path + ".tmp"
        with zipfile.ZipFile(tmp_out, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
            zout.writestr('word/styles.xml', cleaned_styles_xml)
            if has_styles_with_effects:
                zout.writestr('word/stylesWithEffects.xml', cleaned_styles_xml)
            for fname, fcontent in other_items.items():
                zout.writestr(fname, fcontent)
        os.replace(tmp_out, output_path)
    except Exception as e:
        # 不吞：跳过这一步，主题字体/颜色就可能盖掉显式设置，而外表看不出异常。
        # 宁可当场失败，也不要交出一个看着正常的坏模板。
        raise RuntimeError(t('template.theme_cleanup_failed', lang, err=e)) from e

    get_logger().info(t("template.built", lang, count=len(reqs)))


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    format_file = None
    output_path = 'template.docx'

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ('-o', '--output'):
            i += 1
            if i < len(args):
                output_path = args[i]
        elif not arg.startswith('-') and format_file is None:
            format_file = arg
        else:
            logger.error(f'错误: 不认识的参数 "{arg}"')
            logger.error('用法: python3 scripts/generate_template.py format.txt -o template.docx')
            sys.exit(1)
        i += 1

    if format_file is None:
        logger.error('错误: 未提供格式要求文件')
        logger.error('用法: python3 scripts/generate_template.py format.txt -o template.docx')
        sys.exit(1)

    if not os.path.exists(format_file):
        logger.error(f'错误: 文件不存在 "{format_file}"')
        sys.exit(1)

    with open(format_file, 'r', encoding='utf-8') as f:
        format_text = f.read()

    try:
        generate_template(format_text, output_path)
    except TemplateError as exc:
        logger.error(f'错误: {exc}')
        sys.exit(1)
    logger.info(t("template.styles_only", "zh"))


if __name__ == '__main__':
    main()
