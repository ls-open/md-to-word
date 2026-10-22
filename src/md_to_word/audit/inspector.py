#!/usr/bin/env python3
"""导出后抽查：拿**产物 docx** 与格式要求文件逐条对账。

只查"XML 里的确定值"——字体、字号、加粗、倾斜、纸张、页边距、页码格式与起始、
奇偶页开关、首页留白。这些正是**实际出过问题**的地方（例如要求"不加粗"而产物
是加粗：样式属性写进去没生效，链路上不报任何错）。

**不查**：域展开后的样子、奇偶页实际版式、页眉双线粗细、表格跨页断行、图是否
压扁——这些只有真正渲染成 PDF 才看得出来，交给人工/渲染核对。

用法:
  python3 -m md_to_word.audit.inspector <产物.docx> --requirements <格式要求.txt> [--quiet]
退出码: 0=全部对上 / 1=有对不上的（逐条打印）/ 2=用法或读取错误
"""
import argparse
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

from md_to_word.template.generator import (
    ALIGN_VAL, BOTTOM_BORDER_STYLE, CJK_FONTS,
    TABLE_CELL_MARGIN_DEFAULT_CM, TABLE_BORDER_SIDES,
    TABLE_DEFAULT_WIDTHS, MinLineSpacing, _TWIPS_PER_CM,
    _pt_to_border_sz, doc_grid_pitch, page_size_twips,
    parse_requirements, table_border_widths,
)

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

# 纸张与对齐表都从生成器 import：同一件事不写两份——写两份，改一处就会漏另一处。



def _tbl_cond(styles: dict, cond: str):
    """Table 样式里的 w:tblStylePr[type=cond]（表头行条件格式）。"""
    tbl = styles.get('table')
    if tbl is None:
        return None
    for sp in tbl.findall(W + 'tblStylePr'):
        if sp.get(W + 'type') == cond:
            return sp
    return None


def _styles_by_name(z: zipfile.ZipFile) -> dict:
    """产物 styles.xml → {名字小写: <w:style>}，同时按 styleId 索引。

    两个都要：查样式用 w:name（小写——底模里是 `heading 1`，而要求文件写
    `Heading 1`，大小写敏感会全部查不到）；沿 basedOn 链上溯用的是 styleId。
    """
    root = etree.fromstring(z.read('word/styles.xml'))
    out = {}
    for s in root.iter(W + 'style'):
        sid = s.get(W + 'styleId')
        if sid:
            out[sid.lower()] = s
        for n in s.findall(W + 'name'):
            v = n.get(W + 'val')
            if v:
                out[v.lower()] = s
    return out


def _walk(styles: dict, name: str):
    """沿 basedOn 链自下而上产出样式元素（先自身，再父级，防环）；表头行产出 firstRow 条件格式。"""
    if name == '表头':
        fr = _tbl_cond(styles, 'firstRow')
        if fr is not None:
            yield fr
        return
    seen = set()
    cur = styles.get((name or '').lower())
    while cur is not None:
        sid = (cur.get(W + 'styleId') or '').lower()
        if sid in seen:
            break
        seen.add(sid)
        yield cur
        based = cur.find(W + 'basedOn')
        cur = styles.get((based.get(W + 'val') or '').lower()) if based is not None else None


def _first(elements, getter):
    """沿链取第一个"有值"的属性。None 表示整条链都没写。"""
    for el in elements:
        v = getter(el)
        if v is not None:
            return v
    return None


# OOXML 的开关值：val 缺省、1、true、on 都是开；0、false、off 是关
_OFF_VALUES = {'0', 'false', 'off'}


def _effective(styles: dict, name: str, tag: str):
    """rPr 下某属性的有效值：'on' / '0' / 具体值 / None(整条链都没写)。

    必须上溯：属性没写不等于"关"——它继承 basedOn。例如 Table Caption 若继承
    底模的 caption（自带加粗），不写 b 的实际效果就是**加粗**。把"没写"一律当成
    "对不上"会刷出一堆误报（实测 37 条里只有 2 条是真的）；一律当成"没事"又会
    漏掉真正继承来的加粗。
    """
    def g(el):
        rpr = el.find(W + 'rPr')
        if rpr is None:
            return None
        e = rpr.find(W + tag)
        if e is None:
            return None
        return e.get(W + 'val') or 'on'
    return _first(_walk(styles, name), g)


