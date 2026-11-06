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
    "book": "book",
    "booklet": "pamphlet",
    "inbook": "chapter",
    "incollection": "chapter",
    "inproceedings": "paper-conference",
    "conference": "paper-conference",
    "manual": "book",
    "mastersthesis": "thesis",
    "phdthesis": "thesis",
    "proceedings": "book",
    "techreport": "report",
    "unpublished": "manuscript",
    "misc": "article",
    "online": "webpage",
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
        while j < n and body[j] not in ",\n}":
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
            # 原始值另存一份：团体作者靠花括号保护（`{{World Health Organization}}`），
            # 清洗会把它和「名 姓」混成一类
            fields[f"raw:{name}"] = "".join(parts)
            fields[name] = _clean("".join(_strip_delims(p) for p in parts))
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
_ACCENT_CMD = "".join(re.escape(c) for c in _ACCENTS)


def _decode_accents(value: str) -> str:
    def accent(m: re.Match) -> str:
        return unicodedata.normalize("NFC", m.group(2) + _ACCENTS[m.group(1)])

    # `{\v r}` / `\v{r}` / `\v r` 三种写法都要认；命令与字母之间允许一个空格
    value = re.sub(rf"\\\s?\{{?([{_ACCENT_CMD}])\s?(\w)\}}?", accent, value)
    value = re.sub(r"\\(O|o|aa|AA|ss|ae|AE|oe|OE|l|L|i|j)\b",
                   lambda m: _ACCENT_LETTERS[m.group(1)], value)
    return value


def _unescape(value: str) -> str:
    def repl(m: re.Match) -> str:
        return _LATEX_ESCAPES.get(m.group(1), m.group(0))

    return _ESCAPE_SEQ_RE.sub(repl, value)


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
    """BibTeX 姓名 → CSL 名字。三种写法都要认：

    `{World Health Organization}` 整体加花括号是团体作者（有逗号也不拆）；
    `Smith, Jr., John` 是「姓, 后缀, 名」；`Ludwig van Beethoven` 的小写词是姓氏前缀。
    """
    text = raw.strip()
    if text[:1] == "{" and text[-1:] == "}":
        text = text[1:-1]          # 字段值自己的外层花括号
    people: list[dict] = []
    for chunk in re.split(r"\s+and\s+", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("{") and chunk.endswith("}"):
            people.append({"literal": _clean(chunk)})
            continue
        text = _clean(chunk)
        if "," in text:
            parts = [part.strip() for part in text.split(",")]
            family, rest = parts[0], parts[1:]
            suffix = ""
            if len(rest) > 1 and rest[0].rstrip(".").lower() in _SUFFIXES:
                suffix, rest = rest[0], rest[1:]
            person = _person(family, ", ".join(rest))
            if suffix:
                person["suffix"] = suffix
            people.append(person)
        else:
            words = text.split()
            if len(words) == 1:
                people.append({"literal": words[0]})
                continue
            cut = len(words) - 1
            while cut > 0 and words[cut - 1][:1].islower():
                cut -= 1
            people.append(_person(" ".join(words[cut:]), " ".join(words[:cut])))
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
        item: dict = {"id": key, "type": _TYPE_MAP.get(kind, "article")}
        if fields.get("author"):
            item["author"] = _parse_names(fields.get("raw:author", fields["author"]))
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
            ("number", "issue"),
            ("pages", "page"),
            ("publisher", "publisher"),
            ("school", "publisher"),
            ("institution", "publisher"),
            ("address", "publisher-place"),
            ("doi", "DOI"),
            ("url", "URL"),
            ("edition", "edition"),
            ("series", "collection-title"),
            ("note", "note"),
            ("numpages", "number-of-pages"),
            ("numberofpages", "number-of-pages"),
            ("volumes", "number-of-volumes"),
        ):
            if fields.get(source) and target not in item:
                item[target] = fields[source]
        issued = _issued(fields.get("date", ""), fields.get("year", ""))
        month = _month(fields.get("month", ""))
        if issued and month and len(issued["date-parts"][0]) == 1:
            issued["date-parts"][0].append(month)
        if issued:
            item["issued"] = issued
        if kind == "phdthesis":
            item["genre"] = "Doctoral dissertation"
        elif kind == "mastersthesis":
            item["genre"] = "Master's thesis"
        if fields.get("eprint"):
            item["genre"] = item.get("genre", "preprint")
            if not item.get("URL") and "arxiv" in fields.get("archiveprefix", "").lower():
                item["URL"] = f"https://arxiv.org/abs/{fields['eprint']}"
        accessed = _issued(fields.get("urldate", ""), "")
        if accessed:
            item["accessed"] = accessed
        entries.append(item)
    return entries
