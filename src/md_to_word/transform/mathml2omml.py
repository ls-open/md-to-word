"""md_to_word.transform.mathml2omml — LaTeX → MathML → OMML。

为什么中间过一道 MathML：LaTeX 解析是公共难题，MathML 是 W3C 标准，两者的解析器都有
成熟实现；而 **MathML → OMML 没有标准**，各家写法互不相同——这一段必须自己写，也正是
"标准化部分可以借、非标准化部分必须自研"的判据所在。

当前覆盖学术写作里常见的结构：上下标、分式、根式、求和/积分、括号、矩阵与多行公式。
遇到没覆盖的 MathML 元素抛 `UnsupportedMath`，不做静默降级（公式错了比排版错更难发现）。
"""

from __future__ import annotations

from lxml import etree

from md_to_word.i18n import t

MATHML_NS = "http://www.w3.org/1998/Math/MathML"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class UnsupportedMath(NotImplementedError):
    """MathML 里出现了尚未覆盖的结构。"""


def _m(tag: str) -> str:
    return f"{{{M_NS}}}{tag}"


def _local(element) -> str:
    return etree.QName(element).localname


def _el(tag: str, *children, **attrs):
    node = etree.Element(_m(tag))
    for key, value in attrs.items():
        node.set(_m(key), value)
    for child in children:
        if child is not None:
            node.append(child)
    return node


def _run(text: str, upright: bool = False):
    """一个数学 run。变量默认斜体（OMML 不写 sty 即斜体），数字与运算符要直立。"""
    run = _el("r")
    if upright:
        rpr = etree.SubElement(run, _m("rPr"))
        etree.SubElement(rpr, _m("sty")).set(_m("val"), "p")
    t = etree.SubElement(run, _m("t"))
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return run