def _is_on(styles: dict, name: str, tag: str) -> bool:
    """属性的有效开关状态。整条链都没写 = 关（OOXML 里 b/i 的默认值就是关）。

    注意 val 的写法不止一种：`<w:b/>`（缺省）、`val="1"`、`val="true"` 都是**开**。
    只认 'on' 会把 val="1" 误判成关——真实 docx 里这种写法很常见。
    """
    v = _effective(styles, name, tag)
    return v is not None and v not in _OFF_VALUES


def _pattr(styles: dict, name: str, tag: str, attr: str):
    """pPr 下某元素某属性的有效值（行距/段前段后/缩进/对齐都走这里）。

    `attr` 传**已带命名空间**的属性名（`W + 'val'`），这里不再补——补了就是
    `{ns}{ns}val`，查什么都是 None。
    """
    def g(el):
        ppr = el.find(W + 'pPr')
        if ppr is None:
            return None
        e = ppr.find(W + tag)
        return e.get(attr) if e is not None else None
    return _first(_walk(styles, name), g)


def _pelement(styles: dict, name: str, tag: str):
    """pPr 下某元素的**有效元素**（沿 basedOn 上溯）；None = 整条链都没写。

    与 `_pattr` 同理，只是要的是元素本身（制表位、边框要读元素内部的子节点）：
    本样式没写不等于没有——继承来的制表位/边框会被直接 find 误报成"产物缺少"。
    """
    def g(el):
        ppr = el.find(W + 'pPr')
        return ppr.find(W + tag) if ppr is not None else None
    return _first(_walk(styles, name), g)


def _rfonts(styles: dict, name: str) -> tuple:
    """rFonts 的 (eastAsia, ascii) 有效值，没写的一侧为 None。"""
    def g(el):
        rpr = el.find(W + 'rPr')
        f = rpr.find(W + 'rFonts') if rpr is not None else None
        if f is None:
            return None
        return (f.get(W + 'eastAsia'), f.get(W + 'ascii'))
    val = _first(_walk(styles, name), lambda el: g(el))
    return val or (None, None)


