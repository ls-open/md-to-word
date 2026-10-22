#!/usr/bin/env python3
"""read_reference_docx.py — 从一份「参考 .docx」反推 format.txt 草稿。

用法:
    md-to-word-template 参考.docx [-o 草稿.txt]        # 装包后
    python3 scripts/read_reference_docx.py 参考.docx      # 源码检出

目标方给的参考文件（学校模板 / 期刊样例 / 客户旧文档）里的格式，靠人肉目测抄写既慢又漏。
本脚本把**能确定的**读出来写成本工具的写法，把**确定不了的**单独列在末尾注释块里（不猜值
填空）。读完请人工过一遍那份"需确认"清单。

口径（这三条是实测踩出来的，别用 python-docx 的现成 API 代替）：
  1. **中文字体在 `w:rFonts/@w:eastAsia`**：`font.name` 只给西文槽（ascii/hAnsi），
     中文文档的宋体/黑体它一个字都读不到；
  2. **缩进的「字符」形态在 `w:ind/@w:firstLineChars`**：python-docx 只认 twips 的
     `firstLine`，而生成器写的是 Chars —— 用它的 API 会把「首行缩进2字符」读成 `None`；
  3. **行距三态靠 `w:spacing/@w:lineRule`**：`exact`（固定值）与 `atLeast`（最小值）在
     API 层都是 Length，读回来一模一样；两者的差别在内容更高时才显形（固定值会裁掉）。

一并解决的还有：继承（样式属性沿 `basedOn` 链与 `docDefaults` 生效，API 读到的是 None）、
以及段落下边框 / 页码格式 / 表格边框 / 校对语言这些 API 根本没有的属性。
"""
import argparse
import re
import sys
import zipfile
from pathlib import Path
from typing import Optional

from lxml import etree

from md_to_word.i18n import t

from md_to_word.template.generator import CJK_FONTS

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
TWIPS_PER_CM = 566.93

# 页码格式词表：OOXML 值 → 本工具写法（与 generate_template.PAGE_NUMBER_FMT 反向对应）
PGNUM_FMT = {'decimal': '阿拉伯', 'upperRoman': '罗马', 'lowerRoman': '小写罗马',
             'lowerLetter': '字母', 'upperLetter': '大写字母'}
ALIGN = {'both': '两端对齐', 'justify': '两端对齐', 'center': '居中',
         'left': '左对齐', 'right': '右对齐'}
PAPER = {(21.0, 29.7): 'A4', (21.59, 27.94): 'Letter'}
BORDER_STYLE = {'single': '单线', 'double': '双线', 'thinThickMediumGap': '双线',
                'none': '无', 'nil': '无'}


def q(tag: str) -> str:
    return W + tag


