"""md_to_word.contract — 机器可读的契约。

`--contract` 的人读速查在 `cli.contract_cheatsheet`；这里给程序与 Agent 一份
同源的结构化版本：版本号、文档路径、预设指纹、样式词表、退出码、JSON 键。

单一真相源：样式来自 `spec.constants.STYLE_MAP`，预设来自预设目录，退出码来自
`status`，JSON 键与 CLI 出口共用 `RESULT_JSON_KEYS`。这里不手写第二份名单。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from md_to_word import __version__
from md_to_word.config import (
    default_preset_name,
    get_resources_dir,
    resolve_preset_path,
)
from md_to_word.i18n import t
from md_to_word.spec.constants import STYLE_CN, STYLE_EN, STYLE_MAP, YAML_KEYS
from md_to_word.spec.presets import list_available_presets
from md_to_word.status import EXIT_ERROR, EXIT_OK, EXIT_PDF_SKIPPED, EXIT_USAGE
from md_to_word.utils.pdf_figure import PDF_SUFFIX, RASTER_SUFFIXES

# `--json` 结果对象的键集。CLI 出口按这份顺序构造；tests 盯着两边不许分叉。
RESULT_JSON_KEYS = (
    "ok",
    "returncode",
    "input",
    "output",
    "pdf",
    "pdf_skip_reason",
    "lang",
    "doc_lang",
    "format_source",
    "messages",
    "warnings",
    "errors",
    "diagnostics",
)

BLOCK_MARKERS = ("{{< pagebreak >}}", "{{< toc >}}", "{{< section … >}}")

# 稿件里本引擎能读的图片格式；PDF 会在导出时栅格化。
FIGURE_FORMATS = tuple(sorted(RASTER_SUFFIXES | {PDF_SUFFIX}))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def style_pairs() -> list[dict[str, str]]:
    """样式词表：每个 Word 样式取中英两个名字，按词表声明顺序。

    同一目标有多个别名（`表题` / `表格题注` / `表名` 都指向 Table Caption），
    契约里只给一个正典写法，避免 Agent 以为有几种不同样式。
    """
    # 正典名以 `STYLE_CN` / `STYLE_EN` 为准：`STYLE_MAP` 里第一个中文别名不一定是
    # 报错与文档使用的那个（Table Caption 的第一个别名曾给出「表格题注」，而正典是「表题」）。
    pairs: list[dict[str, str]] = []
    for target in dict.fromkeys(STYLE_MAP.values()):
        pairs.append({
            "style": target,
            "zh": STYLE_CN.get(target, target),
            "en": STYLE_EN.get(target, target),
        })
    return pairs


def style_names(ascii_only: bool) -> list[str]:
    """某个语言下的样式名，按词表顺序。`--contract` 速查与 `--help` 共用。"""
    return [p["en" if ascii_only else "zh"] for p in style_pairs()]


def contract_payload(lang: str = "zh") -> dict[str, Any]:
    """`--contract --json` 与 MCP `get_contract` 的返回体。"""
    resources = get_resources_dir()
    presets = []
    for name in list_available_presets():
        path = resolve_preset_path(name)
        if path is None:
            continue
        default_for = [
            code for code in ("zh", "en") if default_preset_name(code) == name
        ]
        presets.append({
            "id": name,
            "path": str(path),
            "sha256": _sha256(path),
            "default_for": default_for,
        })
    return {
        "version": __version__,
        "lang": lang,
        "guides": {
            "agent": str(resources / "guide.md"),
            "human_zh": str(resources / "guide_zh.md"),
        },
        "manuals": {
            "zh": str(resources / "manual.md"),
            "en": str(resources / "manual_en.md"),
        },
        "presets": presets,
        "styles": style_pairs(),
        "yaml_keys": list(YAML_KEYS),
        "block_markers": list(BLOCK_MARKERS),
        "style_line_prefix": "%% ",
        "figure_formats": list(FIGURE_FORMATS),
        "exit_codes": {
            str(EXIT_OK): t("contract.exit.ok", lang),
            str(EXIT_ERROR): t("contract.exit.error", lang),
            str(EXIT_USAGE): t("contract.exit.usage", lang),
            str(EXIT_PDF_SKIPPED): t("contract.exit.pdf_skipped", lang),
        },
        "json_keys": list(RESULT_JSON_KEYS),
    }
