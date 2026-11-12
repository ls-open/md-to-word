"""md_to_word.transform.bibtex — .bib → CSL-JSON。

为什么要自己转：CSL 处理器（citeproc-py）要的是 CSL-JSON，而 BibTeX 到 CSL-JSON 的
映射没有标准实现可用——自带的 BibTeX 读取器不产出 `issued`（只认裸 year）也不认
`journaltitle`，喂给任何 CSL 样式都会抛 VariableError（实测）。这段映射只有百来行，
自己写反而可控。

只覆盖学术写作里真会用到的字段；认不出的字段丢弃而不是报错——文献库常常是作者从
各期刊网站导出的，字段五花八门，为此失败不划算。
"""

from __future__ import annotations

import re
import unicodedata

from md_to_word.utils.typography import smart_quotes

_TYPE_MAP = {
    "article": "article-journal",
    "periodical": "article-journal",
    "book": "book",
    "mvbook": "book",
    "booklet": "pamphlet",
    "inbook": "chapter",
    "incollection": "chapter",
    "collection": "book",
    "mvcollection": "book",
    "inproceedings": "paper-conference",
    "conference": "paper-conference",
    "manual": "book",
    "mastersthesis": "thesis",
    "phdthesis": "thesis",
    "thesis": "thesis",
    "proceedings": "book",
    "techreport": "report",
    "report": "report",
    "unpublished": "manuscript",
    "misc": "article",
    "online": "webpage",
    "electronic": "webpage",
    "www": "webpage",
    "dataset": "dataset",
    "software": "software",
    "patent": "patent",
    "standard": "standard",
}

_PERIODICAL_TYPES = {
    "article-journal",
    "article-magazine",
    "article-newspaper",
    "periodical",
}

_VERBATIM_FIELDS = {
    "url",
    "doi",
    "eprint",
    "archiveprefix",
    "urldate",
    "date",
    "crossref",
    "number",
    "version",
    "isbn",
    "issn",
    "volume",
    "issue",
    "eprinttype",
}

# 只承载字段、本身不是文献的条目类型：`@set`/`@xdata` 是 biblatex 的组合与复用构造，
# 当成条目收下会得到没有题名作者的幽灵条目（被引用时渲染成空白）。
_SKIP_KINDS = {"comment", "string", "preamble", "set", "xdata"}

# `type` 字段能当 `genre`（文献类型描述）用的条目类型。
# 期刊条目的 `type` 是数据字段（DBLP 写 `Journal Articles`、CNKI 写 `硕士`），
# 无条件映射会把它当描述语印进成稿。
_GENRE_TYPES = {"report", "thesis", "patent", "manuscript"}

# BibTeX 标准允许 `{}` 与 `()` 两种定界符；只认前者会把整份括号式文献库静默吞掉。
_ENTRY_HEAD_RE = re.compile(r"@(?P<kind>\w+)\s*(?P<open>[{(])\s*(?P<key>[^,\s]+)\s*,", re.S)
_FIELD_NAME_RE = re.compile(r"(\w+)\s*=\s*", re.S)


def _read_field_value(body: str, start: int) -> tuple[str, int]:
    r"""从 `=` 之后读一个字段值，返回 (值, 下一个位置)。

    必须按**配对括号**读，不能用非贪婪正则：中文名常写成 `{{王伟伟} and {顾炎辉}}`，
    `\{.*?\}` 只会吃到第一个 `}`，作者就只剩第一位——一条文献丢三位作者，且不报错。
    """
    i, n = start, len(body)
    while i < n and body[i] in " \t\n\r":
        i += 1
    if i >= n:
        return "", i
    opener = body[i]
    closer = {"{": "}", "(": ")", '"': '"'}.get(opener)
    if closer is None:  # 裸值：数字或宏名
        j = i
        # `#` 也要断：`journal = jstat # " (Online)"` 里前半是宏名、后半是字符串，
        # 不停在这里就会整段当一个值，拼接分支永远轮不到
        while j < n and body[j] not in ",\n}#":
            j += 1
        return body[i:j].strip(), j
    if opener == closer:
        # 引号包裹的值没有嵌套：找到下一个同样的引号就结束。走下面的配对逻辑，
        # 开符与闭符是同一个字符，每遇到一个都算"加深"，值会一路吞到条目末尾。
        j = i + 1
        while j < n:
            if body[j] == "\\":
                j += 2
                continue
            if body[j] == closer:
                return body[i : j + 1], j + 1
            j += 1
        return body[i:], n

    depth, j = 0, i
    while j < n:
        ch = body[j]
        if ch == "\\":  # 转义字符（\{ \}）原样跳过
            j += 2
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return body[i : j + 1], j + 1
        j += 1
    return body[i:], n