class Ref:
    """一份参考 docx 的读取器：先解包，再沿样式继承链取**生效值**。"""

    def __init__(self, path: Path, lang: str = "zh"):
        self.notes: list[str] = []
        # 消息语言：草稿正文始终是本工具的中文词表写法（那是 format.txt 的合法
        # 语法），变的只是「需人工确认」清单与命令行提示。
        self.lang = lang
        # 不是 .docx（多半是把 .md 或别的文件丢进来了）时要说清楚：直接抛 BadZipFile
        # 的 traceback，用户只会看见 "File is not a zip file"。
        try:
            with zipfile.ZipFile(path) as z:
                self.parts = {n: z.read(n) for n in z.namelist()}
            self.styles = etree.fromstring(self.parts['word/styles.xml'])
        except (zipfile.BadZipFile, KeyError) as exc:
            raise ValueError(
                t("extractor.not_docx", lang, path=path.name)
                if exc.__class__ is zipfile.BadZipFile
                else t("extractor.no_styles", lang, path=path.name)
            ) from exc
        self.doc_defaults = self.styles.find(q('docDefaults'))
        self.by_id = {}
        for st in self.styles.findall(q('style')):
            self.by_id[(st.get(q('styleId')) or '').replace(' ', '').lower()] = st
        self.theme = self._theme_fonts()
        # 页面设置一律取 **body 末尾那个 sectPr**（正文节），与导出后对账 / 标记展开 /
        # fix_docx_equations 同一口径。多节文档里第一个 sectPr 是**前置节**（目录、摘要），
        # 按"第一个"取会把前置节的小写罗马页码当成正文的页码读出来。
        doc_root = etree.fromstring(self.parts['word/document.xml'])
        body = doc_root.find(q('body'))
        self.all_sects = doc_root.findall(f'.//{q("sectPr")}')
        self.sect = (body.find(q('sectPr')) if body is not None
                     else (self.all_sects[0] if self.all_sects else None))
        self.base_borders = self._base_border_styles()

    def _base_border_styles(self) -> set:
        """底模（resources/pure_modern_base.docx）里**带下边框**的样式。

        参考文件不写边框时，这些样式要显式写「无边框」把底模继承来的下边框去掉；
        底模本来就没有的样式不必挂（对参考文件不忠实，也是噪音）。
        """
        base = Path(__file__).resolve().parent.parent / 'resources' / 'pure_modern_base.docx'
        if not base.exists():
            return set()
        try:
            with zipfile.ZipFile(base) as z:
                styles = etree.fromstring(z.read('word/styles.xml'))
        except Exception:
            return set()
        ids = {(st.get(q('styleId')) or '').replace(' ', '').lower(): st
               for st in styles.findall(q('style'))}
        out = set()
        for sid in ids:
            cur, seen = sid, set()
            while cur and cur not in seen:
                seen.add(cur)
                st = ids.get(cur)
                if st is None:
                    break
                if st.find(f'{q("pPr")}/{q("pBdr")}/{q("bottom")}') is not None:
                    out.add(sid)
                    break
                b = st.find(q('basedOn'))
                cur = (b.get(q('val')) if b is not None else '') or ''
        return out

    # ── 继承链：样式 → basedOn… → docDefaults ──
    def chain(self, style_id: str) -> list:
        out, seen = [], set()
        sid = (style_id or '').replace(' ', '').lower()
        while sid and sid not in seen:
            seen.add(sid)
            st = self.by_id.get(sid)
            if st is None:
                break
            out.append(st)
            based = st.find(q('basedOn'))
            sid = (based.get(q('val')) if based is not None else '') or ''
        if self.doc_defaults is not None:
            out.append(self.doc_defaults)
        return out

    def eff(self, chain: list, sub: str):
        """取链上第一个设置了 `sub`（如 'pPr/ind'）的元素。

        注意 docDefaults 的元素结构不同（属性在 `rPrDefault/rPr/...` 下），
        故对它多试一层——`docDefaults` 是继承链的终点，漏了它会导致"读不出来"。
        """
        path = '/'.join(q(p) for p in sub.split('/'))
        for el in chain:
            found = el.find(path)
            if found is None and el is self.doc_defaults:
                found = el.find('/'.join([q('rPrDefault'), path]))
            if found is not None:
                return found
        return None

    # ── 主题字体：Word 默认样式用的常是 `*Theme` 引用而非字体名 ──
    def _theme_fonts(self) -> dict:
        out = {}
        raw = self.parts.get('word/theme/theme1.xml')
        if not raw:
            return out
        scheme = etree.fromstring(raw).find(f'.//{A}fontScheme')
        if scheme is None:
            return out
        for key, slot in (('majorAscii', 'majorFont'), ('minorAscii', 'minorFont')):
            el = scheme.find(f'{A}{slot}/{A}latin')
            if el is not None and el.get('typeface'):
                out[key] = el.get('typeface')
            ea = scheme.find(f'{A}{slot}/{A}ea')
            if ea is not None and ea.get('typeface'):
                out[key.replace('Ascii', 'EastAsia')] = ea.get('typeface')
        return out

    def font_of(self, chain: list) -> tuple:
        rf = self.eff(chain, 'rPr/rFonts')
        if rf is None:
            return None, None
        def pick(name, theme_name):
            v = rf.get(q(name))
            if v:
                return v
            t = rf.get(q(theme_name))
            return self.theme.get(t) if t else None
        return pick('eastAsia', 'eastAsiaTheme'), (pick('ascii', 'asciiTheme')
                                                  or pick('hAnsi', 'hAnsiTheme'))


