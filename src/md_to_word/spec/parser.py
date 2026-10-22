"""md_to_word.spec.parser — requirements.txt 格式要求语法解析器（中英双语）。

将用户声明的单行格式规范文本（中文或英文）解析为统一强类型的 TemplateSpec 对象。
具备 100% 确定性全字词法匹配，杜绝歧义与模糊推测。
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional
from docx.shared import Pt

from md_to_word.spec.constants import (
    ALIGN_MAP,
    PAGE_NUMBER_FMT,
    PAGE_SIZE_MAP,
    SIZE_MAP,
    STYLE_CN,
    STYLE_EN,
    ROW_NAME_EN,
    CURRENT_SCHEMA,
    STYLE_MAP,
    TABLE_ALIGN_MAP,
    TABLE_STYLE_MAP,
    TABLE_VALIGN_MAP,
    WRONG_KEY_HINTS,
)
from md_to_word.spec.models import MinLineSpacing, TemplateSpec

_S = "style"
_T = "table"

_INDENT_UNITS = {"字符": "chars", "字": "chars", "chars": "chars", "英寸": "pt", "in": "pt", "inch": "pt"}
_SZ_ALT = "|".join(sorted(SIZE_MAP, key=len, reverse=True))
_SIZE_PAT = rf"(?P<sz>{_SZ_ALT})|(?P<num>\d+(?:\.\d+)?)pt"
_SIZE_RE = re.compile(_SIZE_PAT, re.IGNORECASE)

_RE_DECOR_TOKEN = re.compile(r"\{([^{}]*)\}")
_RE_STYLEREF = re.compile(r"^(?:样式标题|styleref|style-title)\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)

DECOR_CONTENT_KEYS = {
    # 中文
    "页眉内容": ("header", "default"),
    "偶数页页眉内容": ("header", "even"),
    "首页页眉内容": ("header", "first"),
    "页脚内容": ("footer", "default"),
    "偶数页页脚内容": ("footer", "even"),
    "首页页脚内容": ("footer", "first"),
    # 英文
    "Header Content": ("header", "default"),
    "Even Header Content": ("header", "even"),
    "First Header Content": ("header", "first"),
    "Footer Content": ("footer", "default"),
    "Even Footer Content": ("footer", "even"),
    "First Footer Content": ("footer", "first"),
}

TABLE_WIDTH_KEYS = {
    "线宽上": "top",
    "线宽底": "bottom",
    "线宽表头下": "header_bottom",
    "线宽内": "inside",
    "border-top": "top",
    "border-bottom": "bottom",
    "border-header": "header_bottom",
    "border-inside": "inside",
}


def _set_once(props: dict, key: str, value: Any, what: str, desc: str) -> None:
    if key in props:
        if _english(desc):
            raise ValueError(f"{_label(what, True)} is declared twice ({desc.strip()})")
        raise ValueError(f"{_label(what, False)}写了两次/重复定义（{desc.strip()}）")
    props[key] = value


def _set_indent(props: dict, m: re.Match, desc: str, kind: str) -> None:
    itype = "hanging" if ("悬挂" in kind or "hanging" in kind.lower()) else "first_line"
    if "indent" in props:
        if props.get("indent_type") == itype:
            if _english(desc):
                raise ValueError(f"indent is declared twice ({desc.strip()})")
            raise ValueError(f"缩进写了两次/重复声明（{desc.strip()}）")
        if _english(desc):
            raise ValueError(
                "Only one indent kind is allowed per line, but this line declares both "
                "first-line and hanging indent: "
                + desc.strip()
                + "\n  They share the same underlying property. "
                "For an English reference list, `hanging-indent 0.5in` is enough."
            )
        raise ValueError(
            "缩进只能声明一种，但这一行同时出现了首行缩进与悬挂缩进："
            + desc.strip()
            + "\n  两者共用同一组底层属性。英文参考文献只需声明 hanging-indent 0.5in。"
        )
    unit_str = m.group("u") or "chars"
    unit = _INDENT_UNITS.get(unit_str, "pt" if ("in" in unit_str or "英寸" in unit_str) else "chars")
    mult = 72.0 if unit == "pt" else 1.0
    props["indent"] = float(m.group("v")) * mult
    props["indent_type"] = itype
    props["indent_unit"] = unit


_CLAUSE_TABLE: list[tuple[str, re.Pattern, Callable]] = [
    # ── 字号（支持中文字号与数字pt） ──
    (
        _S,
        _SIZE_RE,
        lambda p, m, d: _set_once(
            p,
            "font_size",
            SIZE_MAP[m.group("sz")] if m.group("sz") in SIZE_MAP else Pt(float(m.group("num"))),
            "字号/font_size",
            d,
        ),
    ),
    # ── 字形（加粗/倾斜） ──
    (_S, re.compile(r"加粗|bold", re.I), lambda p, m, d: _set_once(p, "bold", True, "加粗/bold", d)),
    (
        _S,
        re.compile(r"不加粗|regular|normal|not-bold", re.I),
        lambda p, m, d: _set_once(p, "bold", False, "加粗/bold", d),
    ),
    (_S, re.compile(r"倾斜|italic", re.I), lambda p, m, d: _set_once(p, "italic", True, "倾斜/italic", d)),
    (
        _S,
        re.compile(r"不倾斜|not-italic", re.I),
        lambda p, m, d: _set_once(p, "italic", False, "倾斜/italic", d),
    ),
    # ── 对齐 ──
    (
        _S,
        re.compile(r"居中|左对齐|右对齐|两端对齐|center|left|right|justify", re.I),
        lambda p, m, d: _set_once(p, "alignment", ALIGN_MAP[m.group(0).lower() if m.group(0).lower() in ALIGN_MAP else m.group(0)], "对齐/alignment", d),
    ),
    # ── 行距（唯一正典：倍数带「倍」/固定值带「磅/pt」/最小值） ──
    (
        _S,
        re.compile(r"(?:行距最小值|min-line-spacing)(?P<v>\d+(?:\.\d+)?)(?:磅|pt)?", re.I),
        lambda p, m, d: _set_once(
            p, "line_spacing", MinLineSpacing(float(m.group("v"))), "行距/line_spacing", d
        ),
    ),
    (
        _S,
        re.compile(r"(?:行距|line-spacing)(?P<v>\d+(?:\.\d+)?)磅|line-spacing(?P<v2>\d+(?:\.\d+)?)pt", re.I),
        lambda p, m, d: _set_once(p, "line_spacing", Pt(float(m.group("v") or m.group("v2"))), "行距/line_spacing", d),
    ),
    (
        _S,
        re.compile(r"行距(?P<v>\d+(?:\.\d+)?)倍|line-spacing(?P<v2>\d+(?:\.\d+)?)(?:倍)?", re.I),
        lambda p, m, d: _set_once(p, "line_spacing", float(m.group("v") or m.group("v2")), "行距/line_spacing", d),
    ),
    # ── 段前/段后 ──
    (
        _S,
        re.compile(r"(?:段前|space-before)(?P<v>\d+(?:\.\d+)?)(?:磅|pt)?", re.I),
        lambda p, m, d: _set_once(p, "space_before", Pt(float(m.group("v"))), "段前/space_before", d),
    ),
    (
        _S,
        re.compile(r"(?:段后|space-after)(?P<v>\d+(?:\.\d+)?)(?:磅|pt)?", re.I),
        lambda p, m, d: _set_once(p, "space_after", Pt(float(m.group("v"))), "段后/space_after", d),
    ),
    # ── 缩进（唯一正典：首行缩进N字符/首行缩进0 / 悬挂缩进0.5英寸 / indent Nchars / indent 0） ──
    (
        _S,
        re.compile(r"(?:首行缩进|indent)(?P<v>\d+(?:\.\d+)?)(?P<u>字符|字|英寸|in|inch|chars)?", re.I),
        lambda p, m, d: _set_indent(p, m, d, "首行缩进"),
    ),
    (
        _S,
        re.compile(r"(?:悬挂缩进|hanging-indent)(?P<v>\d+(?:\.\d+)?)(?P<u>字符|字|英寸|in|inch|chars)?", re.I),
        lambda p, m, d: _set_indent(p, m, d, "悬挂缩进"),
    ),
    (
        _S,
        re.compile(r"(?:左缩进|left-indent)(?P<v>\d+(?:\.\d+)?)(?P<u>字符|字|chars)?", re.I),
        lambda p, m, d: _set_once(p, "left_indent_chars", float(m.group("v")), "左缩进/left_indent", d),
    ),
    # ── 边框 ──
    (_S, re.compile(r"无边框|no-border", re.I), lambda p, m, d: _set_once(p, "no_border", True, "边框", d)),
    (
        _S,
        re.compile(r"(?:下边框|border-bottom-)(?P<k>单线|双线|single|double)", re.I),
        lambda p, m, d: _set_once(
            p,
            "bottom_border",
            {"单线": "single", "双线": "double", "single": "single", "double": "double"}[m.group("k").lower()],
            "边框",
            d,
        ),
    ),
    (
        _S,
        re.compile(r"(?:边框粗|border-width)(?P<v>\d+(?:\.\d+)?)(?:磅|pt)?", re.I),
        lambda p, m, d: _set_once(p, "border_width_pt", float(m.group("v")), "边框粗", d),
    ),
    (
        _S,
        re.compile(r"(?:字距|char-spacing)(?P<v>-?\d+(?:\.\d+)?)(?:磅|pt)?", re.I),
        lambda p, m, d: _set_once(p, "char_spacing_pt", float(m.group("v")), "字距", d),
    ),
    (_S, re.compile(r"点线制表位|dot-leader-tab", re.I), lambda p, m, d: _set_once(p, "dot_leader_tab", True, "点线制表位", d)),
    (_S, re.compile(r"加入目录|join-toc", re.I), lambda p, m, d: _set_once(p, "join_toc", True, "加入目录", d)),
    (_S, re.compile(r"与下段同页|keep-with-next", re.I), lambda p, m, d: _set_once(p, "keep_next", True, "与下段同页", d)),
    (_S, re.compile(r"段中不分页|keep-lines", re.I), lambda p, m, d: _set_once(p, "keep_lines", True, "段中不分页", d)),
    (_S, re.compile(r"段前分页|page-break-before", re.I), lambda p, m, d: _set_once(p, "page_break_before", True, "段前分页", d)),
    (_S, re.compile(r"取消孤行控制|no-widow-control", re.I), lambda p, m, d: _set_once(p, "widow_control", False, "孤行控制", d)),
    (_S, re.compile(r"(?<!取消)孤行控制|(?<!no-)widow-control", re.I), lambda p, m, d: _set_once(p, "widow_control", True, "孤行控制", d)),
    (_S, re.compile(r"跨页重复|repeat-header", re.I), lambda p, m, d: _set_once(p, "repeat_header", True, "跨页重复", d)),
    # ── 表格属性 ──
    (
        _T,
        re.compile(r"居中|左对齐|右对齐|center|left|right", re.I),
        lambda p, m, d: _set_once(p, "align", TABLE_ALIGN_MAP[m.group(0).lower() if m.group(0).lower() in TABLE_ALIGN_MAP else m.group(0)], "表格对齐", d),
    ),
    (
        _T,
        re.compile(r"三线表|全网格线|顶底线|无边框|three-line|grid|top-bottom|none", re.I),
        lambda p, m, d: _set_once(p, "style", TABLE_STYLE_MAP[m.group(0).lower() if m.group(0).lower() in TABLE_STYLE_MAP else m.group(0)], "表格边框样式", d),
    ),
    (
        _T,
        re.compile(r"(?:线宽(?P<k>上|底|表头下|内)|border-(?P<ek>top|bottom|header|inside))(?P<v>\d+(?:\.\d+)?)(?:磅|pt)?", re.I),
        lambda p, m, d: p.setdefault("widths", {}).__setitem__(
            TABLE_WIDTH_KEYS["border-" + m.group("ek").lower()] if m.group("ek") else TABLE_WIDTH_KEYS["线宽" + m.group("k")],
            float(m.group("v")),
        ),
    ),
    (
        _T,
        re.compile(r"(?:单元格垂直(?P<k>居中|顶端|底端)|valign-(?P<ek>center|top|bottom))", re.I),
        lambda p, m, d: _set_once(
            p, "valign", TABLE_VALIGN_MAP[m.group("ek").lower() if m.group("ek") else m.group("k")], "单元格垂直对齐", d
        ),
    ),
    (
        _T,
        re.compile(r"(?:单元格内边距|cell-margin)(?P<v>\d+(?:\.\d+)?)cm", re.I),
        lambda p, m, d: _set_once(p, "cell_margin_cm", float(m.group("v")), "单元格内边距", d),
    ),
]

def _english(desc: str) -> bool:
    """错误文案跟随输入语言：这一行没有中日韩字符，就说英文。"""
    return not re.search(r"[\u4e00-\u9fff]", desc or "")


def _who(name: str, english: bool) -> str:
    """样式名按用户的语言回显：中文源回中文名，英文源回英文名。"""
    if english:
        return STYLE_EN.get(name, ROW_NAME_EN.get(name, name))
    return STYLE_CN.get(name, name)


def _label(what: str, english: bool) -> str:
    """`字号/font_size` 这种双语标签按语言取一半；只有一侧时原样返回。"""
    if "/" not in what:
        return what
    zh, _, en = what.partition("/")
    return en.strip() if english else zh.strip()


# (匹配模式, 中文提示, 英文提示)——英文为 None 表示该写法只可能出现在中文输入里
_HINTS = [
    # ── 行距纠偏（引导到唯一正典：行距N倍 / 行距N磅）──
    (re.compile(r"^行距\d+(?:\.\d+)?$"), "行距必须带单位「倍」或「磅」（如 行距1.5倍、行距20磅，英文：line-spacing 1.5 / line-spacing 20pt）", None),
    (re.compile(r"固定值|固定行距|fixed-line-spacing"), "固定磅值行距请统一写「行距N磅」（如 行距20磅，英文：line-spacing 20pt）", "Write a fixed line height as `line-spacing 20pt`."),
    (re.compile(r"^\d+(?:\.\d+)?倍(?:行距)?$"), "行距倍数请统一写「行距N倍」（如 行距1.5倍，英文：line-spacing 1.5）", None),
    (re.compile(r"^(?:单倍|双倍)(?:行距)?$"), "行距倍数请统一写「行距1.0倍」或「行距2.0倍」（英文：line-spacing 1.0）", None),
    (re.compile(r"最小行距|line-spacing-min"), "行距最小值请统一写「行距最小值N磅」（英文：min-line-spacing N pt）", "Write a minimum line height as `min-line-spacing 25pt`."),
    (re.compile(r"行间距"), "行距请统一写「行距N倍」或「行距N磅」（英文：line-spacing N）", None),
    # ── 缩进纠偏（引导到唯一正典：首行缩进N字符 / 首行缩进0）──
    (re.compile(r"^(?:无缩进|不缩进|no-indent)$"), "免缩进请统一写「首行缩进0」（英文：indent 0）", "Write no indent as `indent 0`."),
    (re.compile(r"^缩进\d"), "首行缩进请统一写「首行缩进N字符」（如 首行缩进2字符，英文：indent 2chars）", None),
    # ── 字号纠偏 ──
    (re.compile(r"^\d+(?:\.\d+)?磅$"), "数值字号必须带单位 pt（如 12pt）；「磅」仅用于行距/段前/段后/线宽", None),
    (re.compile(r"^\d+(?:\.\d+)?$"), "数值字号必须带单位 pt（如 12pt、10.5pt）或使用中文字号（如 小四、五号）", "A bare number is ambiguous: write a font size such as `12pt`."),
    # ── 字形与边框纠偏 ──
    (re.compile(r"斜体"), "字体倾斜请写「倾斜」（英文：italic）", None),
    (re.compile(r"下划线"), "下边框请写「下边框单线」（Word 字符级下划线不受模板样式控制）", None),
    # ── 英文否定式：正典写法是 not-bold / not-italic，中间必须带连字符 ──
    (re.compile(r"^(?:not|no)$", re.I), None,
     "To cancel a style, write `not-bold` or `not-italic` (with a hyphen)."),
    (re.compile(r"^(?:notbold|notitalic|notbolditalic)$", re.I), None,
     "Write `not-bold` / `not-italic` (hyphenated)."),
]


def _unknown_word_msg(word: str, name: str, desc: str, lineno: Optional[int]) -> str:
    english = _english(desc)
    where = (f"Line {lineno}: " if english else f"第 {lineno} 行 ") if lineno else ""
    hints = [en if english else zh for pat, zh, en in _HINTS if pat.search(word)]
    hint = hints[0] if hints else ""
    if english:
        tail = f"\n  {hint}" if hint else ""
        return (
            f"{where}{_who(name, True)}: unknown property word `{word}`.{tail}\n"
            f"  Properties use the canonical English (or Chinese) spelling, separated by spaces.\n"
            f"  Line: {desc.strip()}"
        )
    hint = f"（是不是想写 {hint}？）" if hint else ""
    return (
        f"{where}{_who(name, False)}: 不认识属性词「{word}」{hint}\n"
        f"  属性须按中/英标准写法书写，词间用空格分隔。\n"
        f"  原文：{desc.strip()}"
    )


# 组合词前缀（中英文中把参数用空格分立时，如 `line-spacing 1.5`、`行距 1.5倍`、`indent 0`）
_COMPOUND_PREFIXES = {
    # 英文
    "line-spacing",
    "min-line-spacing",
    "space-before",
    "space-after",
    "indent",
    "hanging-indent",
    "left-indent",
    "border-top",
    "border-bottom",
    "border-header",
    "border-inside",
    "border-width",
    "valign",
    "cell-margin",
    "char-spacing",
    "table-align",
    # 中文（仅支持正典前缀后带空格的规整分离）
    "行距",
    "行距最小值",
    "段前",
    "段后",
    "首行缩进",
    "悬挂缩进",
    "左缩进",
    "线宽上",
    "线宽底",
    "线宽表头下",
    "线宽内",
    "边框粗",
    "字距",
    "表格对齐",
    "单元格垂直",
    "单元格内边距",
}


def _normalize_tokens(raw_words: list[str]) -> list[str]:
    """将属性词及其紧随的参数（如 ['line-spacing', '1.5']、['行距', '1.5倍']）归一化为单一 token。"""
    normalized: list[str] = []
    i = 0
    n = len(raw_words)
    while i < n:
        w = raw_words[i]
        w_lower = w.lower()
        if w_lower in _COMPOUND_PREFIXES and i + 1 < n:
            next_w = raw_words[i + 1]
            if w_lower == "valign":
                normalized.append(f"valign-{next_w}")
            elif w_lower in ("table-align", "表格对齐"):
                normalized.append(f"table-align-{next_w}")
            else:
                normalized.append(f"{w_lower}{next_w}")
            i += 2
            continue
        normalized.append(w)
        i += 1
    return normalized


def _consume(props: dict, words: list[str], mode: str, name: str, desc: str, lineno: Optional[int]) -> None:
    tokens = _normalize_tokens(words)
    for token in tokens:
        hit = False
        for m_mode, pat, action in _CLAUSE_TABLE:
            if m_mode != mode:
                continue
            m = pat.fullmatch(token)
            if m:
                action(props, m, desc)
                hit = True
                break
        if not hit:
            raise ValueError(_unknown_word_msg(token, name, desc, lineno))


_CLAUSE_WORD_HINT = re.compile(
    r"行距|段前|段后|缩进|加粗|倾斜|对齐|居中|边框|制表位|加入目录|与下段同页|跨页重复|段中不分页|段前分页|孤行控制"
    r"|line-spacing|space-before|space-after|indent|bold|regular|italic|left|right|center|justify|repeat-header|keep-with-next",
    re.I,
)


def parse_font_name(text: str) -> Optional[list[str]]:
    from md_to_word.spec.constants import CJK_FONTS, LATIN_FONTS

    parts = re.split(r"[/／]", text)
    cjk = None
    latin = None

    for part in parts:
        p = part.strip()
        if not p:
            continue
        known_match = None
        for known in sorted(CJK_FONTS | LATIN_FONTS, key=len, reverse=True):
            if re.search(r"\b" + re.escape(known) + r"\b", p, re.I):
                known_match = known
                break

        if known_match:
            if known_match in CJK_FONTS:
                cjk = known_match
            else:
                latin = known_match
        else:
            candidate = re.split(r"[,，]", p)[0].strip()
            if (
                candidate
                and not re.match(r"^\d", candidate)
                and re.search(r"[^\W\d_]|[\u4e00-\u9fff]", candidate)
            ):
                if re.search(r"[\u4e00-\u9fff]", candidate) or re.search(r"\b(?:SC|TC|CJK|Song|Hei|Kai|FangSong|Han)\b", candidate, re.I):
                    cjk = candidate
                else:
                    latin = candidate

    result = []
    if cjk:
        result.append(cjk)
    if latin:
        result.append(latin)
    return result if result else None


def _consumable_word(word: str) -> bool:
    w_clean = word.lower()
    if w_clean in _COMPOUND_PREFIXES:
        return True
    return any(m_mode == _S and pat.fullmatch(word) for m_mode, pat, _ in _CLAUSE_TABLE)


def _split_font(
    words: list[str], name: str, desc: str, lineno: Optional[int]
) -> tuple[list[str], list[str]]:
    size_i = next((i for i, w in enumerate(words) if _SIZE_RE.fullmatch(w)), None)
    if size_i is None:
        size_i = next((i for i, w in enumerate(words) if _consumable_word(w)), len(words))
    font_words = words[:size_i]
    for w in font_words:
        if re.match(r"^\d+(?:\.\d+)?$", w):
            raise ValueError(_unknown_word_msg(w, name, desc, lineno))
        if any(pat.search(w) for pat, _zh, _en in _HINTS):
            raise ValueError(_unknown_word_msg(w, name, desc, lineno))
    font_text = " ".join(font_words)
    if font_words and (_CLAUSE_WORD_HINT.search(font_text) or _SIZE_RE.search(font_text)):
        if _english(desc):
            raise ValueError(
                f"{_who(name, True)}: the font segment `{font_text}` contains a property word.\n"
                f"  Separate the font name from the size and properties with a space "
                f"(e.g. `Times New Roman 12pt ...`).\n"
                f"  Line: {desc.strip()}"
            )
        raise ValueError(
            f"{_who(name, False)}: 字体段「{font_text}」里混进了属性词。\n"
            f"  字体与后面的字号/属性之间必须留空格（如 `Times New Roman 12pt …`）。\n"
            f"  原文：{desc.strip()}"
        )
    font = parse_font_name(font_text)
    if font_words and not font:
        raise ValueError(_unknown_word_msg(font_words[0], name, desc, lineno))
    return font or [], words[size_i:]


_TOC_INELIGIBLE = {
    "Body Text": "正文",
    "First Paragraph": "首段",
    "Normal": "普通",
    "Compact": "紧凑",
}


def _check_clause_preconditions(props: dict, style_name: str, desc: str, lineno: Optional[int]) -> None:
    english = _english(desc)
    where = (f"Line {lineno}: " if english else f"第 {lineno} 行 ") if lineno else ""
    who = _who(style_name, english)
    tail = f"\n  Line: {desc.strip()}" if english else f"\n  原文：{desc.strip()}"

    if "border_width_pt" in props and props.get("bottom_border") not in ("single", "double"):
        raise ValueError(
            f"{where}{who}: `border-width` is set, but no single or double bottom border was declared.{tail}"
            if english
            else f"{where}{who}: 写了「边框粗 / border-width」，却没声明下边框为单线或双线。{tail}"
        )

    if props.get("repeat_header") and style_name not in ("表头", "Table Header"):
        raise ValueError(
            f"{where}{who}: `repeat-header` only applies to the table header row.{tail}"
            if english
            else f"{where}{who}: 「跨页重复 / repeat-header」只能写在表头行。{tail}"
        )

    if props.get("join_toc") and style_name in _TOC_INELIGIBLE:
        raise ValueError(
            f"{where}{who}: `join-toc` only applies to heading styles.{tail}"
            if english
            else f"{where}{who}: 「加入目录 / join-toc」只能写在标题类样式上。{tail}"
        )


def parse_style_props(style_name: str, desc: str, lineno: Optional[int] = None) -> dict[str, Any]:
    words = desc.split()
    props: dict[str, Any] = {"style_name": style_name}
    font_names, rest = _split_font(words, style_name, desc, lineno)
    if font_names:
        props["font_name"] = font_names
    _consume(props, rest, _S, style_name, desc, lineno)
    _check_clause_preconditions(props, style_name, desc, lineno)
    return props


def parse_table_props(desc: str, lineno: Optional[int] = None) -> dict[str, Any]:
    table: dict[str, Any] = {}
    _consume(table, desc.split(), _T, "表格", desc, lineno)
    return table


def decor_token_to_field(tok: str) -> Optional[str]:
    tok_clean = tok.strip().lower()
    if tok_clean in ("页码", "page"):
        return "PAGE   \\* MERGEFORMAT "
    if tok_clean in ("总页数", "numpages", "total-pages"):
        return "NUMPAGES   \\* MERGEFORMAT "
    m = _RE_STYLEREF.match(tok.strip())
    if m:
        return 'STYLEREF  "%s"   \\* MERGEFORMAT ' % m.group(1)
    return None


def parse_decor_content(text: str, lineno: Optional[int] = None, key: Optional[str] = None) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    pos = 0
    for m in _RE_DECOR_TOKEN.finditer(text):
        if m.start() > pos:
            parts.append(("text", text[pos : m.start()]))
        tok = m.group(1).strip()
        instr = decor_token_to_field(tok)
        if instr is None:
            where = f"第 {lineno} 行" if lineno else ""
            whose = f"「{key}」" if key else ""
            raise ValueError(
                f"{where}{whose} 未知的页眉/页脚域标记 \"{{{tok}}}\"；"
                f"可用：{{页码}}/{{page}}, {{总页数}}/{{total-pages}}, {{样式标题:<样式名>}}"
            )
        parts.append(("field", instr))
        pos = m.end()
    if pos < len(text):
        parts.append(("text", text[pos:]))
    return parts


def parse_page_number(desc: str, lineno: Optional[int] = None) -> tuple[str, int]:
    tokens = desc.split()
    if not (1 <= len(tokens) <= 3) or tokens[0] not in PAGE_NUMBER_FMT:
        valid = " ".join(PAGE_NUMBER_FMT.keys())
        raise ValueError(
            f"第 {lineno} 行「页码/Page Number」格式不认识：{desc}\n  应写：页码：<格式> [起始<N>]；可用格式：{valid}"
        )
    fmt = PAGE_NUMBER_FMT[tokens[0]]
    start = 1
    # 支持 起始1 或 start 1
    if len(tokens) == 2:
        m = re.fullmatch(r"(?:起始|start)(\d+)", tokens[1], re.I)
        if m:
            start = int(m.group(1))
    elif len(tokens) == 3 and tokens[1].lower() == "start":
        start = int(tokens[2])
    return fmt, start


def parse_margins(desc: str, lineno: Optional[int] = None) -> dict[str, float]:
    margins: dict[str, float] = {}
    tokens = desc.split()
    # 支持组合成 ['top', '2.54cm', 'bottom', '2.54cm'] 或 ['上2.54cm', '下2.54cm']
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # 英文分开写法: top 2.54cm
        if tok.lower() in ("top", "bottom", "left", "right") and i + 1 < len(tokens):
            val_m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:cm)?", tokens[i + 1])
            if val_m:
                margins[tok.lower()] = float(val_m.group(1))
                i += 2
                continue
        # 中文紧凑写法: 上2.54cm
        m = re.fullmatch(r"(上|下|左|右|top|bottom|left|right)(\d+(?:\.\d+)?)cm", tok, re.I)
        if m:
            k = m.group(1).lower()
            k = {"上": "top", "下": "bottom", "左": "left", "右": "right"}.get(k, k)
            margins[k] = float(m.group(2))
            i += 1
            continue
        raise ValueError(f"第 {lineno} 行页边距项不认识：{tok}")
    if len(margins) != 4:
        raise ValueError(f"第 {lineno} 行页边距必须包含上/下/左/右（top/bottom/left/right）四项：{desc}")
    return margins


def _bad_value(lineno: Optional[int], key: str, desc: str, should: str, why: str = "") -> ValueError:
    if _english(desc):
        return ValueError(
            f"Line {lineno}: unrecognised value for `{key}`: {desc}"
            + (f"\n  {why}" if why else "")
            + f"\n  Expected: {key}: {should}"
        )
    return ValueError(
        f"第 {lineno} 行「{key}」的值不认识：{desc}"
        + (f"\n  {why}" if why else "")
        + f"\n  应写：{key}：{should}"
    )


def _line_margins(spec: TemplateSpec, desc: str, lineno: int) -> None:
    spec.margins = parse_margins(desc, lineno)


def _line_paper(spec: TemplateSpec, desc: str, lineno: int) -> None:
    if desc not in PAGE_SIZE_MAP:
        raise _bad_value(lineno, "纸张/Paper", desc, "A4|Letter")
    spec.page_size = PAGE_SIZE_MAP[desc]


def _line_proofing_lang(spec: TemplateSpec, desc: str, lineno: int) -> None:
    if not re.fullmatch(r"[A-Za-z]{2}(?:-[A-Za-z]{2,4})?", desc):
        raise _bad_value(lineno, "校对语言/Language", desc, "zh-CN / en-US")
    spec.proofing_lang = desc


def _line_distance(field_name: str, key: str) -> Callable[[TemplateSpec, str, int], None]:
    def handler(spec: TemplateSpec, desc: str, lineno: int) -> None:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)cm", desc)
        if not m:
            raise _bad_value(lineno, key, desc, "1.4cm")
        setattr(spec, field_name, float(m.group(1)))

    return handler


def _line_gutter(spec: TemplateSpec, desc: str, lineno: int) -> None:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)cm", desc)
    if not m:
        raise _bad_value(lineno, "装订线/Gutter", desc, "1cm")
    spec.gutter_cm = float(m.group(1))


def _line_doc_grid(spec: TemplateSpec, desc: str, lineno: int) -> None:
    m = re.fullmatch(r"(?:每页(\d+)行|(\d+)\s*lines)", desc, re.I)
    if not m:
        raise _bad_value(lineno, "文档网格/Document Grid", desc, "每页22行 (22 lines)")
    n = int(m.group(1) or m.group(2))
    if not 1 <= n <= 200:
        raise _bad_value(lineno, "文档网格/Document Grid", desc, "每页22行 (22 lines)", why="行数要在 1–200 之间 / line count must be 1–200")
    spec.doc_grid_lines = n


def _line_equation_number(spec: TemplateSpec, desc: str, lineno: int) -> None:
    """公式编号放在哪：`右侧`（默认，靠版心右边）或 `紧跟`（公式后面）。"""
    value = {"右侧": "right", "右对齐": "right", "right": "right",
             "紧跟": "inline", "紧随": "inline", "inline": "inline"}.get(desc.strip().lower())
    if value is None:
        raise _bad_value(lineno, "公式编号/Equation Number", desc,
                         "右侧 (right) 或 紧跟 (inline)",
                         why="右侧=编号靠版心右边；紧跟=编号直接跟在公式后面")
    spec.equation_number = value


_EQ_FORMAT_KNOWN = ("{c}", "{n}")


def _line_equation_format(spec: TemplateSpec, desc: str, lineno: int) -> None:
    """编号长什么样：`（{c}-{n}）`。

    `{n}` 是序号（必写），`{c}` 是章号（可选，要求稿件开了 `crossref.chapters`）。
    括号、分隔符、中间的空格都写在这行里——不枚举"全角括号""短横线"这些变体，
    一种写法就是一层组合爆炸，而模板能一字不差地表达用户要的样子。
    """
    value = desc.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if value.count("{") != value.count("}"):
        raise _bad_value(lineno, "公式编号格式/Equation Number Format", desc,
                         "（{c}-{n}）", why="花括号要成对：{n} 是序号，{c} 是章号")
    found = set(re.findall(r"\{[^{}]*\}", value))
    unknown = found - set(_EQ_FORMAT_KNOWN)
    if unknown:
        raise _bad_value(lineno, "公式编号格式/Equation Number Format", desc,
                         "（{c}-{n}）",
                         why=f"只认 {{n}}（序号）与 {{c}}（章号），认不出 {'、'.join(sorted(unknown))}")
    if "{n}" not in found:
        raise _bad_value(lineno, "公式编号格式/Equation Number Format", desc,
                         "（{n}）", why="必须包含 {n}——它是编号里的序号")
    spec.equation_number_format = value


def _line_decor(container: str, key: str) -> Callable[[TemplateSpec, str, int], None]:
    def handler(spec: TemplateSpec, desc: str, lineno: int) -> None:
        spec.decor[DECOR_CONTENT_KEYS[key]] = (
            [] if desc in ("无", "none", "None") else parse_decor_content(desc, lineno, key)
        )

    return handler


_LINE_KEYS: dict[str, Callable[[TemplateSpec, str, int], None]] = {
    # 中文
    "西文字体": lambda s, d, l: setattr(s, "default_latin", d),
    "页边距": _line_margins,
    "校对语言": _line_proofing_lang,
    "页眉距边界": _line_distance("header_distance", "页眉距边界"),
    "页脚距边界": _line_distance("footer_distance", "页脚距边界"),
    "纸张": _line_paper,
    "装订线": _line_gutter,
    "文档网格": _line_doc_grid,
    "公式编号": _line_equation_number,
    "公式编号格式": _line_equation_format,
    "页码": lambda s, d, l: setattr(s, "page_number", parse_page_number(d, l)),
    "表格": lambda s, d, l: setattr(s, "table", parse_table_props(d, l)),
    "表头": lambda s, d, l: setattr(s, "table_header", parse_style_props("表头", d, l)),
    # 英文
    "Font": lambda s, d, l: setattr(s, "default_latin", d),
    "Latin Font": lambda s, d, l: setattr(s, "default_latin", d),
    "Margins": _line_margins,
    "Proofing Language": _line_proofing_lang,
    "Language": _line_proofing_lang,
    "Header Distance": _line_distance("header_distance", "Header Distance"),
    "Footer Distance": _line_distance("footer_distance", "Footer Distance"),
    "Paper": _line_paper,
    "Paper Size": _line_paper,
    "Gutter": _line_gutter,
    "Document Grid": _line_doc_grid,
    "Equation Number": _line_equation_number,
    "Equation Number Format": _line_equation_format,
    "Page Number": lambda s, d, l: setattr(s, "page_number", parse_page_number(d, l)),
    "Table": lambda s, d, l: setattr(s, "table", parse_table_props(d, l)),
    "Table Header": lambda s, d, l: setattr(s, "table_header", parse_style_props("表头", d, l)),
    **{key: _line_decor(container, key) for key, container in DECOR_CONTENT_KEYS.items()},
}


_SCHEMA_RE = re.compile(r"^#\s*schema\s*:\s*(\d+)\s*$", re.I)


def _read_schema_version(text: str) -> int:
    """文件头的 `# schema: N`；没写就是 1（既有文件都没写）。"""
    for line in (text or "").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("#"):
            break
        m = _SCHEMA_RE.match(stripped)
        if m:
            return int(m.group(1))
    return CURRENT_SCHEMA


def parse_requirements(text: str) -> TemplateSpec:
    """解析格式要求文本（中英双语） → TemplateSpec。"""
    schema = _read_schema_version(text)
    if schema > CURRENT_SCHEMA:
        raise ValueError(
            f"这份格式要求文件声明了 `# schema: {schema}`，本版本只支持到 {CURRENT_SCHEMA}。\n"
            f"  请升级 md-to-word（或删掉该声明，按 schema {CURRENT_SCHEMA} 的写法核对一遍）。"
        )

    spec = TemplateSpec(schema_version=schema)
    seen_keys: dict[str, int] = {}

    for lineno, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split("：", 1) if "：" in line else line.split(":", 1)
        if len(parts) != 2:
            raise ValueError(
                f"第 {lineno} 行缺少冒号，无法解析：{line!r}\n"
                f"  每行须写成「Key: Value」或「键名：属性值」（冒号支持 : 或 ：）。"
            )

        key = parts[0].strip()
        desc = parts[1].strip()
        if not desc:
            raise ValueError(
                f"第 {lineno} 行的「{key}」没有提供参数值：{line!r}\n"
                f"  如需设置为空容器请填写「无」或「none」。"
            )

        handler = _LINE_KEYS.get(key)
        if handler is not None:
            if key in seen_keys:
                raise ValueError(
                    f"第 {lineno} 行「{key}」重复定义（前一次在第 {seen_keys[key]} 行）：{line}"
                )
            seen_keys[key] = lineno
            handler(spec, desc, lineno)
            continue

        if key not in STYLE_MAP:
            hint = f"（提示：{WRONG_KEY_HINTS[key]}）" if key in WRONG_KEY_HINTS else ""
            valid_styles = "、".join(list(STYLE_MAP.keys())[:15]) + "..."
            raise ValueError(
                f"第 {lineno} 行不认识的键名「{key}」{hint}：{line}\n"
                f"  可填样式名例如：{valid_styles}"
            )

        style_name = STYLE_MAP[key]
        if style_name in seen_keys:
            raise ValueError(
                f"第 {lineno} 行「{key}」重复定义（前一次在第 {seen_keys[style_name]} 行）：{line}"
            )
        seen_keys[style_name] = lineno
        spec.styles.append(parse_style_props(style_name, desc, lineno))

    return spec
