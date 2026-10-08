#!/usr/bin/env python3
"""
create_pure_modern_base.py — 构建现代 Word 365 (16.0) 学术基础模板

直接按 ISO/IEC 29500 与 Word 365 (AppVersion 16.0000) 规范生成 pure_modern_base.docx：
1. 原生包含 Word 365 核心根样式与 Pandoc / Quarto 全部学术排版样式槽位；
2. 默认 A4 页面 (21cm × 29.7cm)、2.54cm 页边距、Cambria Math 居中公式及中西文字体表；
3. 样式表零主题属性引用、纯黑字色 (000000)、零段前段后默认间距与单倍基准行距。
"""

import os
import sys
import zipfile
from lxml import etree

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
MODERN_NS = (
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
    'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" '
    'xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex" '
    'xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid" '
    'xmlns:w16="http://schemas.microsoft.com/office/word/2018/wordml" '
    'xmlns:w16sdtdh="http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash" '
    'xmlns:w16sdtfl="http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock" '
    'xmlns:w16se="http://schemas.microsoft.com/office/word/2015/wordml/symex" '
    'xmlns:w16du="http://schemas.microsoft.com/office/word/2023/wordml/word16du" '
    'mc:Ignorable="w14 w15 w16se w16cid w16 w16cex w16sdtdh w16sdtfl w16du"'
)


def W(tag: str) -> str:
    return f"{{{NS_W}}}{tag}"


def _xml(text: str) -> bytes:
    return etree.tostring(etree.fromstring(text.encode("utf-8")),
                          xml_declaration=True, encoding="UTF-8", standalone="yes")