def _content_width_twips(ref: Ref):
    """正文可用宽度（twips），取自参考文件的正文节。取不全返回 None。

    与写入侧 `generate_template._content_width_twips` 同一条公式（含减掉装订线）——
    判断"这个制表位是不是落在版心右边界"要用它。
    """
    sect = ref.sect
    if sect is None:
        return None
    sz, mar = sect.find(q('pgSz')), sect.find(q('pgMar'))
    if sz is None or mar is None or not sz.get(q('w')):
        return None

    def tw(el, name, default=0):
        v = el.get(q(name))
        return int(v) if v is not None else default
    return tw(sz, 'w') - tw(mar, 'left') - tw(mar, 'right') - tw(mar, 'gutter')


def clauses_for(ref: Ref, sid: str) -> tuple:
    """把一份参考样式的生效属性翻译成本工具的子句串。→ (子句列表, 该样式的疑问)"""
    chain = ref.chain(sid)
    out, doubt = [], []

    cjk, latin = ref.font_of(chain)
    if cjk and latin and cjk != latin:
        out.append(f'{cjk}/{latin}')
    elif cjk or latin:
        out.append(cjk or latin)
    else:
        doubt.append(t('extractor.note.font_undefined', ref.lang))

    sz = ref.eff(chain, 'rPr/sz')
    if sz is not None and sz.get(q('val')):
        out.append(f'{int(sz.get(q("val"))) / 2:g}pt')
    else:
        doubt.append(t('extractor.note.size_undefined', ref.lang))
    defined = bool(cjk or latin) and sz is not None and bool(sz.get(q('val')))

    for tag, on, off in (('b', '加粗', '不加粗'), ('i', '倾斜', '不倾斜')):
        el = ref.eff(chain, f'rPr/{tag}')
        if el is None:
            out.append(off)          # 链上没人设过 = 生效值就是不启用
        else:
            v = el.get(q('val'))
            out.append(on if v not in ('0', 'false') else off)

    jc = ref.eff(chain, 'pPr/jc')
    if jc is not None and jc.get(q('val')):
        got = ALIGN.get(jc.get(q('val')))
        if got:
            out.append(got)
        else:
            doubt.append(t('extractor.note.alignment_unsupported', ref.lang,
                           value=jc.get(q('val'))))
    else:
        out.append('左对齐')

    sp = ref.eff(chain, 'pPr/spacing')
    if sp is not None and sp.get(q('line')):
        line = int(sp.get(q('line')))
        rule = sp.get(q('lineRule')) or 'auto'
        if rule == 'auto':
            out.append(f'行距{line / 240:g}倍')
        elif rule == 'exact':
            out.append(f'行距{line / 20:g}磅')
        else:
            out.append(f'行距最小值{line / 20:g}磅')
    else:
        out.append('行距1.0倍')
        doubt.append(t('extractor.note.line_spacing_default', ref.lang))

    def twips_to_pt(name, lines_name, label):
        if sp is None:
            return
        if sp.get(q(name)) is not None:
            out.append(f'{label}{int(sp.get(q(name))) / 20:g}磅')
        elif sp.get(q(lines_name)) is not None:
            n = int(sp.get(q(lines_name))) / 100
            doubt.append(t('extractor.note.line_unit_converted', ref.lang, label=label, lines=n))
            out.append(f'{label}{n * (int(sz.get(q("val"))) / 2 if sz is not None else 12):g}磅')
        else:
            out.append(f'{label}0磅')
    twips_to_pt('before', 'beforeLines', '段前')
    twips_to_pt('after', 'afterLines', '段后')

    ind = ref.eff(chain, 'pPr/ind')
    # **悬挂缩进要先判**。写悬挂缩进时会同时写 `firstLineChars="0"` 去中和继承来的首行缩进
    # （见 generate_template 的 _neutralize_inherited_first_line），而 `"0"` 是个真值字符串，
    # 先判 firstLineChars 那一支就永远命中——实测写「悬挂缩进0.5英寸」读回来变成
    # 「首行缩进0字符 左缩进3.4字符」，悬挂整个丢掉。
    def ind_int(name):
        return int(ind.get(q(name)) or 0) if ind is not None else 0

    hang_chars, hang_tw = ind_int('hangingChars'), ind_int('hanging')
    if hang_chars or hang_tw:
        if hang_chars:
            doubt.append(t('extractor.note.hanging_chars_converted', ref.lang))
            out.append(f'悬挂缩进{hang_chars / 100:g}字符')
        else:
            out.append(f'悬挂缩进{hang_tw / 1440:g}英寸')
    elif ind is not None and ind.get(q('firstLineChars')):
        out.append(f'首行缩进{int(ind.get(q("firstLineChars"))) / 100:g}字符')
    elif ind is not None and ind.get(q('firstLine')):
        out.append(f'首行缩进{int(ind.get(q("firstLine"))) / 1440:g}英寸')
    else:
        out.append('首行缩进0字符')
    # 悬挂缩进在 Word 里就写作 `left` + `hanging` 一对（生成器也是这么写的：两者取同一个值）。
    # 左缩进等于悬挂值时，它是悬挂缩进的另一半，不是独立的左缩进——重复报出来会让草稿多一条
    # 本来就由悬挂缩进决定的值（读回来是「悬挂缩进0.5英寸 左缩进3.4字符」）。
    left_chars, left_tw = ind_int('leftChars'), ind_int('left')
    if left_chars and left_chars != hang_chars:
        out.append(f'左缩进{left_chars / 100:g}字符')
    elif left_tw and left_tw != hang_tw:
        doubt.append(t('extractor.note.left_indent_converted', ref.lang))
        base = int(sz.get(q('val'))) / 2 if sz is not None else 12
        out.append(f'左缩进{round(left_tw / 20 / base, 1):g}字符')

    # 段落下边框：底模自带下边框（如 Word 的 Title）时，参考文件没写就得**显式去掉**
    # ——但底模本来就没有的样式不必挂一句多余的「无边框」（对参考文件不忠实）
    bottom = ref.eff(chain, 'pPr/pBdr/bottom')
    if bottom is None:
        if sid in ref.base_borders:
            out.append('无边框')
    else:
        kind = BORDER_STYLE.get(bottom.get(q('val')))
        if kind is None:
            doubt.append(t('extractor.note.border_kind_unknown', ref.lang,
                           value=bottom.get(q('val'))))
            kind = '单线'
        # 参考文件显式写了「无下边框」→ 折算成「无边框」。两者在本工具里产物一致
        # （都清掉整段 pBdr），只保留一种写法。
        out.append('无边框' if kind == '无' else f'下边框{kind}')
        if kind != '无' and bottom.get(q('sz')):
            out.append(f'边框粗{int(bottom.get(q("sz"))) / 8:g}磅')

    # 制表位：本工具只能声明**一种**（`点线制表位`，右对齐 + 点线、落在版心右边界，
    # 目录条目靠它顶页码）。参考文件里别的制表位表达不了——**要说出来**，不能静默丢：
    # 用户拿学校模板来读，草稿少一条却毫无提示，正是这套实现一直在防的那种失败。
    tabs = ref.eff(chain, 'pPr/tabs')
    tab_list = tabs.findall(q('tab')) if tabs is not None else []
    if tab_list:
        cw = _content_width_twips(ref)
        t0 = tab_list[0]
        canonical = (len(tab_list) == 1 and t0.get(q('val')) == 'right'
                     and t0.get(q('leader')) == 'dot'
                     and cw is not None and abs(int(t0.get(q('pos')) or 0) - cw) <= 20)
        if canonical:
            out.append('点线制表位')
        else:
            where = '、'.join(f"{t.get(q('val')) or 'left'} "
                              f"{int(t.get(q('pos')) or 0) / TWIPS_PER_CM:.2f}cm"
                              f"{'点线' if t.get(q('leader')) == 'dot' else ''}"
                              for t in tab_list)
            doubt.append(t('extractor.note.tabs_limited', ref.lang,
                           count=len(tab_list), where=where))

    # 字符间距（Word「字体 → 高级 → 字符间距」）：rPr/spacing 的 val 是二十分之一磅。
    # 注意别拿成 pPr/spacing——那是行距，同名不同容器（`.//` 会先撞上 pPr 那个）。
    rsp = ref.eff(chain, 'rPr/spacing')
    if rsp is not None and rsp.get(q('val')):
        pt = int(rsp.get(q('val'))) / 20
        if pt:
            out.append(f'字距{pt:g}磅')
    return out, doubt, defined


