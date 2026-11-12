"""`.bib` 体检：查的是「导出时会不会出事」，不是「符不符合某个外部规范」。

关键一点——**用导出器自己那套解析器**（`transform/bibtex.py` 的 `_iter_entries` /
`_parse_fields`），不另写一份。另写一份的 linter 迟早会和真实解析分叉：它说没问题、
导出时却是空的，比没有 linter 更误导。上一版这个脚本就是这么写废的——它只认
`@type{`，`@article(`（括号式）的库被它判成「文件中未发现任何条目」。

四类检查，按「出了事看得见吗」分级：

- **错误**（`error`）：导出会出错或印出空白——重复的引用键、条目缺 `title`、键名解析不了。
- **提示**（`warning`）：能导出去，但排出来多半不是你要的——缺推荐字段、作者用逗号分隔
  而不是 `and`（BibTeX 会当成一个人）、标题里的缩写没加大括号（APA 一类句首大写样式会把
  它转成小写）。

`author` 与 `title` 的两条从**原始值**（`raw:` 前缀）判断：解析器会把能修的修掉，修完就看不出
问题出在哪了，而作者被当成一个人这种「修」恰恰是错的。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from md_to_word.transform.bibtex import (
    _SKIP_KINDS,
    _iter_entries,
    _parse_fields,
    _parse_strings,
)

# 各条目类型的推荐字段：每组里任一出现即算有（`journal` / `journaltitle` 两种写法都常见）。
REQUIRED_FIELDS: dict[str, list[list[str]]] = {
    "article": [["author"], ["title"], ["journal", "journaltitle"], ["year", "date"]],
    "book": [["author", "editor"], ["title"], ["publisher"], ["year", "date"]],
    "inbook": [["author", "editor"], ["title"], ["publisher"], ["year", "date"]],
    "incollection": [["author"], ["title"], ["booktitle"], ["publisher"], ["year", "date"]],
    "inproceedings": [["author"], ["title"], ["booktitle"], ["year", "date"]],
    "conference": [["author"], ["title"], ["booktitle"], ["year", "date"]],
    "phdthesis": [["author"], ["title"], ["school", "institution"], ["year", "date"]],
    "mastersthesis": [["author"], ["title"], ["school", "institution"], ["year", "date"]],
    "techreport": [["author", "institution"], ["title"], ["year", "date"]],
}

# 两个及以上的大写字母连写：DNA、BERT、GB/T 里的 GB。已被大括号包住的排除。
_ACRONYM_RE = re.compile(r"(?<!\{)\b([A-Z]{2,}\d*)\b(?!\})")
# 句首大写样式里本来就会大写的常见词，不该被当成专有缩写催着加括号。
_HARMLESS_UPPER = frozenset(
    "IN ON AN AS AT BY OF TO IS OR AND THE FOR A".split()
)
_VALID_KEY_RE = re.compile(r"^[\w:.\-]+$")


@dataclass(frozen=True)
class Finding:
    """一条体检结果。`line` 是条目起始行（1 起）。"""

    level: str  # "error" | "warning"
    key: str
    line: int
    message: str

    def format(self) -> str:
        mark = "✗" if self.level == "error" else "⚠"
        where = f" 行 {self.line}" if self.line else ""
        tag = f" [@{self.key}]" if self.key else ""
        return f" {mark}{where}{tag} {self.message}"


def _locate(text: str, key: str, cursor: int) -> tuple[int, int]:
    """条目起始行号与下一次搜索的起点。解析器不报位置，这里按 `@type{key,` 回查。

    从上一处之后找起：重复键时才能分别定位到各自那一行，而不是都指到第一处。
    """
    m = re.compile(rf"@\w+\s*[{{(]\s*{re.escape(key)}\s*,").search(text, cursor)
    if not m:
        return 0, cursor
    return text.count("\n", 0, m.start()) + 1, m.end()


def lint_bibtex(text: str) -> list[Finding]:
    """体检一整份 `.bib`。空文本也算一种结果，由调用方决定怎么报。"""
    findings: list[Finding] = []
    macros = _parse_strings(text or "")
    entries = [(k, key, body) for k, key, body in _iter_entries(text or "")
               if k not in _SKIP_KINDS]
    if not entries:
        # 一条都没读出来时最需要提示：空文件、格式不对、或者路径指错了，
        # 而不说话会让人以为「体检通过」。
        return [Finding("warning", "", 0, "没解析出任何条目——空文件、格式不对，或全是注释。")]

    seen: dict[str, int] = {}
    cursor = 0
    for kind, key, body in entries:
        line, cursor = _locate(text, key, cursor)

        if not _VALID_KEY_RE.match(key):
            findings.append(Finding("error", key, line,
                                    "引用键里有空格或特殊字符，解析器可能读不到它。"))

        if key in seen:
            findings.append(Finding("error", key, line,
                                    f"重复的引用键，与行 {seen[key]} 那条冲突——"
                                    "引文会全指到先出现的那条。"))
            continue
        seen[key] = line

        fields = _parse_fields(body, macros)
        if not fields.get("title"):
            findings.append(Finding("error", key, line,
                                    "没有 title。文献表里这一条会印成空白。"))

        for group in REQUIRED_FIELDS.get(kind, []):
            # 缺 title 已经按错误报过了，不再叠一条提示：同一件事说两遍只会显得罗嗦
            if group == ["title"]:
                continue
            if not any(fields.get(f) for f in group):
                findings.append(Finding("warning", key, line,
                                        f"@{kind} 缺推荐字段 {group[0]}，"
                                        f"{_style_hint(kind)}多半会缺一项。"))

        raw_author = fields.get("raw:author", "")
        if (
            raw_author.count(",") >= 2
            and not re.search(r"\band\b", raw_author, re.I)
            and not raw_author.startswith("{")
        ):
            findings.append(Finding("warning", key, line,
                                    "author 像是用逗号分隔了多位作者。BibTeX 里多人要用 "
                                    "`and`，否则整串被当成一个人。"))

        raw_title = fields.get("raw:title", "")
        acronyms = [a for a in _ACRONYM_RE.findall(raw_title)
                    if a not in _HARMLESS_UPPER]
        if acronyms:
            sample = "、".join(f"{{{a}}}" for a in acronyms[:3])
            findings.append(Finding(
                "warning", key, line,
                f"标题里的缩写 {sample} 没用大括号保护，APA 一类会把它们转成小写。"))

    return findings


def _style_hint(kind: str) -> str:
    """缺字段时给一句「会缺什么」，比单纯说「缺字段」有用。"""
    return {
        "article": "刊名或年份",
        "book": "出版社或年份",
        "incollection": "书名",
        "inproceedings": "会议名",
        "conference": "会议名",
        "phdthesis": "学校",
        "mastersthesis": "学校",
    }.get(kind, "这一项")


def lint_bibtex_file(path: Path) -> tuple[list[Finding], str | None]:
    """读一个文件再体检。返回 `(结果, 读取失败的原因)`。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [], str(exc)
    return lint_bibtex(text), None
