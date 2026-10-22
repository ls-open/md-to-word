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
_FIELD_RE = re.compile(r"(?P<name>\w+)\s*=\s*(?P<value>\{.*?\}|\(.*?\)|\"[^\"]*\"|\d+)\s*,?", re.S)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _clean(value: str) -> str:
    value = value.strip()
    if value[:1] in "{(\"" and value[-1:] in "})\"":
        value = value[1:-1]
    value = value.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", value).strip()


def _parse_names(raw: str) -> list[dict]:
    people: list[dict] = []
    for chunk in re.split(r"\s+and\s+", _clean(raw)):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "," in chunk:
            family, _, given = chunk.partition(",")
            people.append({"family": family.strip(), "given": given.strip()})
        else:
            parts = chunk.split()
            if len(parts) == 1:
                people.append({"literal": parts[0]})
            else:
                people.append({"family": parts[-1], "given": " ".join(parts[:-1])})
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
        fields = {
            m.group("name").lower(): _clean(m.group("value"))
            for m in _FIELD_RE.finditer(match.group("body"))
        }
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
        entries.append(item)
    return entries
