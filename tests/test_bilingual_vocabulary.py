"""中英双语的词表完整性。

两条防线：

1. **结构**：`_CLAUSE_TABLE` 里每条含中文的规则，必须同时含英文别名。新增属性时
   只写中文，这条立刻红——否则「支持英文」会随时间悄悄退化。
2. **行为**：同一份格式的中文写法与英文写法，必须解析出完全相同的 spec。比对的是
   解析结果，不是报错文案。
"""

from __future__ import annotations

import re

import pytest

from md_to_word.spec.parser import _CLAUSE_TABLE, parse_requirements

CJK = re.compile(r"[一-鿿]")
ASCII = re.compile(r"[A-Za-z]")


def test_every_clause_has_an_english_alias() -> None:
    gaps = [
        pattern.pattern
        for _mode, pattern, _action in _CLAUSE_TABLE
        if CJK.search(pattern.pattern) and not ASCII.search(pattern.pattern)
    ]
    assert not gaps, "以下属性规则只有中文写法，缺英文别名：" + "；".join(gaps)


# 中文写法 ↔ 英文写法：两侧必须解析出同一个 spec
PAIRS = {
    "body": (
        "正文：宋体 小四 不加粗 不倾斜 左对齐 行距1.5倍 段前0磅 段后6磅 首行缩进2字符",
        "Body Text: 宋体 12pt not-bold not-italic left line-spacing 1.5 "
        "space-before 0pt space-after 6pt indent 2chars",
    ),
    "hanging_indent": (
        "参考文献：宋体 小四 不加粗 不倾斜 左对齐 行距1.5倍 段前0磅 段后6磅 悬挂缩进0.5英寸",
        "Bibliography: 宋体 12pt not-bold not-italic left line-spacing 1.5 "
        "space-before 0pt space-after 6pt hanging-indent 0.5in",
    ),
    "min_line_spacing": (
        "正文：宋体 小四 不加粗 不倾斜 左对齐 行距最小值25磅 段前0磅 段后0磅 首行缩进0字符",
        "Body Text: 宋体 12pt not-bold not-italic left min-line-spacing 25pt "
        "space-before 0pt space-after 0pt indent 0",
    ),
    "table_header": (
        "表头：宋体 小四 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符 跨页重复",
        "Table Header: 宋体 12pt not-bold not-italic center line-spacing 1.0 "
        "space-before 0pt space-after 0pt indent 0 repeat-header",
    ),
}

SPEC_LEVEL = {
    "paper": ("纸张：A4", "Paper: A4"),
    "margins": (
        "页边距：上2.54cm 下2.54cm 左3.18cm 右3.18cm",
        "Margins: top 2.54cm bottom 2.54cm left 3.18cm right 3.18cm",
    ),
    "table": (
        "表格：居中 三线表 线宽上1.5磅 线宽底1.5磅 线宽表头下0.75磅 单元格垂直居中",
        "Table: center three-line border-top 1.5pt border-bottom 1.5pt "
        "border-header 0.75pt valign center",
    ),
}


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_style_line_parses_identically(name: str) -> None:
    zh_text, en_text = PAIRS[name]
    zh_spec = parse_requirements(zh_text)
    en_spec = parse_requirements(en_text)
    # 「表头：」进的是 table_header，不是 styles
    zh = zh_spec.table_header if name == "table_header" else zh_spec.styles[0]
    en = en_spec.table_header if name == "table_header" else en_spec.styles[0]

    assert zh["bold"] == en["bold"]
    assert zh["italic"] == en["italic"]
    assert zh["alignment"] == en["alignment"]
    assert zh["indent"] == en["indent"]
    assert zh["indent_type"] == en["indent_type"]
    assert zh["line_spacing"] == en["line_spacing"]
    assert zh.get("repeat_header", False) == en.get("repeat_header", False)


@pytest.mark.parametrize("name", sorted(SPEC_LEVEL))
def test_spec_level_setting_parses_identically(name: str) -> None:
    zh = parse_requirements(SPEC_LEVEL[name][0])
    en = parse_requirements(SPEC_LEVEL[name][1])
    field = {"paper": "page_size", "margins": "margins", "table": "table"}[name]
    assert getattr(zh, field) == getattr(en, field)