def read_table(ref: Ref) -> tuple:
    """Table 样式 → 表格行 / 表头行 / 单元格垂直对齐"""
    out, doubt = [], []
    tbl = ref.by_id.get('table')
    if tbl is None:
        return out, doubt
    pr = tbl.find(f'{q("tblPr")}/{q("tblBorders")}')
    if pr is not None:
        def side(name):
            el = pr.find(q(name))
            if el is None:
                return None
            v = el.get(q('val'))
            return None if v in ('none', 'nil') else (int(el.get(q('sz'))) / 8 if el.get(q('sz')) else None)
        top, bottom = side('top'), side('bottom')
        left, right, ih, iv = side('left'), side('right'), side('insideH'), side('insideV')
        if top and bottom and not any((left, right, ih, iv)):
            style = '三线表'
        elif top and bottom and left and right and ih and iv:
            style = '全网格线'
        elif top and bottom and ih and iv and left is None and right is None:
            style = '顶底线'
        elif not any((top, bottom, left, right, ih, iv)):
            style = '无边框'
        else:
            style = '三线表'
            doubt.append(t('extractor.note.table_border_default', ref.lang))
        jc = tbl.find(f'{q("tblPr")}/{q("jc")}')
        align = ALIGN.get(jc.get(q('val')) if jc is not None else 'center', '居中')
        line = [f'表格：{align} {style}']
        for label, v in (('线宽上', top), ('线宽底', bottom)):
            if v:
                line.append(f'{label}{v:g}磅')
        fr = [e for e in tbl.findall(q('tblStylePr')) if e.get(q('type')) == 'firstRow']
        hb = None
        if fr:
            e = fr[0].find(f'{q("tcPr")}/{q("tcBorders")}/{q("bottom")}')
            if e is not None and e.get(q('sz')):
                hb = int(e.get(q('sz'))) / 8
        if hb:
            line.append(f'线宽表头下{hb:g}磅')
        wt = [e for e in tbl.findall(q('tblStylePr')) if e.get(q('type')) == 'wholeTable']
        if wt:
            va = wt[0].find(f'{q("tcPr")}/{q("vAlign")}')
            if va is not None and va.get(q('val')):
                line.append({'center': '单元格垂直居中', 'top': '单元格垂直顶端',
                             'bottom': '单元格垂直底端'}[va.get(q('val'))])
        out.append(' '.join(line))
    else:
        doubt.append(t('extractor.note.table_border_undefined', ref.lang))

    # 表头行样式（firstRow 条件格式）
    fr = [e for e in tbl.findall(q('tblStylePr')) if e.get(q('type')) == 'firstRow']
    if fr and (fr[0].find(q('rPr')) is not None or fr[0].find(q('pPr')) is not None):
        ref.by_id['__firstrow__'] = fr[0]
        try:
            head, hd, _ = clauses_for(ref, '__firstrow__')
        except Exception:
            head, hd = [], ['第一行（表头）样式读取失败']
        out.append('表头：' + ' '.join(head) + (' 跨页重复'
                                                if fr[0].find(f'{q("rPr")}') is not None
                                                and fr[0].find(f'{q("trPr")}/{q("tblHeader")}') is not None
                                                else ''))
        doubt += [f'表头行：{d}' for d in hd]
        ref.by_id.pop('__firstrow__', None)     # 只在真的塞进去过时才清
    return out, doubt


