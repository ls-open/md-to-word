#!/usr/bin/env python3
"""
fix_docx_equations.py — Word 学术公式排版与全局主题净化引擎

功能：
1. 自动识别由 Quarto / Pandoc 生成的带编号公式段落；
2. 将其重构为标准的 1 行 3 列无边框自适应表格：
   - 左列（12% 宽度）：空白占位；
   - 中列（76% 宽度）：公式本体绝对居中；
   - 右列（12% 宽度）：编号文本（如 (1)、(2)）100% 靠右贴紧右侧页边距；
   相邻的公式段会并成一张多行表（OOXML 里相邻的 w:tbl 本就是一表多行，见
   merge_adjacent_equation_tables）；
3. 对 docx 进行深度的 styles.xml 主题属性净化，彻底清除所有残余主题冲突。
"""

import os
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from lxml import etree

_SKILL_DIR = Path(__file__).resolve().parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from skill_utils import strip_theme_attrs_from_xml  # noqa: E402

NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS_M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'

# 公式段里允许的**非内容**子元素：Quarto crossref 的书签锚点（公式段实测形状
# pPr + bookmarkStart + oMathPara + bookmarkEnd）与拼写检查标记。它们随公式一起
# 搬进中列保留（书签是交叉引用锚点，删了就少一个可定位点）；除此之外的任何子元素
# 都算"公式外内容"，出现即不转换该段（见 fix_equations_in_xml）。
_META_PARA_CHILDREN = frozenset({'pPr', 'bookmarkStart', 'bookmarkEnd', 'proofErr'})

def W(tag): return f'{{{NS_W}}}{tag}'
def M(tag): return f'{{{NS_M}}}{tag}'


def extract_quarto_eq_number(om_para) -> str | None:
    """从公式里摘出 Quarto 生成的编号（"(1)"、"(5.1)"），并从公式中移除它。

    编号是 oMath 尾部的 m:r 运行（em-space + "(" + 数字 + ")"）。

    返回 None 表示这条公式没有编号——保持原样居中即可，不套用三列表格。
    """
    if om_para is None:
        return None
    om = om_para.find(M('oMath'))
    if om is None:
        return None
    runs = [r for r in om if r.tag == M('r')]
    if not runs:
        return None
    acc = ''
    for i in range(len(runs) - 1, -1, -1):
        r = runs[i]
        txt = ''.join(t.text or '' for t in r.findall(M('t')))
        acc = txt + acc
        # 匹配 "em-space + 括号 + 数字"（兼容 1.1 / 1a 等，避免吞掉公式尾部的括号项）
        if re.match(r'^[\s   ]*\(\s*\d+(?:\.\d+)?[a-zA-Z]?\s*\)$', acc):
            for r2 in runs[i:]:
                om.remove(r2)
            return acc.strip()
    return None


# crossref 只能选 arabic/roman/alpha，改不了括号与分隔符，故中文写法只能在渲染后改。
# 只认 crossref 生成的形状，认不出的原样放过。
_EQ_NATIVE_NUMBER = re.compile(r'^\(\s*(\d+(?:\.\d+)?[a-zA-Z]?)\s*\)$')


def format_eq_number(num: str, style: str) -> str:
    """改写编号外观：'asis' 原样返回；'cjk' 把 (5.1) 改成 （5-1）、(1) 改成 （1）。"""
    if style != 'cjk' or not num:
        return num
    m = _EQ_NATIVE_NUMBER.match(num)
    return f'（{m.group(1).replace(".", "-")}）' if m else num


def _text_width_pt(root) -> float:
    """正文可用宽度（pt）：pgSz - pgMar。取不到时按 A4 + 2.4cm 边距估。

    优先取 body 末尾的 sectPr（正文节），与 audit_export / expand_markers 同口径；
    单测最小片段或前置节才回退到任意含 pgSz + pgMar 的 sectPr。
    """
    body = root.find(W('body'))
    sect = body.find(W('sectPr')) if body is not None else None
    if sect is None or sect.find(W('pgSz')) is None or sect.find(W('pgMar')) is None:
        sect = next((s for s in root.findall('.//' + W('sectPr'))
                     if s.find(W('pgSz')) is not None and s.find(W('pgMar')) is not None), None)
    if sect is None:
        return 459.0
    pgsz, mar = sect.find(W('pgSz')), sect.find(W('pgMar'))
    def tw(el, name, default):
        v = el.get(W(name))
        return float(v) if v is not None else default
    w = tw(pgsz, 'w', 11906) - tw(mar, 'left', 1361) - tw(mar, 'right', 1361)
    return w / 20.0


