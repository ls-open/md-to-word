#!/usr/bin/env python3
"""
create_pure_modern_base.py — 从零构建 100% 纯净现代 Word 365 学术基础模板

特点：
1. 完全不依赖 Pandoc 2007 旧底模（不调用 pandoc --print-default-data-file）；
2. 基于现代 Office 365 / Word 2021+ 规范（ISO/IEC 29500）从零初始化；
3. 原生构建所有 Pandoc / Quarto 识别的标准学术样式槽位；
4. 默认具备现代 OMML 居中数学排版、标准三线表、A4 规范页边距与中西文字体支持；
5. 全局彻底清除 styles.xml 中的全部主题字体与主题颜色属性，杜绝任何主题覆盖 Bug。
"""

import os
import sys
import zipfile
from pathlib import Path
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm
from lxml import etree

_SKILL_DIR = Path(__file__).resolve().parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from skill_utils import strip_theme_attrs_from_xml  # noqa: E402

NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS_M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
NS_W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'

def W(tag): return f'{{{NS_W}}}{tag}'
def M(tag): return f'{{{NS_M}}}{tag}'

def create_pure_modern_base(output_path="pure_modern_base.docx"):
    print("🌟 正在从零构建 100% 纯净现代 Word 365 基础模板...")

    # 1. 直接新建纯净的现代 Word 文档（不借用任何旧文件）
    doc = Document()

    # 2. 页面设置：A4 (21cm x 29.7cm)，标准学术页边距 (上下左右 2.54cm)
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.54)
    section.right_margin = Cm(2.54)

    # 3. 规范化所有学术样式（定义 styleId 与显示名）
    styles_spec = [
        ('Normal', 'Normal', WD_STYLE_TYPE.PARAGRAPH, None),
        ('Body Text', 'BodyText', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('First Paragraph', 'FirstParagraph', WD_STYLE_TYPE.PARAGRAPH, 'Body Text'),
        ('Compact', 'Compact', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Title', 'Title', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Subtitle', 'Subtitle', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Author', 'Author', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Date', 'Date', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Abstract', 'Abstract', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Keywords', 'Keywords', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Heading 1', 'Heading1', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Heading 2', 'Heading2', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Heading 3', 'Heading3', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Heading 4', 'Heading4', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Heading 5', 'Heading5', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Heading 6', 'Heading6', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Table Caption', 'TableCaption', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Image Caption', 'ImageCaption', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Captioned Figure', 'CaptionedFigure', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Table Note', 'TableNote', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Bibliography', 'Bibliography', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Block Text', 'BlockText', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Source Code', 'SourceCode', WD_STYLE_TYPE.PARAGRAPH, 'Normal'),
        ('Hyperlink', 'Hyperlink', WD_STYLE_TYPE.CHARACTER, None),
        ('Table', 'Table', WD_STYLE_TYPE.TABLE, None),
    ]

    for name, sid, stype, base_name in styles_spec:
        try:
            s = doc.styles[name]
        except KeyError:
            s = doc.styles.add_style(name, stype)
            print(f"  + 新建原生现代样式: {name} (styleId={sid})")
        
        s.element.set(W('styleId'), sid)
        if base_name and base_name in doc.styles:
            try:
                s.base_style = doc.styles[base_name]
            except Exception:
                pass

    # 4. 预设现代学术默认值（标题居中、图居中、摘要两端对齐）
    doc.styles['Title'].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.styles['Captioned Figure'].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.styles['Abstract'].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.styles['Image Caption'].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.styles['Table Caption'].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 5. 保存基础文档
    doc.save(output_path)

    # 6. 在 ZIP 级别对 styles.xml, stylesWithEffects.xml 和 settings.xml 进行彻底清理与现代升级
    with zipfile.ZipFile(output_path, 'r') as zin:
        styles_xml = zin.read('word/styles.xml')

    cleaned_styles_xml = strip_theme_attrs_from_xml(styles_xml)
    styles_root = etree.fromstring(cleaned_styles_xml)

    # 6a. 归零 docDefaults 的默认段后间距（python-docx 底模默认 after=200/line=276，即段后10磅/1.15倍行距）
    ppr_def = styles_root.find(f'.//{W("pPrDefault")}/{W("pPr")}/{W("spacing")}')
    if ppr_def is not None:
        ppr_def.set(W('before'), '0')
        ppr_def.set(W('after'), '0')
        ppr_def.set(W('line'), '240')
        ppr_def.set(W('lineRule'), 'auto')

    # 6b. 彻底清除非表格样式中的 Word 2007 硬编码彩色、Title 蓝底线、字符加宽/字距微调及异常继承
    for style_el in styles_root.findall(W('style')):
        stype = style_el.get(W('type'))
        sid = style_el.get(W('styleId')) or ''
        if stype == 'table':
            continue

        if sid == 'TOCHeading':
            based = style_el.find(W('basedOn'))
            if based is not None:
                based.set(W('val'), 'Normal')

        ppr = style_el.find(W('pPr'))
        if ppr is not None:
            # 清除 Title / IntenseQuote 等自带的蓝色底边框，以及 Subtitle 异常的 numPr
            if sid in ('Title', 'IntenseQuote'):
                pbdr = ppr.find(W('pBdr'))
                if pbdr is not None:
                    ppr.remove(pbdr)
            if sid == 'Subtitle':
                numpr = ppr.find(W('numPr'))
                if numpr is not None:
                    ppr.remove(numpr)
            if sid == 'TOCHeading':
                ol = ppr.find(W('outlineLvl'))
                if ol is not None:
                    ppr.remove(ol)
            if sid == 'Title':
                cs = ppr.find(W('contextualSpacing'))
                if cs is not None:
                    ppr.remove(cs)

        rpr = style_el.find(W('rPr'))
        if rpr is not None:
            # 所有段落与字符样式的颜色统一归零为纯黑 000000（剔除 #365F91/#4F81BD/#17365D/#C0504D 等残留）
            color_el = rpr.find(W('color'))
            if color_el is not None and color_el.get(W('val')) not in ('000000', 'auto'):
                color_el.set(W('val'), '000000')
            # 清除 Title / Subtitle / BookTitle / IntenseReference 等自带的字符间距加宽与字距微调
            for tag in ('spacing', 'kern'):
                el = rpr.find(W(tag))
                if el is not None:
                    rpr.remove(el)
            # 清除 Caption 默认自带的加粗与斜体，防止污染题注派生样式
            if sid == 'Caption':
                for tag in ('b', 'bCs', 'i', 'iCs'):
                    el = rpr.find(W(tag))
                    if el is not None:
                        rpr.remove(el)

    # 全局清除所有 <w:color>（含表格样式条件格式中的 #365F91/#4F81BD 等）为纯黑 000000
    for color_el in styles_root.iter(W('color')):
        if color_el.get(W('val')) not in ('000000', 'auto'):
            color_el.set(W('val'), '000000')

    cleaned_styles_xml = etree.tostring(
        styles_root, xml_declaration=True, encoding='UTF-8', standalone='yes'
    )

    # 纯正 Word 16.0 现代模式 settings.xml
    settings_root = etree.Element(W('settings'), nsmap={
        'w': NS_W, 'm': NS_M, 'w14': NS_W14
    })
    etree.SubElement(settings_root, W('zoom')).set(W('val'), 'bestFit')
    etree.SubElement(settings_root, W('characterSpacingControl')).set(W('val'), 'doNotCompress')
    
    compat = etree.SubElement(settings_root, W('compat'))
    compat_items = [
        ('compatibilityMode', '16'),
        ('overrideTableStyleFontSizeAndJustification', '1'),
        ('enableOpenTypeFeatures', '1'),
        ('doNotFlipMirrorIndents', '1'),
        ('dntScrollLDNDraw', '1'),
    ]
    for k, v in compat_items:
        el = etree.SubElement(compat, W('compatSetting'))
        el.set(W('name'), k)
        el.set(W('uri'), 'http://schemas.microsoft.com/office/word')
        el.set(W('val'), v)

    math_pr = etree.SubElement(settings_root, M('mathPr'))
    math_font = etree.SubElement(math_pr, M('mathFont'))
    math_font.set(M('val'), 'Cambria Math')
    def_jc = etree.SubElement(math_pr, M('defJc'))
    def_jc.set(M('val'), 'center')
    etree.SubElement(math_pr, M('dispDef'))

    pure_settings_xml = etree.tostring(settings_root, xml_declaration=True, encoding='UTF-8', standalone='yes')

    # 写回 docx
    tmp_out = output_path + ".tmp"
    with zipfile.ZipFile(output_path, 'r') as zin, zipfile.ZipFile(tmp_out, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == 'word/settings.xml':
                zout.writestr(item, pure_settings_xml)
            elif item.filename in ('word/styles.xml', 'word/stylesWithEffects.xml'):
                zout.writestr(item, cleaned_styles_xml)
            else:
                zout.writestr(item, zin.read(item.filename))
    os.replace(tmp_out, output_path)

    print(f"🎉 纯净现代 Word 365 基础母版构建完成: {output_path} (0 残留主题属性，完全受控)")

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(script_dir), "resources", "pure_modern_base.docx")
    create_pure_modern_base(out)