def body_line_multiple(ref: Ref) -> float:
    """正文的行距**倍数**——把参考文件里的 `linePitch` 反推成「每页 N 行」要用它。

    复用样式读取那一套（不另写一遍 XML 解析），优先级与写入侧
    `generate_template.body_line_spacing_multiple` 一致：先「正文」，退回「普通」。
    """
    from md_to_word.template.generator import STYLE_MAP
    sid_of = {(w.replace(' ', '')).lower(): cn for cn, w in STYLE_MAP.items()}
    for cn in ('正文', '普通'):
        sid = next((s for s, c in sid_of.items() if c == cn), None)
        if sid is None or sid not in ref.by_id:
            continue
        cs, _, _ = clauses_for(ref, sid)          # 丢弃 doubt：主流程还会再读一次
        for t in cs:
            m = re.fullmatch(r'行距(\d+(?:\.\d+)?)倍', t)
            if m:
                return float(m.group(1))
    return 1.0


def read_page(ref: Ref, line_multiple: float = 1.0) -> tuple:
    out, doubt = [], []
    sect = ref.sect
    if sect is None:
        return out, ['找不到 sectPr，页面设置读不出来']
    if len(ref.all_sects) > 1:
        doubt.append(t('extractor.note.multi_section', ref.lang, count=len(ref.all_sects)))
    paper = None
    top = bottom = left = right = None          # 文档网格要拿它们算版心高，先占位
    sz = sect.find(q('pgSz'))
    if sz is not None and sz.get(q('w')) and sz.get(q('h')):
        cm = (round(int(sz.get(q('w'))) / TWIPS_PER_CM, 2),
              round(int(sz.get(q('h'))) / TWIPS_PER_CM, 2))
        paper = PAPER.get(cm)
        out.append(f'纸张：{paper}' if paper else f'# 纸张：{cm[0]}×{cm[1]}cm（不是 A4/Letter）')
        if not paper:
            doubt.append(t('extractor.note.paper_unsupported', ref.lang,
                           width=cm[0], height=cm[1]))
    mar = sect.find(q('pgMar'))
    if mar is not None:
        def cm_of(name):
            return round(int(mar.get(q(name))) / TWIPS_PER_CM, 2) if mar.get(q(name)) else None
        top, bottom, left, right = (cm_of(x) for x in ('top', 'bottom', 'left', 'right'))
        if None not in (top, bottom, left, right):
            out.append(f'页边距：上{top:g}cm 下{bottom:g}cm 左{left:g}cm 右{right:g}cm')
        for name, label in (('header', '页眉距边界'), ('footer', '页脚距边界')):
            v = cm_of(name)
            if v:
                out.append(f'{label}：{v:g}cm')
        # 装订线（pgMar/@w:gutter）。本工具自己的产物里不会有它——写入时是**折进左边距**
        # 写的（理由见 design.md §1.5），故这里读的只可能是别人模板里的。
        gut = cm_of('gutter')
        if gut:
            out.append(f'装订线：{gut:g}cm')
    pn = sect.find(q('pgNumType'))
    if pn is not None and pn.get(q('fmt')):
        fmt = PGNUM_FMT.get(pn.get(q('fmt')))
        start = pn.get(q('start'))
        if fmt:
            out.append(f'页码：{fmt}' + (f' 起始{start}' if start else ''))
        else:
            doubt.append(t('extractor.note.page_number_format_unknown', ref.lang,
                           value=pn.get(q('fmt'))))
    # 文档网格：`linePitch` 是「每行多少 twips」，本工具的写法是「每页 N 行」，
    # 中间隔着行距倍数那一步补偿——用写入侧同一个函数反推（doc_grid_lines_from_pitch）。
    grid = sect.find(q('docGrid'))
    if grid is not None and grid.get(q('linePitch')):
        from md_to_word.template.generator import PAGE_SIZE_MAP, doc_grid_lines_from_pitch
        page_size = PAGE_SIZE_MAP.get(paper) if paper else None
        if None in (top, bottom, left, right) or page_size is None:
            doubt.append(t('extractor.note.doc_grid_skipped', ref.lang))
        else:
            n = doc_grid_lines_from_pitch(int(grid.get(q('linePitch'))), line_multiple,
                                          page_size, dict(top=top, bottom=bottom,
                                                          left=left, right=right))
            out.append(f'文档网格：每页{n}行')

    lang = ref.eff([ref.doc_defaults] if ref.doc_defaults is not None else [], 'rPrDefault/rPr/lang')
    if lang is not None and lang.get(q('eastAsia')):
        out.append(f'校对语言：{lang.get(q("eastAsia"))}')
    return out, doubt