def _eq_number_pct(num_text: str, text_w_pt: float) -> int:
    """编号列所需宽度，单位同 w:tblW 的 pct（5000 = 100%）。

    「（式 5-1）」这类中文按章编号比 "(1)" 宽得多，固定 12% 的右列会让编号折成两行
    （实测「（式」/「5-1）」）。按字符宽度估算：全角按 1 em、半角按 0.55 em。
    """
    if not num_text:
        return 600
    em = 12.0  # 编号字号与正文同（小四），仅用于估宽
    width = sum(em if ord(c) > 0x2E80 else em * 0.55 for c in num_text)
    # 实测：按字符宽度估算出的值仍会被 Word 折行（编号列 ~16% 时「（式 5-1）」断成
    # 「（式 5-」/「1）」），单元格还有样式侧的左右内边距等未计入的占位，故留足余量。
    return max(800, min(1150, int(width / text_w_pt * 5000 * 1.15) + 260))

def _table_layout_key(tbl, nsmap):
    """公式表的版式指纹：列宽表 + 各单元格宽度。

    两张表只有版式一致才能并成一张。否则并完所有行共用第一张的列宽，第二张的
    编号列会被压窄——正是本模块要避免的"编号折成两行"（如 (9) 与 (10)、
    （式 5-9）与（式 5-10）的编号列宽度并不相同）。
    """
    grid = tbl.xpath('./w:tblGrid', namespaces=nsmap)
    cells = tbl.xpath('./w:tr[1]/w:tc/w:tcPr/w:tcW', namespaces=nsmap)
    return (etree.tostring(grid[0]) if grid else b'',
            tuple(f"{c.get(W('w'))}/{c.get(W('type'))}" for c in cells))


def merge_adjacent_equation_tables(tables, nsmap):
    """把相邻的公式表显式并成一张多行表，返回合并次数。

    OOXML 里两个相邻的 w:tbl 之间不隔 w:p，语义上就是**同一张表的两行**：Word 打开
    再存盘会把它悄悄并掉，产物因此不可复现，外人一存盘结构就变了。与其让 Word 替
    我们决定，不如导出时就并好——XML 与渲染结果一致。

    版式不同的两张表不能并（见 _table_layout_key），改用一个 1pt 高的空段落隔开：
    既让 XML 语义明确，又几乎不产生可见间距。
    """
    merged = 0
    i = 0
    while i < len(tables) - 1:
        a, b = tables[i], tables[i + 1]
        if a.getparent() is None or a.getparent() is not b.getparent() or a.getnext() is not b:
            i += 1
            continue
        if _table_layout_key(a, nsmap) == _table_layout_key(b, nsmap):
            for tr in b.xpath('./w:tr', namespaces=nsmap):
                a.append(tr)          # lxml 会把 tr 从 b 移走
            b.getparent().remove(b)
            tables.pop(i + 1)
            merged += 1
        else:
            b.addprevious(_separator_paragraph())
            i += 1
    return merged


def _separator_paragraph():
    """1pt 高的空段落：把两张版式不同的公式表隔开，但几乎看不见。"""
    sep = etree.Element(W('p'), nsmap={'w': NS_W})
    ppr = etree.SubElement(sep, W('pPr'))
    spacing = etree.SubElement(ppr, W('spacing'))
    spacing.set(W('before'), '0')
    spacing.set(W('after'), '0')
    spacing.set(W('line'), '20')
    spacing.set(W('lineRule'), 'exact')
    rpr = etree.SubElement(sep, W('rPr'))
    etree.SubElement(rpr, W('sz')).set(W('val'), '2')
    etree.SubElement(rpr, W('szCs')).set(W('val'), '2')
    return sep