class _Converter:
    def __init__(self, lang: str = "zh") -> None:
        self.lang = lang

    def convert(self, element) -> list:
        handler = getattr(self, f"_on_{_local(element)}", None)
        if handler is None:
            raise UnsupportedMath(t("mathml.unknown_element", self.lang, name=_local(element)))
        try:
            return handler(element)
        except UnsupportedMath:
            raise                      # 已经说清是哪个元素了，别再包一层
        except (ValueError, IndexError, KeyError) as exc:
            # 结构不完整（如 `\frac{1}` 只有一个参数）会在各 `_on_*` 里炸成 ValueError；
            # 那是**公式写坏了**，不是本程序的 bug——统一包成 UnsupportedMath，走
            # 「这个结构写不出来」的正常报错路径，而不是甩一个 traceback 给作者。
            raise UnsupportedMath(
                t("mathml.structure_invalid", self.lang, name=_local(element), err=exc)
            ) from exc

    # ── 基础 ────────────────────────────────────────────────────────
    def _on_math(self, element) -> list:
        return self._children(element)

    def _on_mrow(self, element) -> list:
        return self._children(element)

    def _children(self, element) -> list:
        r"""逐个子元素转换；大型运算符要**吃掉后面一个元素当被运算体**。

        OMML 的 `m:nary` 自带 `m:e`（被运算体），而 MathML 里 `\sum_{k} a_k` 是并列的
        兄弟节点——`msub(∑,k)` 后面跟 `a_k`。不把 `a_k` 放进 `m:e`，Word 会先画一个空的
        求和号（带占位框），再把 `a_k` 当普通项排在后面，下限 `k` 被挤到下一行去。
        texmath（TeX → OMML 的常用实现）同样如此：只吃紧邻的一个元素，其余留在 nary 外面。
        """
        out: list = []
        kids = list(element)
        i = 0
        while i < len(kids):
            nodes = self.convert(kids[i])
            nary = nodes[0] if len(nodes) == 1 and _is_nary(nodes[0]) else None
            if nary is not None and len(nary.find(_m("e"))) == 0 and i + 1 < len(kids):
                operand = nary.find(_m("e"))
                for node in self.convert(kids[i + 1]):
                    operand.append(node)
                out.extend(nodes)
                i += 2
                continue
            out.extend(nodes)
            i += 1
        return out

    def _on_mi(self, element) -> list:
        return [_run(element.text or "", upright=False)]

    def _on_mn(self, element) -> list:
        return [_run(element.text or "", upright=True)]

    def _on_mo(self, element) -> list:
        text = (element.text or "").strip()
        # 大型运算符（求和/积分）在 MathML 里也是 mo，但 OMML 有专门的 nary
        if text in ("∑", "∏", "∫", "∬", "∮"):
            return [_nary(text)]
        return [_run(text, upright=True)]

    def _on_mtext(self, element) -> list:
        return [_run(element.text or "", upright=True)]

    def _on_mspace(self, element) -> list:
        return []

    def _on_mstyle(self, element) -> list:
        return self._children(element)

    # ── 结构 ────────────────────────────────────────────────────────
    def _on_mfrac(self, element) -> list:
        num, den = list(element)[:2]
        frac = _el("f")
        num_el = etree.SubElement(frac, _m("num"))
        for node in self.convert(num):
            num_el.append(node)
        den_el = etree.SubElement(frac, _m("den"))
        for node in self.convert(den):
            den_el.append(node)
        return [frac]

    def _on_msup(self, element) -> list:
        base, sup = list(element)[:2]
        base_nodes = self.convert(base)
        if len(base_nodes) == 1 and _is_nary(base_nodes[0]):
            nary = base_nodes[0]
            _fill(nary.find(_m("sup")), self.convert(sup))
            _hide(nary, sup=True)
            return [nary]
        node = _el("sSup")
        e = etree.SubElement(node, _m("e"))
        for child in self.convert(base):
            e.append(child)
        sup_el = etree.SubElement(node, _m("sup"))
        for child in self.convert(sup):
            sup_el.append(child)
        return [node]

    def _on_msub(self, element) -> list:
        base, sub = list(element)[:2]
        base_nodes = self.convert(base)
        if len(base_nodes) == 1 and _is_nary(base_nodes[0]):
            nary = base_nodes[0]
            _fill(nary.find(_m("sub")), self.convert(sub))
            _hide(nary, sub=True)
            return [nary]
        node = _el("sSub")
        e = etree.SubElement(node, _m("e"))
        for child in self.convert(base):
            e.append(child)
        sub_el = etree.SubElement(node, _m("sub"))
        for child in self.convert(sub):
            sub_el.append(child)
        return [node]

    def _on_msubsup(self, element) -> list:
        base, sub, sup = list(element)[:3]
        base_nodes = self.convert(base)
        # 求和/积分的上下限要进 nary 自己的 sub/sup，不能在外面套一层 sSubSup
        if len(base_nodes) == 1 and _is_nary(base_nodes[0]):
            nary = base_nodes[0]
            _fill(nary.find(_m("sub")), self.convert(sub))
            _fill(nary.find(_m("sup")), self.convert(sup))
            _hide(nary, sub=True, sup=True)
            return [nary]

        node = _el("sSubSup")
        e = etree.SubElement(node, _m("e"))
        for child in self.convert(base):
            e.append(child)
        sub_el = etree.SubElement(node, _m("sub"))
        for child in self.convert(sub):
            sub_el.append(child)
        sup_el = etree.SubElement(node, _m("sup"))
        for child in self.convert(sup):
            sup_el.append(child)
        return [node]

    def _on_msqrt(self, element) -> list:
        rad = _el("rad")
        etree.SubElement(rad, _m("radPr")).append(_el("degHide", val="1"))
        etree.SubElement(rad, _m("deg"))
        e = etree.SubElement(rad, _m("e"))
        for child in self._children(element):
            e.append(child)
        return [rad]

    def _on_mroot(self, element) -> list:
        base, deg = list(element)[:2]
        rad = _el("rad")
        etree.SubElement(rad, _m("radPr"))
        deg_el = etree.SubElement(rad, _m("deg"))
        for child in self.convert(deg):
            deg_el.append(child)
        e = etree.SubElement(rad, _m("e"))
        for child in self.convert(base):
            e.append(child)
        return [rad]

    def _on_mfenced(self, element) -> list:
        return self._children(element)

    def _on_mover(self, element) -> list:
        kids = list(element)
        if len(kids) < 2:
            return self._children(element)
        base, over = kids[0], kids[1]
        over_text = (over.text or "").strip()
        # 重音符号映射：上面的字符 → 微软 OMML 的 accPr 字符
        acc_map = {
            "^": "\u0302",      # \hat
            "¯": "\u0304",      # \bar (macron)
            "→": "\u20d7",      # \vec
            "˙": "\u0307",      # \dot
            "¨": "\u0308",      # \ddot
            "~": "\u0303",      # \tilde
            "―": "\u0304",      # horizontal bar
            "‾": "\u0305",      # overline
        }
        # 判据是「上面是一个单独的符号」，不是「上面的文字很短」：`\overset{def}{=}` 的
        # 上面是一个 mrow（text 为空），按长度判会被当成重音符，把 `=` 变成 `≙`。
        mark = acc_map.get(over_text)
        is_single_symbol = len(over) == 0 and len(over_text) == 1
        if mark or (element.get("accent") == "true" and is_single_symbol):
            acc = _el("acc")
            pr = etree.SubElement(acc, _m("accPr"))
            val = mark or over_text
            etree.SubElement(pr, _m("chr")).set(_m("val"), val)
            e = etree.SubElement(acc, _m("e"))
            for child in self.convert(base):
                e.append(child)
            return [acc]
        lim = _el("limUpp")
        e = etree.SubElement(lim, _m("e"))
        for child in self.convert(base):
            e.append(child)
        lim_el = etree.SubElement(lim, _m("lim"))
        for child in self.convert(over):
            lim_el.append(child)
        return [lim]

    def _on_munder(self, element) -> list:
        kids = list(element)
        if len(kids) < 2:
            return self._children(element)
        base, under = kids[0], kids[1]
        under_text = (under.text or "").strip()
        if element.get("accentunder") == "true" or under_text in ("―", "_", "\u2015", "\u0332"):
            acc = _el("acc")
            pr = etree.SubElement(acc, _m("accPr"))
            etree.SubElement(pr, _m("chr")).set(_m("val"), "\u0332")
            e = etree.SubElement(acc, _m("e"))
            for child in self.convert(base):
                e.append(child)
            return [acc]
        lim = _el("limLow")
        e = etree.SubElement(lim, _m("e"))
        for child in self.convert(base):
            e.append(child)
        lim_el = etree.SubElement(lim, _m("lim"))
        for child in self.convert(under):
            lim_el.append(child)
        return [lim]

    def _on_munderover(self, element) -> list:
        base, sub, sup = list(element)[:3]
        base_nodes = self.convert(base)
        if len(base_nodes) == 1 and _is_nary(base_nodes[0]):
            nary = base_nodes[0]
            _fill(nary.find(_m("sub")), self.convert(sub))
            _fill(nary.find(_m("sup")), self.convert(sup))
            _hide(nary, sub=True, sup=True)
            return [nary]
        node = _el("sSubSup")
        e = etree.SubElement(node, _m("e"))
        for child in self.convert(base):
            e.append(child)
        sub_el = etree.SubElement(node, _m("sub"))
        for child in self.convert(sub):
            sub_el.append(child)
        sup_el = etree.SubElement(node, _m("sup"))
        for child in self.convert(sup):
            sup_el.append(child)
        return [node]

    def _on_mtable(self, element) -> list:
        matrix = _el("m")
        for row in element:
            if _local(row) != "mtr":
                raise UnsupportedMath(t("mathml.mtable_child", self.lang, name=_local(row)))
            mr = etree.SubElement(matrix, _m("mr"))
            for cell in row:
                for node in self.convert(cell):
                    mr.append(node)
        return [matrix]

    def _on_mtr(self, element) -> list:
        return self._children(element)

    def _on_mtd(self, element) -> list:
        return self._children(element)