STATIC_PARTS = {
    "[Content_Types].xml": """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
      <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
      <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
      <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
      <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
      <Override PartName="/word/webSettings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml"/>
      <Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>
      <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
      <Override PartName="/word/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
    </Types>""",
    "_rels/.rels": """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
      <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
      <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
    </Relationships>""",
    "word/_rels/document.xml.rels": """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
      <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
      <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/webSettings" Target="webSettings.xml"/>
      <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/>
      <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
      <Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
    </Relationships>""",
    "docProps/app.xml": """<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
      <Template>Normal.dotm</Template><TotalTime>0</TotalTime><Pages>1</Pages><Words>0</Words><Characters>0</Characters>
      <Application>Microsoft Office Word</Application><DocSecurity>0</DocSecurity><Lines>0</Lines><Paragraphs>0</Paragraphs>
      <ScaleCrop>false</ScaleCrop><Company/><LinksUpToDate>false</LinksUpToDate><CharactersWithSpaces>0</CharactersWithSpaces>
      <SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0000</AppVersion>
    </Properties>""",
    "docProps/core.xml": """<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <dc:title/><dc:subject/><dc:creator/><cp:keywords/><dc:description/><cp:lastModifiedBy/><cp:revision>1</cp:revision>
    </cp:coreProperties>""",
    "word/document.xml": f"""<w:document {MODERN_NS}><w:body><w:p/>
      <w:sectPr>
        <w:pgSz w:w="11906" w:h="16838"/>
        <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
        <w:cols w:space="720"/><w:docGrid w:linePitch="360"/>
      </w:sectPr>
    </w:body></w:document>""",
    "word/settings.xml": f"""<w:settings {MODERN_NS}>
      <w:zoom w:val="bestFit"/><w:bordersDoNotSurroundHeader/><w:bordersDoNotSurroundFooter/>
      <w:defaultTabStop w:val="420"/><w:drawingGridVerticalSpacing w:val="156"/>
      <w:displayHorizontalDrawingGridEvery w:val="0"/><w:displayVerticalDrawingGridEvery w:val="2"/>
      <w:characterSpacingControl w:val="doNotCompress"/>
      <w:compat>
        <w:spaceForUL/><w:balanceSingleByteDoubleByteWidth/><w:doNotLeaveBackslashAlone/><w:ulTrailSpace/>
        <w:doNotExpandShiftReturn/><w:adjustLineHeightInTable/><w:applyBreakingRules/><w:useFELayout/>
        <w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
        <w:compatSetting w:name="overrideTableStyleFontSizeAndJustification" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
        <w:compatSetting w:name="enableOpenTypeFeatures" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
        <w:compatSetting w:name="doNotFlipMirrorIndents" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
        <w:compatSetting w:name="differentiateMultirowTableHeaders" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
        <w:compatSetting w:name="useWord2013TrackBottomHyphenation" w:uri="http://schemas.microsoft.com/office/word" w:val="0"/>
      </w:compat>
      <m:mathPr>
        <m:mathFont m:val="Cambria Math"/><m:brkBin m:val="before"/><m:brkBinSub m:val="--"/>
        <m:smallFrac m:val="0"/><m:dispDef/><m:lMargin m:val="0"/><m:rMargin m:val="0"/>
        <m:defJc m:val="center"/><m:wrapIndent m:val="1440"/><m:intLim m:val="subSup"/><m:naryLim m:val="undOvr"/>
      </m:mathPr>
      <w:themeFontLang w:val="en-US" w:eastAsia="zh-CN" w:bidi="ar-SA"/>
      <w:clrSchemeMapping w:bg1="light1" w:t1="dark1" w:bg2="light2" w:t2="dark2" w:accent1="accent1" w:accent2="accent2" w:accent3="accent3" w:accent4="accent4" w:accent5="accent5" w:accent6="accent6" w:hyperlink="hyperlink" w:followedHyperlink="followedHyperlink"/>
      <w:decimalSymbol w:val="."/><w:listSeparator w:val=","/>
    </w:settings>""",
    "word/webSettings.xml": f"""<w:webSettings {MODERN_NS}><w:allowPNG/><w:doNotSaveAsSingleFile/></w:webSettings>""",
    "word/numbering.xml": f"""<w:numbering {MODERN_NS}/>""",
    "word/fontTable.xml": f"""<w:fonts {MODERN_NS}>
      <w:font w:name="Times New Roman"><w:charset w:val="00"/><w:family w:val="roman"/><w:pitch w:val="variable"/></w:font>
      <w:font w:name="Arial"><w:charset w:val="00"/><w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font>
      <w:font w:name="Cambria Math"><w:charset w:val="00"/><w:family w:val="roman"/><w:pitch w:val="variable"/></w:font>
      <w:font w:name="Calibri"><w:charset w:val="00"/><w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font>
      <w:font w:name="宋体"><w:altName w:val="SimSun"/><w:charset w:val="86"/><w:family w:val="auto"/><w:pitch w:val="variable"/></w:font>
      <w:font w:name="黑体"><w:altName w:val="SimHei"/><w:charset w:val="86"/><w:family w:val="auto"/><w:pitch w:val="variable"/></w:font>
      <w:font w:name="楷体"><w:altName w:val="KaiTi"/><w:charset w:val="86"/><w:family w:val="auto"/><w:pitch w:val="variable"/></w:font>
      <w:font w:name="仿宋"><w:altName w:val="FangSong"/><w:charset w:val="86"/><w:family w:val="auto"/><w:pitch w:val="variable"/></w:font>
      <w:font w:name="DengXian"><w:altName w:val="等线"/><w:charset w:val="86"/><w:family w:val="auto"/><w:pitch w:val="variable"/></w:font>
    </w:fonts>""",
    "word/theme/theme1.xml": """<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office Theme">
      <a:themeElements>
        <a:clrScheme name="Office">
          <a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
          <a:dk2><a:srgbClr val="44546A"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>
          <a:accent1><a:srgbClr val="4472C4"/></a:accent1><a:accent2><a:srgbClr val="ED7D31"/></a:accent2>
          <a:accent3><a:srgbClr val="A5A5A5"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4>
          <a:accent5><a:srgbClr val="5B9BD5"/></a:accent5><a:accent6><a:srgbClr val="70AD47"/></a:accent6>
          <a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
        </a:clrScheme>
        <a:fontScheme name="Office">
          <a:majorFont><a:latin typeface="Times New Roman"/><a:ea typeface=""/><a:cs typeface=""/><a:font script="Hans" typeface="黑体"/></a:majorFont>
          <a:minorFont><a:latin typeface="Times New Roman"/><a:ea typeface=""/><a:cs typeface=""/><a:font script="Hans" typeface="宋体"/></a:minorFont>
        </a:fontScheme>
        <a:fmtScheme name="Office">
          <a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>
          <a:lnStyleLst>
            <a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>
            <a:ln w="12700" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>
            <a:ln w="19050" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>
          </a:lnStyleLst>
          <a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
          <a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>
        </a:fmtScheme>
      </a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/>
      <a:extLst><a:ext uri="{05A4C25C-085E-4340-85A3-A5531E510DB2}">
        <thm15:themeFamily xmlns:thm15="http://schemas.microsoft.com/office/thememl/2012/main" name="Office Theme" id="{62F939B6-93AF-4DB8-9C6B-D6C7DFDC589F}" vid="{4A3C46E8-61CC-4603-A589-7422A47A8E4A}"/>
      </a:ext></a:extLst>
    </a:theme>""",
}