_EQ_REF_TAIL = re.compile(r'(\d+(?:\.\d+)?)\s*$')
_XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def rewrite_eq_references(root, nsmap) -> int:
    """把正文里的公式交叉引用改成与编号一致的 CJK 写法 → 改写条数。

    公式**旁边**的编号由 fix_equations_in_xml 改成 `（2-1）`；正文里**引用**它的地方
    是 Quarto 生成的超链接（`w:hyperlink w:anchor="eq-xxx"`），显示文字「式 2.1」是
    普通文本——不跟着改，一份文档里就会同时出现 `（2-1）` 和 `式 2.1`。

    只动锚点以 `eq-` 开头的超链接，所以不会误伤别的文字（靠锚点认，不靠正则猜）。
    """
    changed = 0
    for hl in root.xpath('//w:hyperlink[starts-with(@w:anchor, "eq-")]', namespaces=nsmap):
        ts = hl.xpath('.//w:t', namespaces=nsmap)
        if not ts:
            continue
        text = ''.join(t.text or '' for t in ts)
        m = _EQ_REF_TAIL.search(text)
        if not m:
            continue
        # 「式 2.1」→「式（2-1）」：编号换写法，前缀与编号之间的空格按中文惯例去掉
        ts[0].text = text[:m.start()].rstrip() + '（' + m.group(1).replace('.', '-') + '）'
        ts[0].set(_XML_SPACE, 'preserve')
        for t in ts[1:]:
            t.text = ''
        changed += 1
    return changed


