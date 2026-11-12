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
}

_ENTRY_HEAD_RE = re.compile(r"@(?P<kind>\w+)\s*\{\s*(?P<key>[^,\s]+)\s*,", re.S)
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


def _parse_fields(body: str, macros: dict[str, str] | None = None) -> dict:
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
    """技术类原文段清洗（URL / DOI / 日期 / eprint）：保留 -- / --- / ~ / 直引号等原样字符。"""
    value = value.strip()
    if value[:1] in "{(\"" and value[-1:] in "})\"":
        value = value[1:-1].strip()
    m = re.fullmatch(r"\\url\s*\{(.*)\}", value, re.S)
    if m:
        value = m.group(1)
    return re.sub(r"\s+", " ", value).strip()


def _clean(value: str) -> str:
    value = value.strip()
    if value[:1] in "{(\"" and value[-1:] in "})\"":
        value = value[1:-1]
    value = _decode_accents(value)
    value = value.replace("{", "").replace("}", "")
    value = _unescape(value)
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
    for chunk in _split_depth0_and(text):
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
                people.append(person)
            else:
                family = " ".join(_clean(tok) for tok in family_tokens if _clean(tok))
                people.append(_person(family, given))
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
    """
    pos = 0
    while True:
        head = _ENTRY_HEAD_RE.search(text, pos)
        if not head:
            return
        depth, i = 1, head.end()
        while i < len(text) and depth:
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
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
        if kind in ("comment", "string", "preamble"):
            continue
        if _parse_fields(body).get("crossref"):
            keys.append(key)
    return keys


def parse_bibtex(text: str) -> list[dict]:
    """整份 .bib → CSL-JSON 条目列表。"""
    entries: list[dict] = []
    macros = _parse_strings(text or "")
    for kind, key, body in _iter_entries(text or ""):
        if kind in ("comment", "string", "preamble"):
            continue
        fields = _parse_fields(body, macros)
        entry_type = _TYPE_MAP.get(kind, "article")
        if (
            kind == "misc"
            and (fields.get("journal") or fields.get("journaltitle"))
            and not fields.get("eprint")
        ):
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
        for source, target in (
            ("title", "title"),
            ("journal", "container-title"),
            ("journaltitle", "container-title"),
            ("booktitle", "container-title"),
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
            ("type", "genre"),
            ("note", "note"),
            ("numpages", "number-of-pages"),
            ("numberofpages", "number-of-pages"),
            ("volumes", "number-of-volumes"),
        ):
            if fields.get(source) and target not in item:
                item[target] = fields[source]
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
        if fields.get("eprint"):
            item.setdefault("genre", "preprint")
            if not item.get("URL") and "arxiv" in fields.get("archiveprefix", "").lower():
                item["URL"] = f"https://arxiv.org/abs/{fields['eprint']}"
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