def read_decor(ref: Ref) -> tuple:
    """页眉/页脚内容 → 页眉内容：… 等行（含 {页码} {总页数} {样式标题:X} 三种域）"""
    out, doubt = [], []
    slots = {'header1': '页眉内容', 'header2': '偶数页页眉内容', 'header3': '首页页眉内容',
             'footer1': '页脚内容', 'footer2': '偶数页页脚内容', 'footer3': '首页页脚内容'}
    found_any = False
    for name, label in slots.items():
        raw = ref.parts.get(f'word/{name}.xml')
        if not raw:
            continue
        root = etree.fromstring(raw)
        pieces = []
        for el in root.iter():
            if el.tag == q('t') and el.text:
                pieces.append(el.text)
            elif el.tag == q('instrText') and el.text:
                instr = el.text.strip()
                if 'PAGE' in instr:
                    pieces.append('{页码}')
                elif 'NUMPAGES' in instr:
                    pieces.append('{总页数}')
                elif 'STYLEREF' in instr:
                    m = instr.split('"')
                    name_arg = m[1] if len(m) > 1 else ''
                    pieces.append('{样式标题:' + name_arg + '}')
        content = ' '.join(p for p in pieces if p).strip()
        if content:
            found_any = True
            out.append(f'{label}：{content}')
    if not found_any:
        return [], []
    return out, doubt