def fix_equations_in_xml(doc_xml_bytes: bytes, eq_number_style: str = 'asis') -> bytes:
    root = etree.fromstring(doc_xml_bytes)
    nsmap = {'w': NS_W, 'm': NS_M}
    text_w_pt = _text_width_pt(root)

    # 查找包含数学公式与编号的段落
    paragraphs = root.xpath('//w:p', namespaces=nsmap)
    modified_count = 0
    skipped_kinds = Counter()
    created_tables = []   # 本轮生成的公式表，按文档顺序，供相邻合并用

    for p in paragraphs:
        # 跳过已经在表格内部的段落
        if p.xpath('ancestor::w:tbl', namespaces=nsmap):
            continue

        # 只处理真正的显示公式段落（m:oMathPara）。
        # 不能把含行内公式（m:oMath）的正文段当作公式：正文段若同时含括号缩写
        # （如 "(ICVs)" "(NLP)"）会被误判为带编号公式并整段转成表格，丢失正文文本。
        math_elements = p.xpath('.//m:oMathPara', namespaces=nsmap)
        if not math_elements:
            continue

        # 编号由 Quarto crossref 生成，落在 oMath 尾部的 m:r 里（m:t），不在 w:t 里。
        # 取不到编号＝这条公式本来就不编号，保持原样居中即可。
        eq_num_str = extract_quarto_eq_number(math_elements[0])
        if not eq_num_str:
            continue

        # 只替换「纯公式段」：替换语义是整段丢弃（见下方 parent.remove），
        # 同段一旦出现公式外的**内容**就会连同它一起消失。Quarto 实测形状是
        # pPr + bookmarkStart + oMathPara + bookmarkEnd（无正文），故正常产物全走
        # 转换分支；出现 w:r / w:hyperlink / w:ins 等则说明形状认不出——
        # 按「认不出的原样放过」（同 format_eq_number 判据）不转换，宁可少优化一处
        # 排版，也不静默吃内容：post-flight 守护只比对三位以上小数，不含数字的
        # 丢失内容它拦不住。
        math_set = {id(e) for e in math_elements}
        foreign = [c for c in p if id(c) not in math_set
                   and etree.QName(c).localname not in _META_PARA_CHILDREN]
        if foreign:
            for c in foreign:
                skipped_kinds[etree.QName(c).localname] += 1
            continue

        # 构建 1 行 3 列 无边框表格
        tbl = etree.Element(W('tbl'), nsmap={'w': NS_W, 'm': NS_M})
        tbl_pr = etree.SubElement(tbl, W('tblPr'))
        
        # 表格居中，宽度 100% (5000 / 50分之一百分比，即 100%)
        tbl_w = etree.SubElement(tbl_pr, W('tblW'))
        tbl_w.set(W('w'), '5000')
        tbl_w.set(W('type'), 'pct')
        
        tbl_jc = etree.SubElement(tbl_pr, W('jc'))
        tbl_jc.set(W('val'), 'center')
        
        # 无边框
        tbl_borders = etree.SubElement(tbl_pr, W('tblBorders'))
        for b_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
            b_el = etree.SubElement(tbl_borders, W(b_name))
            b_el.set(W('val'), 'none')
            
        # 固定布局：不写 tblLayout 时 Word 走 autofit，会按内容重算列宽，把编号列压到
        # 只有约 40pt——「（式 5-1）」这种中文按章编号就折成两行。方程表本来就是固定
        # 栅格（编号贴右边距、公式居中），必须让 Word 照栅格来。
        tbl_layout = etree.SubElement(tbl_pr, W('tblLayout'))
        tbl_layout.set(W('type'), 'fixed')

        # 单元格默认间距 0
        tbl_cell_mar = etree.SubElement(tbl_pr, W('tblCellMar'))
        for m_name in ['top', 'left', 'bottom', 'right']:
            m_el = etree.SubElement(tbl_cell_mar, W(m_name))
            m_el.set(W('w'), '0')
            m_el.set(W('type'), 'dxa')
            
        # 三列宽度：左右两列等宽（编号列按编号实际宽度算，短编号即原来的 12%），
        # 等宽才能让中间列在整页上居中——公式居中靠的就是这个。
        eq_num_str = format_eq_number(eq_num_str, eq_number_style)
        num_pct = _eq_number_pct(eq_num_str, text_w_pt)
        mid_pct = 5000 - 2 * num_pct
        grid_total = int(text_w_pt * 20)          # 正文宽（twips）
        tbl_grid = etree.SubElement(tbl, W('tblGrid'))
        for units in (num_pct, mid_pct, num_pct):
            grid_col = etree.SubElement(tbl_grid, W('gridCol'))
            grid_col.set(W('w'), str(int(grid_total * units / 5000)))
            
        # 继承原段落样式（若存在）
        orig_pstyle_el = p.xpath('./w:pPr/w:pStyle', namespaces=nsmap)
        orig_pstyle = orig_pstyle_el[0].get(W('val')) if orig_pstyle_el else None

        # 唯一的一行 (tr)
        tr = etree.SubElement(tbl, W('tr'))
        
        # ── 第 1 列: 左侧空白占位 ──
        tc1 = etree.SubElement(tr, W('tc'))
        tc1_pr = etree.SubElement(tc1, W('tcPr'))
        tc1_w = etree.SubElement(tc1_pr, W('tcW'))
        tc1_w.set(W('w'), str(num_pct))
        tc1_w.set(W('type'), 'pct')
        tc1_v_align = etree.SubElement(tc1_pr, W('vAlign'))
        tc1_v_align.set(W('val'), 'center')
        tc1_p = etree.SubElement(tc1, W('p'))
        tc1_ppr = etree.SubElement(tc1_p, W('pPr'))
        if orig_pstyle:
            ps1 = etree.SubElement(tc1_ppr, W('pStyle'))
            ps1.set(W('val'), orig_pstyle)
        tc1_sp = etree.SubElement(tc1_ppr, W('spacing'))
        tc1_sp.set(W('before'), '0')
        tc1_sp.set(W('after'), '0')
        
        # ── 第 2 列: 公式居中 ──
        tc2 = etree.SubElement(tr, W('tc'))
        tc2_pr = etree.SubElement(tc2, W('tcPr'))
        tc2_w = etree.SubElement(tc2_pr, W('tcW'))
        tc2_w.set(W('w'), str(mid_pct))
        tc2_w.set(W('type'), 'pct')
        tc2_v_align = etree.SubElement(tc2_pr, W('vAlign'))
        tc2_v_align.set(W('val'), 'center')
        tc2_p = etree.SubElement(tc2, W('p'))
        tc2_ppr = etree.SubElement(tc2_p, W('pPr'))
        if orig_pstyle:
            ps2 = etree.SubElement(tc2_ppr, W('pStyle'))
            ps2.set(W('val'), orig_pstyle)
        tc2_jc = etree.SubElement(tc2_ppr, W('jc'))
        tc2_jc.set(W('val'), 'center') # 居中对齐
        tc2_sp = etree.SubElement(tc2_ppr, W('spacing'))
        tc2_sp.set(W('before'), '120') # 适当上下间距
        tc2_sp.set(W('after'), '120')
        
        # 将原段落中的数学公式元素移动到第 2 列
        for m_elem in math_elements:
            tc2_p.append(m_elem)

        # 书签/拼写标记随公式一起保留（原地整段丢弃会连带删掉 crossref 锚点）
        for meta in [c for c in p if etree.QName(c).localname in _META_PARA_CHILDREN
                     and etree.QName(c).localname != 'pPr']:
            tc2_p.append(meta)
            
        # ── 第 3 列: 编号靠右 ──
        tc3 = etree.SubElement(tr, W('tc'))
        tc3_pr = etree.SubElement(tc3, W('tcPr'))
        tc3_w = etree.SubElement(tc3_pr, W('tcW'))
        tc3_w.set(W('w'), str(num_pct))
        tc3_w.set(W('type'), 'pct')
        tc3_v_align = etree.SubElement(tc3_pr, W('vAlign'))
        tc3_v_align.set(W('val'), 'center')
        tc3_p = etree.SubElement(tc3, W('p'))
        tc3_ppr = etree.SubElement(tc3_p, W('pPr'))
        if orig_pstyle:
            ps3 = etree.SubElement(tc3_ppr, W('pStyle'))
            ps3.set(W('val'), orig_pstyle)
        tc3_jc = etree.SubElement(tc3_ppr, W('jc'))
        tc3_jc.set(W('val'), 'right') # 靠右对齐
        tc3_sp = etree.SubElement(tc3_ppr, W('spacing'))
        tc3_sp.set(W('before'), '0')
        tc3_sp.set(W('after'), '0')
        
        # 写入编号 Run（自然继承段落样式，不硬编码写死字体与字号）
        tc3_r = etree.SubElement(tc3_p, W('r'))
        tc3_t = etree.SubElement(tc3_r, W('t'))
        tc3_t.text = eq_num_str
        
        # 用构建好的表格替换原公式段落
        parent = p.getparent()
        if parent is not None:
            idx = parent.index(p)
            parent.insert(idx, tbl)
            parent.remove(p)
            created_tables.append(tbl)
            modified_count += 1

    merged_count = merge_adjacent_equation_tables(created_tables, nsmap)

    # CJK 编号还要把正文里的引用一起改，否则一份文档里会同时出现 （2-1） 与 式 2.1
    ref_count = rewrite_eq_references(root, nsmap) if eq_number_style == 'cjk' else 0

    if modified_count > 0:
        print(f"✨ 成功优化 {modified_count} 个公式的排版（公式居中，编号靠右）")
    if ref_count:
        print(f"🔗 同步改写 {ref_count} 处正文公式引用为 CJK 编号写法")
    if merged_count:
        print(f"📐 合并 {merged_count} 处相邻公式表（相邻 w:tbl 本就是一表多行，"
              f"显式并好以免 Word 存盘时替我们改写）")
    if skipped_kinds:
        # 不静默：跳过意味着这几处公式没有靠右编号，用户/AI 该知道原因
        kinds = '、'.join(f'{k}×{v}' for k, v in sorted(skipped_kinds.items()))
        print(f"ℹ 跳过 {sum(skipped_kinds.values())} 个公式段（同段含公式外内容：{kinds}）"
              f"——保持原样以免丢内容，编号不做右对齐")
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone='yes')