def _build_styles_xml() -> bytes:
    root = etree.fromstring(f"""<w:styles {MODERN_NS}>
      <w:docDefaults>
        <w:rPrDefault><w:rPr><w:rFonts/><w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="en-US" w:eastAsia="en-US" w:bidi="ar-SA"/></w:rPr></w:rPrDefault>
        <w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault>
      </w:docDefaults>
      <w:latentStyles w:defLockedState="0" w:defUIPriority="99" w:defSemiHidden="0" w:defUnhideWhenUsed="0" w:defQFormat="0" w:count="376"/>
      <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
      <w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont"><w:name w:val="Default Paragraph Font"/><w:uiPriority w:val="1"/><w:semiHidden/><w:unhideWhenUsed/></w:style>
      <w:style w:type="table" w:default="1" w:styleId="TableNormal">
        <w:name w:val="Normal Table"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/>
        <w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr>
      </w:style>
      <w:style w:type="numbering" w:default="1" w:styleId="NoList"><w:name w:val="No List"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/></w:style>
      <w:style w:type="table" w:customStyle="1" w:styleId="Table"><w:name w:val="Table"/><w:basedOn w:val="TableNormal"/></w:style>
    </w:styles>""".encode("utf-8"))

    def add_style(stype, sid, name, based="Normal", next_s=None, link=None, jc=None, ol=None, b=False, i=False, sz=None, va=None, u_none=False):
        st = etree.SubElement(root, W("style"), {W("type"): stype, W("styleId"): sid})
        etree.SubElement(st, W("name"), {W("val"): name})
        if based:
            etree.SubElement(st, W("basedOn"), {W("val"): based})
        if next_s:
            etree.SubElement(st, W("next"), {W("val"): next_s})
        if link:
            etree.SubElement(st, W("link"), {W("val"): link})
        etree.SubElement(st, W("qFormat"))
        if jc or ol is not None:
            ppr = etree.SubElement(st, W("pPr"))
            if ol is not None:
                etree.SubElement(ppr, W("keepNext"))
                etree.SubElement(ppr, W("keepLines"))
            if jc:
                etree.SubElement(ppr, W("jc"), {W("val"): jc})
            if ol is not None:
                etree.SubElement(ppr, W("outlineLvl"), {W("val"): str(ol)})
        if b or i or sz or va or u_none:
            rpr = etree.SubElement(st, W("rPr"))
            if b:
                etree.SubElement(rpr, W("b"))
                etree.SubElement(rpr, W("bCs"))
            if i:
                etree.SubElement(rpr, W("i"))
                etree.SubElement(rpr, W("iCs"))
            if b or i or sz or u_none:
                etree.SubElement(rpr, W("color"), {W("val"): "000000"})
            if sz:
                etree.SubElement(rpr, W("sz"), {W("val"): str(sz)})
                etree.SubElement(rpr, W("szCs"), {W("val"): str(sz)})
            if u_none:
                etree.SubElement(rpr, W("u"), {W("val"): "none"})
            if va:
                etree.SubElement(rpr, W("vertAlign"), {W("val"): va})

    for sid, name in (("Header", "header"), ("Footer", "footer"), ("BodyText", "Body Text"), ("Quote", "Quote"), ("IntenseQuote", "Intense Quote")):
        cid = f"{sid}Char"
        add_style("paragraph", sid, name, link=cid)
        add_style("character", cid, f"{sid if sid != 'BodyText' else 'Body Text'} Char", based="DefaultParagraphFont", link=sid)

    for lvl, is_b, is_i, sz in ((1, True, False, 28), (2, True, False, 26), (3, True, False, None), (4, True, True, None),
                                (5, False, False, None), (6, False, True, None), (7, False, True, None), (8, False, False, 20), (9, False, True, 20)):
        sid, cid = f"Heading{lvl}", f"Heading{lvl}Char"
        add_style("paragraph", sid, f"heading {lvl}", next_s="Normal", link=cid, ol=lvl - 1, b=is_b, i=is_i, sz=sz)
        add_style("character", cid, f"Heading {lvl} Char", based="DefaultParagraphFont", link=sid, b=is_b, i=is_i, sz=sz)

    add_style("paragraph", "Title", "Title", next_s="Normal", link="TitleChar", jc="center", sz=52)
    add_style("character", "TitleChar", "Title Char", based="DefaultParagraphFont", link="Title", sz=52)
    add_style("paragraph", "Subtitle", "Subtitle", next_s="Normal", link="SubtitleChar", i=True, sz=24)
    add_style("character", "SubtitleChar", "Subtitle Char", based="DefaultParagraphFont", link="Subtitle", i=True, sz=24)

    for sid, name, based, jc in (
        ("Author", "Author", "Normal", None), ("Date", "Date", "Normal", None),
        ("Abstract", "Abstract", "Normal", "both"), ("Keywords", "Keywords", "Normal", None),
        ("FirstParagraph", "First Paragraph", "BodyText", None), ("Compact", "Compact", "Normal", None),
        ("ListParagraph", "List Paragraph", "Normal", None), ("BlockText", "Block Text", "Normal", None),
        ("SourceCode", "Source Code", "Normal", None), ("TOCHeading", "TOC Heading", "Normal", None),
        ("Caption", "caption", "Normal", None), ("TableCaption", "Table Caption", "Normal", "center"),
        ("ImageCaption", "Image Caption", "Normal", "center"), ("Figure", "Figure", "Normal", "center"),
        ("CaptionedFigure", "Captioned Figure", "Normal", "center"), ("TableNote", "Table Note", "Normal", None),
        ("Bibliography", "Bibliography", "Normal", None), ("FootnoteText", "Footnote Text", "Normal", None),
        ("FootnoteBlockText", "Footnote Block Text", "FootnoteText", None),
        ("DefinitionTerm", "Definition Term", "Normal", None), ("Definition", "Definition", "Normal", None),
    ):
        add_style("paragraph", sid, name, based=based, jc=jc)

    add_style("character", "VerbatimChar", "Verbatim Char", based="DefaultParagraphFont")
    add_style("character", "SectionNumber", "Section Number", based="DefaultParagraphFont")
    add_style("character", "FootnoteReference", "Footnote Reference", based="DefaultParagraphFont", va="superscript")
    add_style("character", "Strong", "Strong", based="DefaultParagraphFont", b=True)
    add_style("character", "Emphasis", "Emphasis", based="DefaultParagraphFont", i=True)
    add_style("character", "Hyperlink", "Hyperlink", based="DefaultParagraphFont", u_none=True)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def create_pure_modern_base(output_path: str = "pure_modern_base.docx") -> None:
    print("🌟 正在构建现代 Word 365 (16.0) 基础模板...")
    tmp_out = output_path + ".tmp"
    with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for arcname, xml_text in STATIC_PARTS.items():
            zout.writestr(arcname, _xml(xml_text))
        zout.writestr("word/styles.xml", _build_styles_xml())
    os.replace(tmp_out, output_path)
    print(f"🎉 现代 Word 365 基础母版构建完成: {output_path}")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(script_dir), "resources", "pure_modern_base.docx")
    create_pure_modern_base(out)