def _auto_lang(docx: Path) -> str:
    """`--lang auto` 时按**参考文件**判语种：校对语言是 zh-* 或用的是中日韩字体就算中文。

    这里没有稿件正文可数汉字，只能看参考 docx 自己留下的痕迹。
    """
    try:
        probe = Ref(docx)
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return 'zh'
    lang_el = probe.eff([probe.doc_defaults] if probe.doc_defaults is not None else [],
                        'rPrDefault/rPr/lang')
    east = lang_el.get(q('eastAsia')) if lang_el is not None else None
    if east:
        return 'zh' if east.lower().startswith('zh') else 'en'
    fonts = {f.get(q('eastAsia')) for f in probe.styles.iter(q('rFonts'))}
    return 'zh' if any(f in CJK_FONTS for f in fonts if f) else 'en'


def main(argv=None):
    ap = argparse.ArgumentParser(description=t('extractor.cli.description', 'zh'))
    ap.add_argument('docx', help=t('extractor.cli.docx', 'zh'))
    ap.add_argument('-o', '--output', help=t('extractor.cli.output', 'zh'))
    ap.add_argument('--lang', default='auto', help=t('extractor.cli.lang', 'zh'))
    args = ap.parse_args(argv)

    from md_to_word.spec.constants import STYLE_MAP
    from md_to_word.template.generator import REQUIRED_STYLES

    lang = args.lang if args.lang in ('zh', 'en') else _auto_lang(Path(args.docx))
    try:
        ref = Ref(Path(args.docx), lang)
    except ValueError as exc:      # 不是 .docx / 没有样式表：一句话说清楚，别甩 traceback
        print(f'❌ {exc}', file=sys.stderr)
        return 1
    word_to_cn = {(w.replace(' ', '')).lower(): cn for cn, w in STYLE_MAP.items()}

    lines = ['# 由 md-to-word-template 从参考文件读出的草稿，**请核对**',
             f'# 来源: {Path(args.docx).name}']
    for part in (read_page(ref, body_line_multiple(ref)), read_table(ref), read_decor(ref)):
        lines += part[0]
        ref.notes += part[1]

    required_cn = set(REQUIRED_STYLES.values())
    styled, skipped = [], []
    for sid_norm, cn in word_to_cn.items():
        if sid_norm not in ref.by_id:
            continue
        cs, doubt, defined = clauses_for(ref, sid_norm)
        if not defined and cn not in required_cn:
            # 参考文件没给这条样式定义属性 → 整条跳过。硬凑一份"字体=?"的行去生成模板，
            # 只会得到一份必填校验不过、或格式凭空的草稿
            skipped.append(cn)
            continue
        lines.append(f'{cn}：' + ' '.join(cs))
        styled.append(cn)
        ref.notes += [f'{cn}：{d}' for d in doubt]
    if skipped:
        ref.notes.append(t('extractor.note.styles_skipped', ref.lang, names='、'.join(skipped)))
    used = {(st.get(q('val')) or '').replace(' ', '').lower()
            for st in etree.fromstring(ref.parts['word/document.xml']).iter(q('pStyle'))}
    leftover = sorted(k for k in ref.by_id
                      if k in used and k not in word_to_cn and not k.startswith('_'))
    if leftover:
        ref.notes.append(t('extractor.note.styles_unmapped', ref.lang,
                           names='、'.join(sorted(leftover))))

    if ref.notes:
        lines += ['', f'# ── {t("extractor.notes_header", lang)} ──'] + [f'# {n}' for n in ref.notes]
    text = '\n'.join(lines) + '\n'
    if args.output:
        Path(args.output).write_text(text, encoding='utf-8')
        print(t('extractor.draft_written', lang, path=args.output,
                styled=len(styled), notes=len(ref.notes)))
    else:
        print(text, end='')
    return 0