def audit(docx: Path, req_path: Path) -> list:
    """返回不符项列表，每项 (类别, 说明)。空列表 = 全部对上。"""
    problems = []
    spec = parse_requirements(req_path.read_text(encoding='utf-8'))
    z = zipfile.ZipFile(docx)
    styles = _styles_by_name(z)

    # ── 1. 样式（含表头行 firstRow 条件格式）：字体 / 字号 / 加粗 / 倾斜 / 段落属性 ──
    targets = list(spec.styles) + ([spec.table_header] if spec.table_header else [])
    for r in targets:
        name = r['style_name']
        st = _tbl_cond(styles, 'firstRow') if name in ('表头', 'Table Header') else styles.get(name.lower())
        if st is None:
            problems.append(('样式', f'{name}：产物里没有这个样式（要求文件写了，导出后不存在）'))
            continue

        want_fonts = r.get('font_name') or []
        east, ascii_ = _rfonts(styles, name)
        if want_fonts:
            got = [x for x in (east, ascii_) if x]
            # 中文字体落 eastAsia、西文落 ascii；单字体时两者相同
            for f in want_fonts:
                if f not in got:
                    problems.append(('字体', f'{name}：要求 {f}，产物 rFonts={got}'))

        if r.get('font_size'):
            want_sz = str(int(round(r['font_size'].pt * 2)))
            rpr = st.find(W + 'rPr')
            e = rpr.find(W + 'sz') if rpr is not None else None
            got_sz = e.get(W + 'val') if e is not None else None
            if got_sz != want_sz:
                problems.append(('字号', f'{name}：要求 {want_sz}(半磅)，产物 {got_sz}'))

        want_b, want_i = r.get('bold'), r.get('italic')
        on_b, on_i = _is_on(styles, name, 'b'), _is_on(styles, name, 'i')
        src_b, src_i = _effective(styles, name, 'b'), _effective(styles, name, 'i')
        if want_b is True and not on_b:
            problems.append(('加粗', f'{name}：要求加粗，产物没加粗（链上 b={src_b}）'))
        if want_b is False and on_b:
            problems.append(('加粗', f'{name}：要求不加粗，产物是加粗'
                                       f'（b={src_b}——来自底模或继承，没被显式关闭）'))
        if want_i is True and not on_i:
            problems.append(('倾斜', f'{name}：要求斜体，产物没斜体（链上 i={src_i}）'))
        if want_i is False and on_i:
            problems.append(('倾斜', f'{name}：要求不倾斜，产物是斜体（i={src_i}）'))

        # 对齐：要求文件写中文，OOXML 落 jc 的英文值
        if r.get('alignment') is not None:
            want_jc = ALIGN_VAL.get(r['alignment'])
            got_jc = _pattr(styles, name, 'jc', W + 'val')
            if want_jc and got_jc != want_jc:
                problems.append(('对齐', f'{name}：要求 {want_jc}，产物 {got_jc}'))

        # 行距：倍数落 line=倍数*240/auto；磅值落 line=pt*20/exact；最小值落 line=pt*20/atLeast
        if r.get('line_spacing') is not None:
            ls = r['line_spacing']
            if isinstance(ls, MinLineSpacing):
                want_line, want_rule = str(int(round(ls.pt * 20))), 'atLeast'
            elif hasattr(ls, 'pt'):
                want_line, want_rule = str(int(round(ls.pt * 20))), 'exact'
            else:
                want_line, want_rule = str(int(round(float(ls) * 240))), 'auto'
            got_line = _pattr(styles, name, 'spacing', W + 'line')
            got_rule = _pattr(styles, name, 'spacing', W + 'lineRule')
            if got_line != want_line or (got_rule or 'auto') != want_rule:
                problems.append(('行距', f'{name}：要求 line={want_line}/{want_rule}，'
                                          f'产物 line={got_line}/{got_rule}'))

        # 段前 / 段后（pt → twips = pt*20）
        for key, attr, cn in (('space_before', W + 'before', '段前'),
                              ('space_after', W + 'after', '段后')):
            if key in r and hasattr(r[key], 'pt'):
                want_sb = str(int(round(r[key].pt * 20)))
                got_sb = _pattr(styles, name, 'spacing', attr)
                if got_sb != want_sb:
                    problems.append((cn, f'{name}：要求 {want_sb}(twips)，产物 {got_sb}'))

        # 缩进：中文字符单位落 firstLineChars/hangingChars（值=字符数*100）；
        # 英寸/磅绝对单位落 firstLine/hanging（值=pt*20 twips）
        if r.get('indent') is not None and r.get('indent_unit') == 'chars':
            itype = r.get('indent_type')
            if itype == 'first_line':
                want_ind = str(int(r['indent'] * 100))
                got_ind = _pattr(styles, name, 'ind', W + 'firstLineChars')
                if got_ind != want_ind:
                    problems.append(('缩进', f'{name}：要求首行缩进 {r["indent"]} 字符，'
                                              f'产物 firstLineChars={got_ind}'))
            elif itype == 'hanging':
                want_ind = str(int(r['indent'] * 100))
                got_ind = _pattr(styles, name, 'ind', W + 'hangingChars')
                if got_ind != want_ind:
                    problems.append(('缩进', f'{name}：要求悬挂缩进 {r["indent"]} 字符，'
                                              f'产物 hangingChars={got_ind}'))
        elif r.get('indent') is not None and r.get('indent_unit') == 'pt':
            want_ind = str(int(round(r['indent'] * 20)))
            itype = r.get('indent_type')
            if itype == 'first_line':
                got_ind = _pattr(styles, name, 'ind', W + 'firstLine')
                if got_ind != want_ind:
                    problems.append(('缩进', f'{name}：要求首行缩进 {r["indent"]} pt(twips={want_ind})，'
                                              f'产物 firstLine={got_ind}'))
            elif itype == 'hanging':
                got_ind = _pattr(styles, name, 'ind', W + 'hanging')
                if got_ind != want_ind:
                    problems.append(('缩进', f'{name}：要求悬挂缩进 {r["indent"]} pt(twips={want_ind})，'
                                              f'产物 hanging={got_ind}'))

        # 左缩进（目录条目逐级右移）：leftChars = 字符数 * 100
        if r.get('left_indent_chars') is not None:
            want_lc = str(int(r['left_indent_chars'] * 100))
            got_lc = _pattr(styles, name, 'ind', W + 'leftChars')
            if got_lc != want_lc:
                problems.append(('缩进', f'{name}：要求左缩进 {r["left_indent_chars"]} 字符，'
                                          f'产物 leftChars={got_lc}'))

        # 点线制表位（目录条目页码右对齐引导线）
        if r.get('dot_leader_tab'):
            tabs = _pelement(styles, name, 'tabs')
            has_dot = any(t.get(W + 'leader') == 'dot' and t.get(W + 'val') == 'right'
                          for t in (tabs.findall(W + 'tab') if tabs is not None else ()))
            if not has_dot:
                problems.append(('制表位', f'{name}：要求点线制表位，产物缺少 right+dot 制表位'))

        # 加入目录（给自定义标题样式挂大纲级别 outlineLvl）
        if r.get('join_toc'):
            got_ol = _pattr(styles, name, 'outlineLvl', W + 'val')
            if got_ol is None:
                problems.append(('目录', f'{name}：要求加入目录（outlineLvl），产物未设置大纲级别'))

        # 与下段同页（keepNext）：题注跟表、目录标题跟条目——不写就随底模继承定，静默
        if r.get('keep_next') and _pelement(styles, name, 'keepNext') is None:
            problems.append(('同页', f'{name}：要求与下段同页（keepNext），产物未设置'))

        # 段落下边框（如页眉下双线、或显式声明无边框）
        if r.get('bottom_border') in BOTTOM_BORDER_STYLE:
            want_bdr = BOTTOM_BORDER_STYLE[r['bottom_border']]
            pbdr = _pelement(styles, name, 'pBdr')
            bot = pbdr.find(W + 'bottom') if pbdr is not None else None
            got_bdr = bot.get(W + 'val') if bot is not None else None
            if got_bdr != want_bdr:
                problems.append(('边框', f'{name}：要求下边框 {want_bdr}，产物 {got_bdr}'))
            elif r.get('border_width_pt') is not None:
                want_sz = _pt_to_border_sz(r['border_width_pt'])
                got_sz = bot.get(W + 'sz') if bot is not None else None
                if got_sz != want_sz:
                    problems.append(('边框', f'{name}：要求下边框粗 {r["border_width_pt"]}磅(sz={want_sz})，产物 sz={got_sz}'))
        elif r.get('no_border') or r.get('bottom_border') == 'none':
            pbdr = _pelement(styles, name, 'pBdr')
            bot = pbdr.find(W + 'bottom') if pbdr is not None else None
            if bot is not None and bot.get(W + 'val') not in (None, 'none', 'nil'):
                problems.append(('边框', f'{name}：要求无下边框，产物仍残留 bottom={bot.get(W + "val")}'))

        # 西文字体（全局默认 `西文字体：X`）：**自己没指定西文的样式**，西文槽应落它。
        # 判定与写入侧的 split_fonts 同一把尺子（字体名里有没有非中日韩的那个）。
        if spec.default_latin and r.get('font_name') is not None:
            names = r['font_name']
            if not any(not (f in CJK_FONTS or re.search(r'[\u4e00-\u9fff]', f)) for f in names):
                got_ascii = _rfonts(styles, name)[1]
                if got_ascii != spec.default_latin:
                    problems.append(('西文字体', f'{name}：要求全局西文字体 {spec.default_latin}，'
                                                 f'产物 ascii={got_ascii}'))

        # 字符间距（`字距<N>磅`）：rPr/spacing 的 val 是二十分之一磅
        if r.get('char_spacing_pt') is not None:
            want_v = str(int(round(r['char_spacing_pt'] * 20)))
            rpr = st.find(W + 'rPr')
            e = rpr.find(W + 'spacing') if rpr is not None else None
            got_v = e.get(W + 'val') if e is not None else None
            if got_v != want_v:
                problems.append(('字距', f'{name}：要求 {r["char_spacing_pt"]}磅(val={want_v})，产物 {got_v}'))

        # 换行与分页的三个复选框：keepLines / pageBreakBefore / widowControl
        # （「与下段同页」keepNext 在上一段单独查）
        for key, tag, cn in (('keep_lines', 'keepLines', '段中不分页'),
                             ('page_break_before', 'pageBreakBefore', '段前分页')):
            if r.get(key) and _pelement(styles, name, tag) is None:
                problems.append((cn, f'{name}：要求{cn}（{tag}），产物未设置'))
        if r.get('widow_control') is not None:
            # OOXML 里 widowControl **缺省为开**，故"要求开、产物没写"是合规的；
            # 反过来"要求关、产物没写"等于没关，得报。
            got_wc = _pattr(styles, name, 'widowControl', W + 'val')
            is_on = got_wc not in _OFF_VALUES      # None 也算开（缺省）
            if is_on != bool(r['widow_control']):
                problems.append(('孤行控制', f'{name}：要求 {"开" if r["widow_control"] else "关"}'
                                             f'（val={1 if r["widow_control"] else 0}），产物 {got_wc or "缺省(开)"}'))

    # ── 1b. 校对语言：写了 zh-CN 而产物仍是 en-US 时，Word 拿英文校对器查中文 ──
    if spec.proofing_lang:
        st_root = etree.fromstring(z.read('word/styles.xml'))
        lang_el = st_root.find(f'.//{W}lang') if st_root is not None else None
        got = lang_el.get(W + 'eastAsia') if lang_el is not None else None
        if got != spec.proofing_lang:
            problems.append(('校对语言', f'要求 eastAsia={spec.proofing_lang}，产物 {got}'))

    # ── 2. 页面：纸张 / 页边距 ──
    doc = etree.fromstring(z.read('word/document.xml'))
    # 取 **body 末尾那个** sectPr，不是文档里第一个：要求文件里的纸张/页边距/页码描述的是
    # 正文节（参考模板给的那套）。正文里用 {{< section >}} 分出来的节另带自己的 sectPr，
    # 出现在它之前，按"第一个"取就会拿前置节的页码去对正文的要求。
    body = doc.find(W + 'body')
    sect = body.find(W + 'sectPr') if body is not None else None
    if sect is not None:
        pgsz = sect.find(W + 'pgSz')
        if pgsz is not None:
            got = (int(pgsz.get(W + 'w') or 0), int(pgsz.get(W + 'h') or 0))
            want = page_size_twips(spec.page_size)
            if want and got != want:
                problems.append(('纸张', f'要求 {spec.page_size}{want}，产物 {got}'))
        if spec.margins:
            pgmar = sect.find(W + 'pgMar')
            # 「装订线」是折进**左**边距写的（理由见 generate_template 里那段注释：
            # 正文宽度按 pgSz − pgMar 计算，不认 w:gutter，图片会压出右边距），故左边的期望值要加它。
            expect = dict(spec.margins)
            if spec.gutter_cm:
                expect['left'] = expect['left'] + spec.gutter_cm
            for cn, en in (('上', 'top'), ('下', 'bottom'), ('左', 'left'), ('右', 'right')):
                if en not in expect:
                    continue
                want_tw = int(round(expect[en] * 567))   # cm → twips
                got_tw = int(pgmar.get(W + en) or 0) if pgmar is not None else 0
                if abs(got_tw - want_tw) > 2:                  # 容忍 2 twips 取整
                    problems.append(('页边距', f'{cn}边：要求 {expect[en]}cm({want_tw})，产物 {got_tw}'))

        # 文档网格：linePitch 由版心高 ÷ 行数 ÷ 正文行距倍数算出。
        # 这里**直接调写入侧那个函数**——两边各算一遍的话，算法一漂移就互相看不出来
        # （「每页几行」正是靠这条 pitch 兑现的，pitch 错了页面就是错的，而它看不见）。
        if spec.doc_grid_lines and spec.margins:
            grid = sect.find(W + 'docGrid')
            got_pitch = grid.get(W + 'linePitch') if grid is not None else None
            want_pitch = str(doc_grid_pitch(spec, spec.margins))
            if got_pitch != want_pitch:
                problems.append(('文档网格', f'要求每页 {spec.doc_grid_lines} 行'
                                            f'(linePitch={want_pitch})，产物 {got_pitch}'))

        # 页眉/页脚距边界（与页边距是 pgMar 上的两组属性，别混）
        for cn, attr, key in (('页眉', 'header', 'header_distance'), ('页脚', 'footer', 'footer_distance')):
            want_cm = getattr(spec, key, None)
            if want_cm is None:
                continue
            want_tw = int(round(want_cm * 567))
            got_tw = int(pgmar.get(W + attr) or 0) if pgmar is not None else 0
            if abs(got_tw - want_tw) > 2:
                problems.append((f'{cn}距边界', f'要求 {want_cm}cm({want_tw})，产物 {got_tw}'))

        # 页码格式 / 起始 / 首页不同
        if spec.page_number:
            want_fmt, want_start = spec.page_number
            pg = sect.find(W + 'pgNumType')
            got_fmt = pg.get(W + 'fmt') if pg is not None else None
            got_start = pg.get(W + 'start') if pg is not None else None
            if got_fmt != want_fmt:
                problems.append(('页码', f'格式：要求 {want_fmt}，产物 {got_fmt}'))
            if want_start is not None and str(got_start) != str(want_start):
                problems.append(('页码', f'起始：要求 {want_start}，产物 {got_start}'))
        # 只有要求文件写了「首页页眉/页脚内容」时 titlePg 才有意义：整篇不加页眉页脚的
        # 文档（要求里一条页眉页脚行都没有）根本谈不上「首页带出页眉页脚」。
        if any(which == 'first' for _, which in spec.decor) and sect.find(W + 'titlePg') is None:
            problems.append(('首页', '产物没有 titlePg——「首页页眉/页脚内容」不会生效，首页会带出页眉页脚'))

    # ── 4. 表格：边框样式 / 单元格垂直对齐 / 表头跨页重复 ──
    if spec.table:
        tbl = styles.get('table')
        if tbl is None:
            problems.append(('表格', '产物里没有 Table 样式（表格边框与对齐无处落）'))
        else:
            tbl_pr = tbl.find(W + 'tblPr')
            want_align = spec.table.get('align')
            if want_align:
                jc = tbl_pr.find(W + 'jc') if tbl_pr is not None else None
                got = jc.get(W + 'val') if jc is not None else None
                if got != want_align:
                    problems.append(('表格', f'表格对齐：要求 {want_align}，产物 {got}'))
            tstyle = spec.table.get('style')
            declared = spec.table.get('widths') or {}
            borders = tbl_pr.find(W + 'tblBorders') if tbl_pr is not None else None
            if tstyle in ('three-line', 'top-bottom', 'grid'):
                # 期望线宽从生成器那张表取（**同一份规则**）——本处各自推一遍时，
                # 全网格线的上下外框会按 `线宽内` 取期望，把"写了线宽上却不生效"判成通过。
                label = {'three-line': '三线表', 'top-bottom': '顶底线', 'grid': '全网格线'}[tstyle]
                for side, want_pt in table_border_widths(tstyle, declared).items():
                    if want_pt is None:
                        continue
                    want_sz = _pt_to_border_sz(want_pt)
                    e = borders.find(W + side) if borders is not None else None
                    got_sz = e.get(W + 'sz') if e is not None else None
                    if got_sz != want_sz:
                        problems.append(('表格', f'{label} {side} 线：要求 sz={want_sz}'
                                                  f'（{want_pt}磅），产物 sz={got_sz}'))
                # 表头下线在 firstRow 条件格式的**单元格级**（表级会被 insideH 压掉）；
                # 三线表按定义就有（默认 0.75 磅），其余样式只有显式声明才写
                if tstyle == 'three-line' or 'header_bottom' in declared:
                    want_hb_pt = declared.get('header_bottom', TABLE_DEFAULT_WIDTHS['three-line']['header_bottom'])
                    fr = _tbl_cond(styles, 'firstRow')
                    tc = fr.find(W + 'tcPr') if fr is not None else None
                    tcb = tc.find(W + 'tcBorders') if tc is not None else None
                    e = tcb.find(W + 'bottom') if tcb is not None else None
                    got_hb = e.get(W + 'sz') if e is not None else None
                    want_hb = _pt_to_border_sz(want_hb_pt)
                    if got_hb != want_hb:
                        problems.append(('表格', f'{label}表头下线：要求 sz={want_hb}'
                                                  f'（{want_hb_pt}磅），产物 sz={got_hb}'))
            elif tstyle == 'none' and borders is not None:
                for side in TABLE_BORDER_SIDES:
                    e = borders.find(W + side)
                    if e is not None and e.get(W + 'val') not in (None, 'none', 'nil'):
                        problems.append(('表格', f'无边框表格残留 {side}={e.get(W + "val")}'))

            want_va = spec.table.get('valign')
            if want_va:
                wt = _tbl_cond(styles, 'wholeTable')
                tc = wt.find(W + 'tcPr') if wt is not None else None
                va = tc.find(W + 'vAlign') if tc is not None else None
                got_va = va.get(W + 'val') if va is not None else None
                if got_va != want_va:
                    problems.append(('表格', f'单元格垂直对齐：要求 {want_va}，产物 {got_va}'))

            # 单元格内边距：左右两栏由 `单元格内边距Ncm` 定，上下恒为 0。
            # **不写也要对账**——底模的继承链里有个默认值，它不落进 Table 样式就等于由
            # 继承链说了算，而要求文件里写着"不写即 0"。
            want_cm = spec.table.get('cell_margin_cm', TABLE_CELL_MARGIN_DEFAULT_CM)
            want_lr = str(int(round(want_cm * _TWIPS_PER_CM)))
            cell_mar = tbl_pr.find(W + 'tblCellMar') if tbl_pr is not None else None
            for side, want_w in (('top', '0'), ('left', want_lr),
                                 ('bottom', '0'), ('right', want_lr)):
                e = cell_mar.find(W + side) if cell_mar is not None else None
                got_w = e.get(W + 'w') if e is not None else None
                if got_w != want_w:
                    problems.append(('表格', f'单元格内边距{side}：要求 {want_w}(twips)，产物 {got_w}'))

    # ── 5. 表头跨页重复 ──
    if (spec.table_header or {}).get('repeat_header'):
        fr = _tbl_cond(styles, 'firstRow')
        trpr = fr.find(W + 'trPr') if fr is not None else None
        if trpr is None or trpr.find(W + 'tblHeader') is None:
            problems.append(('表格', '要求表头跨页重复（tblHeader），产物没有'))

    # ── 6. 奇偶页不同 ──
    settings = etree.fromstring(z.read('word/settings.xml'))
    wants_even = any(k[1] == 'even' for k in spec.decor)
    has_even = settings.find(W + 'evenAndOddHeaders') is not None
    if wants_even and not has_even:
        problems.append(('奇偶页', '要求了偶数页页眉/页脚，但产物没开「奇偶页不同」'))
    if has_even and sect is not None:
        types = {r.get(W + 'type') or 'default' for r in sect
                 if etree.QName(r).localname.endswith('Reference')}
        if 'even' not in types:
            problems.append(('奇偶页', '产物开了「奇偶页不同」但没有任何 even 页眉/页脚引用'))
    return problems


