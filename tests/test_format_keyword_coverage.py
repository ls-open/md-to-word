"""词表里的每个关键字，都得有落点：写进产物，并且被产物对账看见。

没落点的关键字最坏：格式文件写了、导出成功、产物里什么也没发生，或者写了但没人验，
以后哪天真写坏了也不会有人知道。「声明了只做一半」和「声明了不做」在这里同样红。
"""

from __future__ import annotations

import re
from pathlib import Path

from md_to_word.spec import parser

SRC = Path(__file__).resolve().parents[1] / "src" / "md_to_word"
WRITERS = {"产物的写出": SRC / "template" / "generator.py", "文档写出": SRC / "writer" / "docx_writer.py"}
AUDIT = SRC / "audit" / "inspector.py"

# 落点不在两个写出器里的少数几项，逐个说明为什么
ELSEWHERE = {
    "space_after_pt": "表后间距由流水线传给写出器（参数名 table_space_after），不在词表层再出现",
    "num": "正则组名，不是属性键",
}


def _keywords() -> dict[str, str]:
    """从 _CLAUSE_TABLE 的动作里取属性键——lambda 的字符串常量就是它写进 spec 的那个键。"""
    found: dict[str, str] = {}
    for _mode, pattern, action in parser._CLAUSE_TABLE:
        code = getattr(action, "__code__", None)
        if code is None:
            continue
        for const in code.co_consts:
            if isinstance(const, str) and re.fullmatch(r"[a-z][a-z0-9_]{2,}", const):
                found.setdefault(const, pattern.pattern[:40])
    return found


def test_the_scan_still_sees_the_whole_vocabulary() -> None:
    """取键的方式依赖 lambda 的写法；写法一改这里会先红，而不是悄悄少查一批。"""
    assert len(_keywords()) >= 25, sorted(_keywords())


def test_every_keyword_reaches_the_output_and_the_audit() -> None:
    texts = {name: path.read_text(encoding="utf-8") for name, path in WRITERS.items()}
    audit_text = AUDIT.read_text(encoding="utf-8")
    missing = []
    for key, pattern in sorted(_keywords().items()):
        if key in ELSEWHERE:
            continue
        written = any(re.search(rf"\b{key}\b", text) for text in texts.values())
        audited = re.search(rf"\b{key}\b", audit_text) is not None
        if not written or not audited:
            missing.append(f"{key}（{pattern}）：{'没写出' if not written else ''}"
                           f"{'没对账' if not audited else ''}")
    assert not missing, "这些关键字缺落点：\n  " + "\n  ".join(missing)
