"""手册与指南里的示例，必须真的过一遍解析器。

这些片段是 Agent 的合同：照着写却跑不通，比没写更糟。语法改过一次（分节标记只收节名），
人工同步迟早漏一段；这里把代码块抽出来，格式片段交给 `parse_format`、稿件片段交给
`read_markdown`、命令行交给各自的 argparse，JSON 片段交给 `json.loads`。
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest

from md_to_word.cli import build_parser
from md_to_word.model.reader import read_markdown
from md_to_word.spec.parser import parse_format
from md_to_word.template.extractor import build_parser as build_template_parser

RESOURCES = Path(__file__).resolve().parents[1] / "src" / "md_to_word" / "resources"
DOCS = ("manual.md", "manual_en.md", "guide.md", "guide_zh.md")
FENCE = re.compile(r"^```(\w*)\n(.*?)^```$", re.M | re.S)
# 格式文件的指纹：整篇太长，文档里常只贴一段
FORMAT_HINTS = ("纸张：", "Paper:", "分节：", "Section:")
COMMAND_HEADS = ("md-to-word ", "md-to-word-template ")


def _docs() -> list[tuple[Path, str]]:
    out = [(RESOURCES / name, (RESOURCES / name).read_text(encoding="utf-8")) for name in DOCS]
    assert all(p.is_file() for p, _ in out), [str(p) for p, _ in out]
    return out


def _fences(text: str) -> list[tuple[str, str, int]]:
    return [
        (m.group(1), m.group(2), text[: m.start()].count("\n") + 1)
        for m in FENCE.finditer(text)
    ]


def test_manuscript_snippets_still_read() -> None:
    checked = 0
    for path, text in _docs():
        for lang, body, line in _fences(text):
            if lang != "markdown":
                continue
            try:
                read_markdown(body)
            except Exception as exc:  # noqa: BLE001 - 报错要带文件与行号
                pytest.fail(f"{path.name}:{line} 的稿件片段读不通：{exc}")
            checked += 1
    assert checked >= 4, "一个 markdown 代码块都没抽到，正则或文档结构变了"


def test_format_snippets_still_parse() -> None:
    checked = 0
    for path, text in _docs():
        for _lang, body, line in _fences(text):
            if not any(hint in body for hint in FORMAT_HINTS):
                continue
            try:
                parse_format(body)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"{path.name}:{line} 的格式片段解析不了：{exc}")
            checked += 1
    assert checked >= 1, "一个格式片段都没抽到，正则或文档结构变了"


def test_json_snippets_still_parse() -> None:
    checked = 0
    for path, text in _docs():
        for lang, body, line in _fences(text):
            if lang != "json":
                continue
            try:
                json.loads(body)
            except ValueError as exc:
                pytest.fail(f"{path.name}:{line} 的 JSON 片段不合法：{exc}")
            checked += 1
    assert checked >= 1


def test_every_documented_command_still_parses() -> None:
    """文档里每一行 `md-to-word …` / `md-to-word-template …` 都得被真正的参数表接受。

    只检查参数名，不执行命令：示例里的文件名本来就不存在。
    """
    parsers = {
        False: build_parser("zh"),
        True: build_template_parser("zh"),
    }
    checked = 0
    for path, text in _docs():
        for _lang, body, line in _fences(text):
            for raw in body.splitlines():
                cmd = raw.split(" #")[0].strip()
                if not cmd.startswith(COMMAND_HEADS):
                    continue
                argv = shlex.split(cmd)
                is_template = argv[0].endswith("-template")
                try:
                    parsers[is_template].parse_args(argv[1:])
                except SystemExit:
                    pytest.fail(f"{path.name}:{line} 的示例命令参数表不认：{cmd}")
                checked += 1
    assert checked >= 8, "文档里的命令行示例变少了，先确认是不是抽取出错"