def main():
    ap = argparse.ArgumentParser(description='导出后抽查：产物 docx ↔ 格式要求文件')
    ap.add_argument('docx', help='导出的产物 .docx')
    ap.add_argument('--requirements', '-r', required=True, help='生成模板用的格式要求文件')
    ap.add_argument('--quiet', '-q', action='store_true', help='只报结论，不逐条列')
    args = ap.parse_args()

    docx, req = Path(args.docx), Path(args.requirements)
    for p in (docx, req):
        if not p.exists():
            print(f'错误: 文件不存在 {p}', file=sys.stderr)
            return 2
    try:
        problems = audit(docx, req)
    except (KeyError, etree.XMLSyntaxError) as e:
        print(f'错误: 产物不是可解析的 docx（{e}）', file=sys.stderr)
        return 2

    if not problems:
        print(f'✓ 导出后抽查通过：{docx.name} 与 {req.name} 逐条对上')
        return 0
    print(f'⚠ 导出后抽查发现 {len(problems)} 处不符（{docx.name} ↔ {req.name}）：')
    if not args.quiet:
        for cat, msg in problems:
            print(f'   [{cat}] {msg}')
    return 1


def audit_docx_against_spec(docx_path: Path | str, req_path: Path | str) -> tuple[bool, list[tuple[str, str]]]:
    """供流水线调用的标准函数：返回 (matched: bool, problems: list)。"""
    problems = audit(Path(docx_path), Path(req_path))
    return (len(problems) == 0, problems)


if __name__ == '__main__':
    sys.exit(main())