def _is_nary(node) -> bool:
    return hasattr(node, "tag") and node.tag == _m("nary")


def _fill(slot, nodes) -> None:
    for node in nodes:
        slot.append(node)


def _hide(nary, *, sub: bool = False, sup: bool = False) -> None:
    """标明哪一侧的上下限是真的有内容。

    nary 里没有内容的 sub/sup 会留下一个空占位框，Word 里看得到；`*Hide=on` 让 Word
    不画它。texmath 同样如此（`supHide=on`）。
    """
    pr = nary.find(_m("naryPr"))
    for tag, present in (("subHide", sub), ("supHide", sup)):
        node = pr.find(_m(tag))
        if node is None:
            node = etree.SubElement(pr, _m(tag))
        node.set(_m("val"), "off" if present else "on")


def _nary(symbol: str):
    """求和/积分：OMML 的 nary。

    sub/sup 先留空，由外层的上下标填；`m:e` 由 `_children` 用紧随其后的一项填。
    三项都缺时 Word 会画空占位框，所以填过之后要用 `_hide()` 标出哪侧真的有内容。
    """
    nary = _el("nary")
    pr = etree.SubElement(nary, _m("naryPr"))
    etree.SubElement(pr, _m("chr")).set(_m("val"), symbol)
    etree.SubElement(pr, _m("limLoc")).set(_m("val"), "undOvr" if symbol in "∑∏" else "subSup")
    etree.SubElement(nary, _m("sub"))
    etree.SubElement(nary, _m("sup"))
    etree.SubElement(nary, _m("e"))
    return nary


def mathml_to_omml(mathml: str | bytes, lang: str = "zh"):
    """MathML 字符串 → OMML 元素列表（`m:r` / `m:f` / `m:sSup` …）。

    `lang` 决定解析失败时的报错语言：英文稿的公式出错，读到的得是英文。
    """
    data = mathml.encode("utf-8") if isinstance(mathml, str) else mathml
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError as exc:
        # 转换器偶有产出非法 XML 的情形（`aligned` 里的 `&` 会漏成裸实体）。这类失败要
        # 一句话说清是哪条公式，不能把 lxml 的 traceback 甩给作者。
        raise UnsupportedMath(t("mathml.malformed", lang, err=exc)) from exc
    return _Converter(lang).convert(root)


# `aligned` 是 latex2mathml 唯一没吃干净的写法：`&` 对齐符会被当成 `<mi>&</mi>`，产出非法
# XML。改用 `split`——语义相同（多行、按 `&` 对齐），产出的是带 `columnalign` 的 mtable。
_ENV_ALIASES = (("\\begin{aligned}", "\\begin{split}"), ("\\end{aligned}", "\\end{split}"))


def latex_to_omml(latex: str, lang: str = "zh") -> list:
    """LaTeX 公式 → OMML 元素列表。"""
    from latex2mathml.converter import convert as latex_to_mathml

    for old, new in _ENV_ALIASES:
        latex = latex.replace(old, new)
    try:
        mathml = latex_to_mathml(latex)
    except Exception as exc:
        raise UnsupportedMath(t("mathml.latex_failed", lang, err=exc)) from exc
    return mathml_to_omml(mathml, lang)