def _parse_strings(text: str) -> dict[str, str]:
    """`@string{acm = "ACM Press"}` → {acm: ACM Press}。

    BibTeX 允许把出版社、期刊名定义成宏，字段里裸写宏名。不展开的话成稿里会印出
    `acm` 这个标识符——实测过。
    """
    macros: dict[str, str] = {}
    for match in re.finditer(r"@string", text, re.I):
        start = text.find("{", match.end())
        if start == -1:
            continue
        depth, end = 0, start
        while end < len(text):
            ch = text[end]
            if ch == "\\":
                end += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            end += 1
        for name, value in _parse_fields(text[start + 1 : end]).items():
            if not name.startswith("raw:"):
                macros[name] = value
    return macros


def _strip_delims(text: str) -> str:
    """去掉字段值最外层的一对引号或花括号（拼接时逐段去，不能整串去）。"""
    if text[:1] in '{(\"' and text[-1:] in '})\"':
        return text[1:-1]
    return text


def _expand(value: str, macros) -> str:
    """字段值里裸写的宏名（`publisher = acm`）展开成宏的正文。"""
    bare = value.strip().lower()
    return macros[bare] if macros and value[:1] not in '{(\"' and bare in macros else value


def _strip_percent_comments(body: str) -> str:
    """删掉字段值之外的 `%` 注释（从 `%` 到行尾）。

    BibTeX 本身不认 `%`（那是 LaTeX 的注释符），但 biber 与人手写文件普遍这么用。
    不删的话注释掉的 `% author = {X}` 会变成真作者——静默改写作者比忽略注释危险得多。
    只处理**不在花括号、也不在引号里**的 `%`：`title = {50% off}`、
    `url = "http://x/100%20"` 这类值里的百分号原样保留。
    """
    out: list[str] = []
    depth = 0
    in_quotes = False
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "\\":
            out.append(body[i : i + 2])
            i += 2
            continue
        if ch == '"' and depth == 0:
            in_quotes = not in_quotes
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == "%" and depth == 0 and not in_quotes:
            while i < n and body[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_fields(body: str, macros: dict[str, str] | None = None) -> dict:
    body = _strip_percent_comments(body)
    fields: dict[str, str] = {}
    pos = 0
    while pos < len(body):
        m = _FIELD_NAME_RE.search(body, pos)
        if not m:
            break
        value, pos = _read_field_value(body, m.end())
        parts = [_expand(value, macros)]
        # BibTeX 的 `#` 是字符串拼接：`publisher = "ACM" # " Press"`。不认它，后面的
        # `# " Press", year = …` 会被当成同一个值吞进去，整条条目跟着坏掉。
        while True:
            ahead = pos
            while ahead < len(body) and body[ahead] in " \t\n\r":
                ahead += 1
            if ahead >= len(body) or body[ahead] != "#":
                break
            extra, pos = _read_field_value(body, ahead + 1)
            parts.append(_expand(extra, macros))
        if any(parts):
            name = m.group(1).lower()
            # 原始值剥离最外层字段分隔符但保留内部花括号（供作者/organisational protection 与 \url{} 解析）
            raw_joined = "".join(_strip_delims(p) for p in parts)
            fields[f"raw:{name}"] = raw_joined
            fields[name] = (
                _clean_verbatim(raw_joined) if name in _VERBATIM_FIELDS else _clean(raw_joined)
            )
        # 跳过字段间的逗号
        while pos < len(body) and body[pos] in " ,\t\n\r":
            pos += 1
    return fields



# LaTeX 转义还原：`\&` 出 `&`。不做这层，文献里会原样印出 `McKinsey \& Company`。
# 只收学术文献里真会出现的几个，认不出的原样保留——宁可多一个反斜杠，不可吞字。
_LATEX_ESCAPES = {
    "&": "&", "%": "%", "$": "$", "#": "#", "_": "_", "{": "{", "}": "}",
    "textasciitilde": "~", "textless": "<", "textgreater": ">",
    "textbackslash": "\\", "textendash": "\u2013", "textemdash": "\u2014",
}
_ESCAPE_SEQ_RE = re.compile(r"\\([&%$#_{}]|text[a-z]+)")


# BibTeX 用「重音命令 + 字母」写带音标的字母：`{\^o}`、`\"u`、`{\v r}`。
# 组合用字符经 NFC 合成单个预组合字符，作者名才不会印成 `T\^O` 这种字面量。
_ACCENTS = {
    "^": "\u0302", '"': "\u0308", "'": "\u0301", "`": "\u0300", "~": "\u0303",
    "=": "\u0304", ".": "\u0307", "u": "\u0306", "v": "\u030c", "H": "\u030b",
    "c": "\u0327", "k": "\u0328", "r": "\u030a",
}
_ACCENT_LETTERS = {
    "O": "\u00d8", "o": "\u00f8", "aa": "\u00e5", "AA": "\u00c5",
    "ss": "\u00df", "ae": "\u00e6", "AE": "\u00c6", "oe": "\u0153", "OE": "\u0152",
    "l": "\u0142", "L": "\u0141", "i": "\u0131", "j": "\u0237",
}
_SYM_ACCENT_CMD = "".join(re.escape(c) for c in "^\"'`~=.")
_ALPHA_ACCENT_CMD = "uvHckr"
_ACCENT_RE = re.compile(
    rf"\\(?:"
    rf"(?P<scmd>[{_SYM_ACCENT_CMD}])(?:\s*\{{\s*(?P<sarg1>\\[ij]|\w)\s*\}}|\s*(?P<sarg2>\\[ij](?![a-zA-Z])|\w))"
    rf"|"
    rf"(?P<acmd>[{_ALPHA_ACCENT_CMD}])(?:\s*\{{\s*(?P<aarg1>\\[ij]|\w)\s*\}}|\s+(?P<aarg2>\\[ij](?![a-zA-Z])|\w))"
    rf")"
)


def _decode_accents(value: str) -> str:
    def accent(m: re.Match) -> str:
        cmd = m.group("scmd") or m.group("acmd")
        arg = m.group("sarg1") or m.group("sarg2") or m.group("aarg1") or m.group("aarg2")
        if arg in ("\\i", "\\j"):
            arg = arg[1]
        return unicodedata.normalize("NFC", arg + _ACCENTS[cmd])

    # 兼容 `{\v r}` / `\v{r}` / `\"{u}` / `\'{\i}` / `\"u` 多种 BibTeX 重音写法
    value = _ACCENT_RE.sub(accent, value)
    value = re.sub(r"\\(O|o|aa|AA|ss|ae|AE|oe|OE|l|L|i|j)\b",
                   lambda m: _ACCENT_LETTERS[m.group(1)], value)
    return value


def _unescape(value: str) -> str:
    def repl(m: re.Match) -> str:
        return _LATEX_ESCAPES.get(m.group(1), m.group(0))

    return _ESCAPE_SEQ_RE.sub(repl, value)


def _clean_verbatim(value: str) -> str:
    """技术类原文段清洗（URL / DOI / 日期 / eprint）：保留 -- / --- / ~ / 直引号等原样字符。

    但 LaTeX 的转义字符必须还原：`doi = {10.1007/3-540-48749-2\\_2}` 里的下划线是**转义**，
    原样留着会让成稿印出反斜杠、DOI 超链接也打不开（DBLP 导出的真实数据里成规模存在）。
    只还原 `\\_ \\% \\& \\# \\$` 这五个，其余（`--`、`~`、`\\url{}`）按技术字段原样保留。
    """
    value = value.strip()
    if value[:1] in "{(\"" and value[-1:] in "})\"":
        value = value[1:-1].strip()
    m = re.fullmatch(r"\\url\s*\{(.*)\}", value, re.S)
    if m:
        value = m.group(1)
    value = re.sub(r"\\([_%&#$])", r"\1", value)
    return re.sub(r"\s+", " ", value).strip()


# 文本字段里的 LaTeX 排版命令。花括号在这一步之后才删，所以必须先换成它的参数：
# 反过来做的话 `\emph{Foo}` 会先变成 `\emphFoo`（反斜杠 + 命令名粘着实词），
# 成稿里就是乱码。野生 `.bib` 的题名里 `\emph` / `\textit` / `\textsc` 非常常见。
_MARKUP_ARG_RE = re.compile(
    r"\\(?:emph|textit|textbf|textsc|textsf|texttt|textrm|textup|textnormal|textsl|"
    r"mkbibquote|mkbibemph|mkbibitalic|mkbibbold|mkbibparens|enquote|"
    r"mbox|hbox|text|mathrm|mathit|mathbf|underline)\s*\{([^{}]*)\}"
)
# `\mkbibquoteDe Motu` 这类「命令名与实词粘连」的 biblatex 写法：去掉命令名，留下实词
_GLUED_CMD_RE = re.compile(
    r"\\(?:mkbibquote|mkbibemph|mkbibitalic|mkbibbold|mkbibparens|textsc|textsuperscript)"
    r"(?=[A-Za-z0-9])"
)
_SYMBOL_CMD_RE = re.compile(r"\\([A-Za-z]+)\s*(?:\{\})?")
_SYMBOL_CMDS = {
    "TeX": "TeX",
    "LaTeX": "LaTeX",
    "BibTeX": "BibTeX",
    "ldots": "\u2026",
    "dots": "\u2026",
    "textendash": "\u2013",
    "textemdash": "\u2014",
    "textquotedblleft": "\u201c",
    "textquotedblright": "\u201d",
    "textquoteleft": "\u2018",
    "textquoteright": "\u2019",
    "quad": " ",
    "qquad": " ",
    # \u6ce8\u610f\uff1a`\o` `\ss` `\i` \u8fd9\u7c7b**\u5b57\u6bcd\u547d\u4ee4**\u4e0d\u5728\u8fd9\u91cc\u5904\u7406\u2014\u2014\u5b83\u4eec\u7531 `_decode_accents`
    # \u5728\u91cd\u97f3\u89e3\u7801\u4e4b\u540e\u7edf\u4e00\u6362\u6210\u5b57\u7b26\u3002\u653e\u8fd9\u91cc\u4f1a\u5148\u4e8e\u91cd\u97f3\u5c55\u5f00\uff0c\u628a `\'{\i}` \u62c6\u6210 `\u0131` + \u91cd\u97f3\uff0c
    # \u5f97\u5230\u7684\u662f\u300c\u70b9\u0131 + \u0301\u300d\u800c\u4e0d\u662f `\u00ed`\u3002
}


def _strip_markup(value: str) -> str:
    """把文本字段里的 LaTeX 排版命令换成它包裹的文字。"""
    previous = None
    while previous != value:  # 嵌套：`\\emph{\\textit{X}}`
        previous = value
        value = _MARKUP_ARG_RE.sub(r"\1", value)
    value = _GLUED_CMD_RE.sub("", value)
    return _SYMBOL_CMD_RE.sub(
        lambda m: _SYMBOL_CMDS.get(m.group(1), m.group(0)), value
    )


def _clean(value: str) -> str:
    value = value.strip()
    if value[:1] in "{(\"" and value[-1:] in "})\"":
        value = value[1:-1]
    value = _strip_markup(value)
    value = _decode_accents(value)
    value = value.replace("{", "").replace("}", "")
    value = _unescape(value)
    # LaTeX 的转义空格与 `@`（`\TeX\ book`、`Prof.\@ Smith`）
    value = value.replace("\\ ", " ").replace("\\@", "")
    value = re.sub(r"\s+", " ", value).strip()
    # LaTeX 连字：bib 里 `--` 是短破折号、`---` 是长破折号、`~` 是不换行空格
    return smart_quotes(
        value.replace("---", "\u2014").replace("--", "\u2013").replace("~", "\u00a0")
    )


def _is_whole_braced(s: str) -> bool:
    """判断整段字符串是否由一对完整包裹首尾的花括号组成（排除 `{A} {B}`）。"""
    if len(s) < 2 or s[0] != "{" or s[-1] != "}":
        return False
    depth = 0
    for i, ch in enumerate(s):
        if ch == "\\" and i + 1 < len(s):
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i == len(s) - 1
    return False


def _split_depth0_and(s: str) -> list[str]:
    """仅在花括号层级为 0 时按 `and` 拆作者，避免拆裂 `{Food and Agriculture Organization}`。"""
    chunks: list[str] = []
    depth, start, i, n = 0, 0, 0, len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0:
            m = re.match(r"\s+and\s+", s[i:], re.I)
            if m:
                chunks.append(s[start:i])
                i += m.end()
                start = i
                continue
        i += 1
    chunks.append(s[start:])
    return chunks


def _split_depth0_char(s: str, sep: str) -> list[str]:
    """仅在花括号层级为 0 时按分隔符（如 `,`）切分。"""
    parts: list[str] = []
    depth, start, i, n = 0, 0, 0, len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            parts.append(s[start:i])
            start = i + 1
        i += 1
    parts.append(s[start:])
    return parts


def _split_depth0_ws(s: str) -> list[str]:
    """仅在花括号层级为 0 时按空白切分，保留 `{Smith Jr.}` 为整体词元。"""
    tokens: list[str] = []
    cur: list[str] = []
    depth, i, n = 0, 0, len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            cur.append(s[i : i + 2])
            i += 2
            continue
        if ch == "{":
            depth += 1
            cur.append(ch)
        elif ch == "}":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch.isspace() and depth == 0:
            if cur:
                tokens.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
        i += 1
    if cur:
        tokens.append("".join(cur))
    return tokens


def _split_particle(family: str) -> tuple[str, str]:
    """把家族名里的小写前缀拆成「不可省略前缀」：`van Doorn` → (`van`, `Doorn`)。

    CSL 把它单列成 non-dropping-particle，姓氏大写化只作用于 `Doorn`，渲染成
    `DOORN J van` 而不是 `VAN DOORN J`。splitting 错了会把人名印错，比样式错更显眼。
    """
    words = family.split()
    i = 0
    while i < len(words) - 1 and words[i][:1].islower():
        i += 1
    if i == 0:
        return "", family
    return " ".join(words[:i]), " ".join(words[i:])


def _person(family: str, given: str = "") -> dict:
    particle, surname = _split_particle(family.strip())
    person = {"family": surname}
    if given.strip():
        person["given"] = given.strip()
    if particle:
        person["non-dropping-particle"] = particle
    return person


_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def _parse_names(raw: str) -> list[dict]:
    """BibTeX 姓名 → CSL 名字。支持：

    `{{World Health Organization}}` / `{{Food and Agriculture Organization}}` 整体加花括号是团体作者
    （内含逗号或 `and` 也不拆）；`J. R. {Smith Jr.}` 保留花括号包裹的复合姓氏不拆尾词；
    `Smith, Jr., John` 识别「姓, 后缀, 名」；`Ludwig van Beethoven` 识别小写姓氏前缀。
    """
    text = raw.strip()
    people: list[dict] = []
    chunks = _split_depth0_and(text)
    # BibTeX 的 `and others` 是「等等」（et al.），不是一位叫 others 的作者。
    # 不收掉的话，GB/T 会印出「王临慧, OTHERS.」、APA 会印出「Wang, & others.」。
    while chunks and _clean(chunks[-1]).strip().rstrip(".").lower() == "others":
        chunks.pop()
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if _is_whole_braced(chunk):
            people.append({"literal": _clean(chunk)})
            continue
        comma_parts = _split_depth0_char(chunk, ",")
        if len(comma_parts) > 1:
            raw_family = comma_parts[0].strip()
            rest = [_clean(part) for part in comma_parts[1:] if _clean(part)]
            suffix = ""
            if len(rest) > 1 and rest[0].rstrip(".").lower() in _SUFFIXES:
                suffix, rest = rest[0], rest[1:]
            given = ", ".join(rest)
            if _is_whole_braced(raw_family):
                person = {"family": _clean(raw_family)}
                if given:
                    person["given"] = given
            else:
                person = _person(_clean(raw_family), given)
            if suffix:
                person["suffix"] = suffix
            people.append(person)
        else:
            tokens = _split_depth0_ws(chunk)
            if not tokens:
                continue
            if len(tokens) == 1:
                people.append({"literal": _clean(tokens[0])})
                continue
            # 无逗号写法里的后缀：`John Smith Jr.` 的末词是后缀，不是姓氏的一部分
            # （`Smith, Jr., John` 与 `J. R. {Smith Jr.}` 两条路已各自处理好了）
            suffix = ""
            if len(tokens) >= 3 and not _is_whole_braced(tokens[-1]):
                if _clean(tokens[-1]).rstrip(".").lower() in _SUFFIXES:
                    suffix = _clean(tokens[-1])
                    tokens = tokens[:-1]
            cut = len(tokens) - 1
            while cut > 0 and not _is_whole_braced(tokens[cut - 1]):
                cleaned_prev = _clean(tokens[cut - 1])
                if not cleaned_prev or not cleaned_prev[:1].islower():
                    break
                cut -= 1
            given = " ".join(_clean(tok) for tok in tokens[:cut] if _clean(tok))
            family_tokens = tokens[cut:]
            if len(family_tokens) == 1 and _is_whole_braced(family_tokens[0]):
                person = {"family": _clean(family_tokens[0])}
                if given:
                    person["given"] = given
            else:
                family = " ".join(_clean(tok) for tok in family_tokens if _clean(tok))
                person = _person(family, given)
            if suffix:
                person["suffix"] = suffix
            people.append(person)
    return people


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _month(raw: str) -> int | None:
    text = (raw or "").strip().strip("{}").lower()[:3]
    if text.isdigit() and 1 <= int(text) <= 12:
        return int(text)
    return _MONTHS.get(text)


def _issued(raw_date: str, year: str) -> dict | None:
    if raw_date:
        parts = re.findall(r"\d+", raw_date)
        if parts:
            return {"date-parts": [[int(p) for p in parts[:3]]]}
    if year:
        m = re.search(r"\d{4}", year)
        if m:
            return {"date-parts": [[int(m.group(0))]]}
    return None


def _iter_entries(text: str):
    """逐条切出 (类型, key, 字段正文)。

    按配对花括号找条目结尾，不用 `.*?\n}`：后者要求收尾的 `}` 独占一行，
    单行写法的条目（`@article{a, author={…}, year={2020}}`）会被整条漏掉。

    `(` 定界的条目（`@article(key, … )`）同样是 BibTeX 标准写法，真实文献库里有整份
    只用括号的文件；只认花括号会让它们一条不剩地消失，且不报错。
    """
    pos = 0
    while True:
        head = _ENTRY_HEAD_RE.search(text, pos)
        if not head:
            return
        opener = head.group("open")
        closer = "}" if opener == "{" else ")"
        depth, brace, i = 1, 0, head.end()
        while i < len(text) and depth:
            ch = text[i]
            if ch == "\\":
                i += 2
                continue
            if opener == "{":
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
            else:
                # 括号式条目：花括号里的 `(` `)` 属于字段值，不参与条目定界计数
                if ch == "{":
                    brace += 1
                elif ch == "}":
                    brace = max(0, brace - 1)
                elif brace == 0 and ch == "(":
                    depth += 1
                elif brace == 0 and ch == ")":
                    depth -= 1
            i += 1
        yield head.group("kind").lower(), head.group("key"), text[head.end() : i - 1]
        pos = i


def crossref_keys(text: str) -> list[str]:
    """用了 `crossref` 的条目 key。

    那是「子条目从父条目继承字段」的写法（会议论文引用同一条 proceedings，省得每条都
    抄一遍会议名、出版社、年份）。本工具不做继承，这些条目会缺字段——要说得出来。
    """
    keys: list[str] = []
    for kind, key, body in _iter_entries(text or ""):
        if kind in _SKIP_KINDS:
            continue
        if _parse_fields(body).get("crossref"):
            keys.append(key)
    return keys


def parse_bibtex(text: str) -> list[dict]:
    """整份 .bib → CSL-JSON 条目列表。"""
    entries: list[dict] = []
    macros = _parse_strings(text or "")
    for kind, key, body in _iter_entries(text or ""):
        if kind in _SKIP_KINDS:
            continue
        fields = _parse_fields(body, macros)
        entry_type = _TYPE_MAP.get(kind, "article")
        # `@misc` 带真刊名就是期刊论文——带不带 `eprint` 都一样。APS/INSPIRE 与
        # Google Scholar 混导出来的条目常是「刊名 + 卷期页 + arXiv 号」，
        # 判成章节会让 GB/T 印 `[A/OL]`、APA 印成 `In … (Preprint No. …)`。
        if kind == "misc" and (fields.get("journal") or fields.get("journaltitle")):
            entry_type = "article-journal"
        item: dict = {"id": key, "type": entry_type}
        if fields.get("author"):
            item["author"] = _parse_names(fields.get("raw:author", fields["author"]))
        elif kind == "patent" and (fields.get("holder") or fields.get("assignee")):
            patent_owner = fields.get("raw:holder") or fields.get("raw:assignee") or fields.get("holder") or fields.get("assignee")
            item["author"] = _parse_names(patent_owner)
        if fields.get("editor"):
            item["editor"] = _parse_names(fields.get("raw:editor", fields["editor"]))
        if fields.get("translator"):
            item["translator"] = _parse_names(fields.get("raw:translator", fields["translator"]))
        # `bookauthor` 是 `@inbook` / `@incollection` 里「整本书的作者」，GB/T 的
        # `某章[M]//某书. 某出版社` 与 APA 的 `In A. Editor (Ed.)` 都要它；
        # 不映射就等于把这本书的作者整段删掉。
        if fields.get("bookauthor"):
            item["container-author"] = _parse_names(
                fields.get("raw:bookauthor", fields["bookauthor"])
            )
        for source, target in (
            ("title", "title"),
            ("journal", "container-title"),
            ("journaltitle", "container-title"),
            ("booktitle", "container-title"),
            # DBLP 派生的 `venue` 是同一件事的另一个字段名；放在 journal/booktitle 之后，
            # 让它们优先（同一份文件里两者都在时不至于被覆盖）
            ("venue", "container-title"),
            ("shortjournal", "container-title-short"),
            ("shorttitle", "title-short"),
            ("volume", "volume"),
            ("issue", "issue"),
            ("chapter", "chapter-number"),
            ("pages", "page"),
            ("publisher", "publisher"),
            ("school", "publisher"),
            ("institution", "publisher"),
            ("organization", "publisher"),
            ("address", "publisher-place"),
            ("location", "publisher-place"),
            ("authority", "authority"),
            ("doi", "DOI"),
            ("url", "URL"),
            ("edition", "edition"),
            ("version", "version"),
            ("series", "collection-title"),
            ("note", "note"),
            ("isbn", "ISBN"),
            ("issn", "ISSN"),
            ("langid", "language"),
            ("numpages", "number-of-pages"),
            ("numberofpages", "number-of-pages"),
            # `pagetotal` 是 `numpages` 的同义写法（GB/T 7714—2025 的标准示例全用它）
            ("pagetotal", "number-of-pages"),
            ("volumes", "number-of-volumes"),
        ):
            if fields.get(source) and target not in item:
                item[target] = fields[source]
        # 副题名在 CSL-JSON 里的常规写法是并进 `title`（`Title: Subtitle`）；
        # 丢掉 `subtitle` 的后果是题名被腰斩，比多印一个冒号糟得多。
        if fields.get("subtitle") and item.get("title"):
            sub = str(fields["subtitle"]).strip()
            base = str(item["title"]).strip()
            if sub and sub.lower() not in base.lower():
                item["title"] = f"{base}{'' if base.endswith((':', '?', '!', '：')) else ':'} {sub}"
        # `type` 只在报告/学位论文/专利/手稿上才是「文献类型描述」；
        # 期刊条目的 `type` 是数据字段（DBLP 写 `Journal Articles`、CNKI 写 `硕士`），
        # 无条件映射会把它们当描述语印进成稿（`[Journal Articles]`、`Patenteu`）。
        if fields.get("type") and item["type"] in _GENRE_TYPES:
            item.setdefault("genre", fields["type"])
        # `number` 在期刊（article/periodical）里是期号（issue），
        # 在报告/图书/会议集/标准等非期刊条目里是编号（number，如 techreport 的报告号）。
        if fields.get("number"):
            if item["type"] in _PERIODICAL_TYPES:
                item.setdefault("issue", fields["number"])
            else:
                item.setdefault("number", fields["number"])
        # `howpublished`：含 `\url{...}` 或 `http(s)://...` 时提取为 URL；
        # 其余纯文本在网页/电子资源下作 `publisher`（APA/GB/T 7714 均会渲染平台/发布方），无 URL 时退回 `note`
        raw_howpub = fields.get("raw:howpublished")
        if raw_howpub:
            m_url = re.search(r"\\url\s*\{([^}]+)\}|(https?://[^\s}]+)", raw_howpub)
            if m_url:
                item.setdefault("URL", _clean_verbatim(m_url.group(1) or m_url.group(2)))
            elif fields.get("howpublished"):
                if "publisher" not in item:
                    item["publisher"] = fields["howpublished"]
                else:
                    item.setdefault("note", fields["howpublished"])
        issued = _issued(fields.get("date", ""), fields.get("year", ""))
        month = _month(fields.get("month", ""))
        if issued and month and len(issued["date-parts"][0]) == 1:
            issued["date-parts"][0].append(month)
        if issued:
            item["issued"] = issued
        if kind == "phdthesis":
            item.setdefault("genre", "Doctoral dissertation")
        elif kind == "mastersthesis":
            item.setdefault("genre", "Master's thesis")
        eprint = (fields.get("eprint") or "").strip()
        # `eprinttype` 是 biblatex 对 `archiveprefix` 的写法，两个都要认
        eprint_type = (fields.get("archiveprefix") or fields.get("eprinttype") or "").lower()
        if eprint:
            # 已正式发表的期刊论文常同时带 arXiv 号：那是附加信息，不是「预印本」。
            # 一律打 genre=preprint 会让 APA 给正经论文印 `[Preprint]`。
            published = item["type"] in _PERIODICAL_TYPES and "container-title" in item
            if not published:
                item.setdefault("genre", "preprint")
            if not item.get("URL") and "arxiv" in eprint_type:
                # `eprint = {arXiv:2101.00001}` 自带前缀，再拼一次就成了坏链
                ident = re.sub(r"^arxiv\s*:\s*", "", eprint, flags=re.I).strip()
                item["URL"] = f"https://arxiv.org/abs/{ident}"
        # `@misc` 无期刊/预印本但带 URL（含 `howpublished = {\url{...}}`）通常表示网页/电子资源
        if (
            kind == "misc"
            and item.get("URL")
            and "container-title" not in item
            and not fields.get("eprint")
        ):
            item["type"] = "webpage"
        accessed = _issued(fields.get("urldate", ""), "")
        if accessed:
            item["accessed"] = accessed
        entries.append(item)
    return entries