def process_docx(docx_path: str, eq_number_style: str = 'asis'):
    with zipfile.ZipFile(docx_path, 'r') as zin:
        doc_xml = zin.read('word/document.xml')
        styles_xml = zin.read('word/styles.xml') if 'word/styles.xml' in zin.namelist() else None
        styles_with_effects_xml = zin.read('word/stylesWithEffects.xml') if 'word/stylesWithEffects.xml' in zin.namelist() else None
        other_files = {item.filename: zin.read(item.filename) for item in zin.infolist() if item.filename not in ('word/document.xml', 'word/styles.xml', 'word/stylesWithEffects.xml')}

    new_doc_xml = fix_equations_in_xml(doc_xml, eq_number_style)
    cleaned_styles_xml = strip_theme_attrs_from_xml(styles_xml) if styles_xml else None

    tmp_path = docx_path + ".tmp"
    with zipfile.ZipFile(tmp_path, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
        zout.writestr('word/document.xml', new_doc_xml)
        if cleaned_styles_xml:
            zout.writestr('word/styles.xml', cleaned_styles_xml)
            if styles_with_effects_xml:
                zout.writestr('word/stylesWithEffects.xml', cleaned_styles_xml)
        for fname, fbytes in other_files.items():
            zout.writestr(fname, fbytes)

    os.replace(tmp_path, docx_path)
    print(f"✅ 已写入更新与主题深度清理: {docx_path}")

if __name__ == '__main__':
    args = sys.argv[1:]
    style = 'asis'
    if '--eq-number-style' in args:
        i = args.index('--eq-number-style')
        if i + 1 >= len(args):
            print("错误: --eq-number-style 需要取值（asis | cjk）")
            sys.exit(1)
        style = args[i + 1]
        del args[i:i + 2]
    if style not in ('asis', 'cjk'):
        print(f"错误: --eq-number-style 只接受 asis | cjk，收到: {style}")
        sys.exit(1)
    if len(args) < 1:
        print("用法: python3 fix_docx_equations.py <target.docx> [--eq-number-style asis|cjk]")
        sys.exit(1)
    target = args[0]
    if not os.path.exists(target):
        print(f"错误: 文件不存在: {target}")
        sys.exit(1)
    process_docx(target, style)
