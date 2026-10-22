"""md_to_word.transform.mathml2omml — LaTeX → MathML → OMML。

为什么中间过一道 MathML：LaTeX 解析是公共难题，MathML 是 W3C 标准，两者的解析器都有
成熟实现；而 **MathML → OMML 没有标准**，各家写法互不相同——这一段必须自己写，也正是
"标准化部分可以借、非标准化部分必须自研"的判据所在。

当前覆盖学术写作里常见的结构：上下标、分式、根式、求和/积分、括号、矩阵与多行公式。
遇到没覆盖的 MathML 元素抛 `UnsupportedMath`，不做静默降级（公式错了比排版错更难发现）。
"""

from __future__ import annotations

from lxml import etree

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
    def convert(self, element) -> list:
        handler = getattr(self, f"_on_{_local(element)}", None)
        if handler is None:
            raise UnsupportedMath(f"尚未支持的 MathML 元素：{_local(element)}")
        return handler(element)

    # ── 基础 ────────────────────────────────────────────────────────
    def _on_math(self, element) -> list:
        return self._children(element)

    def _on_mrow(self, element) -> list:
        return self._children(element)

    def _children(self, element) -> list:
        out: list = []
        for child in element:
            out.extend(self.convert(child))
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
        if len(base_nodes) == 1 and _local(base_nodes[0] if hasattr(base_nodes[0], "tag") else element) == "nary":
            nary = base_nodes[0]
            nary.remove(nary.find(_m("sub")))
            nary.remove(nary.find(_m("sup")))
            sub_el, sup_el = _el("sub"), _el("sup")
            for child in self.convert(sub):
                sub_el.append(child)
            for child in self.convert(sup):
                sup_el.append(child)
            nary.insert(1, sup_el)
            nary.insert(1, sub_el)
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

    def _on_mtable(self, element) -> list:
        matrix = _el("m")
        for row in element:
            if _local(row) != "mtr":
                raise UnsupportedMath(f"mtable 里出现了 {_local(row)}")
            mr = etree.SubElement(matrix, _m("mr"))
            for cell in row:
                for node in self.convert(cell):
                    mr.append(node)
        return [matrix]

    def _on_mtr(self, element) -> list:
        return self._children(element)

    def _on_mtd(self, element) -> list:
        return self._children(element)


def _nary(symbol: str):
    """求和/积分：OMML 的 nary。上下限由外层 msubsup 提供，这里只放算子本身。"""
    nary = _el("nary")
    pr = etree.SubElement(nary, _m("naryPr"))
    etree.SubElement(pr, _m("chr")).set(_m("val"), symbol)
    etree.SubElement(pr, _m("limLoc")).set(_m("val"), "undOvr" if symbol in "∑∏" else "subSup")
    etree.SubElement(nary, _m("sub"))
    etree.SubElement(nary, _m("sup"))
    e = etree.SubElement(nary, _m("e"))
    return nary


def mathml_to_omml(mathml: str | bytes):
    """MathML 字符串 → OMML 元素列表（`m:r` / `m:f` / `m:sSup` …）。"""
    root = etree.fromstring(mathml.encode("utf-8") if isinstance(mathml, str) else mathml)
    return _Converter().convert(root)


def latex_to_omml(latex: str) -> list:
    """LaTeX 公式 → OMML 元素列表。"""
    from latex2mathml.converter import convert as latex_to_mathml

    return mathml_to_omml(latex_to_mathml(latex))
