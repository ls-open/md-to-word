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

_ENTRY_RE = re.compile(r"@(?P<kind>\w+)\s*\{\s*(?P<key>[^,\s]+)\s*,(?P<body>.*?)\n\}", re.S)
_FIELD_NAME_RE = re.compile(r"(\w+)\s*=\s*", re.S)


def _read_field_value(body: str, start: int) -> tuple[str, int]:
    """从 `=` 之后读一个字段值，返回 (值, 下一个位置)。

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


def _parse_fields(body: str) -> dict:
    fields: dict[str, str] = {}
    pos = 0
    while pos < len(body):
        m = _FIELD_NAME_RE.search(body, pos)
        if not m:
            break
        value, pos = _read_field_value(body, m.end())
        if value:
            fields[m.group(1).lower()] = _clean(value)
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


def _unescape(value: str) -> str:
    def repl(m: re.Match) -> str:
        return _LATEX_ESCAPES.get(m.group(1), m.group(0))

    return _ESCAPE_SEQ_RE.sub(repl, value)


def _clean(value: str) -> str:
    value = value.strip()
    if value[:1] in "{(\"" and value[-1:] in "})\"":
        value = value[1:-1]
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


def _parse_names(raw: str) -> list[dict]:
    people: list[dict] = []
    for chunk in re.split(r"\s+and\s+", _clean(raw)):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "," in chunk:
            family, _, given = chunk.partition(",")
            people.append(_person(family, given))
        else:
            parts = chunk.split()
            if len(parts) == 1:
                people.append({"literal": parts[0]})
            else:
                people.append(_person(parts[-1], " ".join(parts[:-1])))
    return people


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


def parse_bibtex(text: str) -> list[dict]:
    """整份 .bib → CSL-JSON 条目列表。"""
    entries: list[dict] = []
    for match in _ENTRY_RE.finditer(text or ""):
        kind = match.group("kind").lower()
        if kind in ("comment", "string", "preamble"):
            continue
        fields = _parse_fields(match.group("body"))
        item: dict = {"id": match.group("key"), "type": _TYPE_MAP.get(kind, "article")}
        if fields.get("author"):
            item["author"] = _parse_names(fields["author"])
        if fields.get("editor"):
            item["editor"] = _parse_names(fields["editor"])
        for source, target in (
            ("title", "title"),
            ("journal", "container-title"),
            ("journaltitle", "container-title"),
            ("booktitle", "container-title"),
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
        ):
            if fields.get(source) and target not in item:
                item[target] = fields[source]
        issued = _issued(fields.get("date", ""), fields.get("year", ""))
        if issued:
            item["issued"] = issued
        accessed = _issued(fields.get("urldate", ""), "")
        if accessed:
            item["accessed"] = accessed
        entries.append(item)
    return entries