def extract_spec_from_docx(
    docx_path: Path | str, output_path: Optional[Path | str] = None, lang: str = "zh"
) -> str:
    """从给定的 docx 模板反推单行 format.txt 草稿。``lang`` 只管消息，草稿正文用中文词表。"""
    ref = Ref(Path(docx_path), lang)
    from md_to_word.spec.constants import STYLE_MAP
    from md_to_word.template.generator import REQUIRED_STYLES
    word_to_cn = {(w.replace(' ', '')).lower(): cn for cn, w in STYLE_MAP.items()}
    lines = ['# 由 md-to-word-template 从参考文件读出的草稿，**请核对**',
             f'# 来源: {Path(docx_path).name}']
    for part in (read_page(ref, body_line_multiple(ref)), read_table(ref), read_decor(ref)):
        lines += part[0]
        ref.notes += part[1]
    required_cn = set(REQUIRED_STYLES.values())
    for sid_norm, cn in word_to_cn.items():
        if sid_norm not in ref.by_id:
            continue
        cs, doubt, defined = clauses_for(ref, sid_norm)
        if not defined and cn not in required_cn:
            continue
        lines.append(f'{cn}：' + ' '.join(cs))
        ref.notes += [f'{cn}：{d}' for d in doubt]
    if ref.notes:
        lines += ['', f'# ── {t("extractor.notes_header", lang)} ──'] + [f'# {n}' for n in ref.notes]
    text = '\n'.join(lines) + '\n'
    if output_path:
        Path(output_path).write_text(text, encoding='utf-8')
    return text


if __name__ == '__main__':
    sys.exit(main())
