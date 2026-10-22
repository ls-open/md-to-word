"""md_to_word.scaffold — `md-to-word init`：让第一次导出只需要一条命令。

同类工具都有这一步（`sphinx-quickstart`、`mdbook init`、`typst init`、`quarto create`）：
输入是一门小语言时，空白目录才是最大的门槛。这里生成的是一份**能直接导出**的稿件
和一份**完整有效**的格式声明，不是占位符——用户要做的只是改里面的内容。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from md_to_word.config import DEFAULT_PRESET_EN, DEFAULT_PRESET_ZH, resolve_preset_path
from md_to_word.i18n import t

SAMPLE_ZH = """%% 文档标题 我的第一份规范 Word 文档

# 引言

把这一段换成你自己的内容。排版由同目录的 `format.txt` 决定：改那里的某一行，
这段文字的字体、行距、缩进就跟着变，正文一个字都不用动。

# 一个三线表

%% 表题 **表 1** 示例表

| 列 A | 列 B |
|:--|:--|
| 值 1 | 值 2 |
| 值 3 | 值 4 |

%% 表注 注：表注写在表格下方，表题写在表格上方。
"""

SAMPLE_EN = """%% Title My first compliant Word document

# Introduction

Replace this paragraph with your own. The layout comes from `format.txt` beside it:
change one line there and the font, spacing or indent of this paragraph changes —
the text itself is untouched.

# A three-line table

%% Table Caption **Table 1** A sample table

| Column A | Column B |
|:--|:--|
| Value 1 | Value 2 |
| Value 3 | Value 4 |

%% Table Note Note: the caption goes above the table, the note below it.
"""


def _sample(lang: str) -> str:
    return SAMPLE_EN if lang == "en" else SAMPLE_ZH


def run_init(
    directory: Path,
    *,
    preset: Optional[str] = None,
    force: bool = False,
    lang: str = "zh",
) -> int:
    """在 `directory` 里写好 `format.txt` 与 `hello.md`，打印下一步。

    已存在的同名文件不覆盖（除非 `force`）：这一步是给空目录用的，不是同步工具。
    """
    name = preset or (DEFAULT_PRESET_EN if lang == "en" else DEFAULT_PRESET_ZH)
    preset_path = resolve_preset_path(name)
    if preset_path is None:
        print(t("init.preset_missing", lang, name=name))
        return 1

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(t("init.dir_failed", lang, dir=directory, err=exc))
        return 1

    targets = {"format": directory / "format.txt", "manuscript": directory / "hello.md"}
    existing = [p for p in targets.values() if p.exists()]
    if existing and not force:
        print(t("init.exists", lang, paths=", ".join(str(p) for p in existing)))
        return 1

    shutil.copyfile(preset_path, targets["format"])
    targets["manuscript"].write_text(_sample(lang), encoding="utf-8")

    print(t(
        "init.done",
        lang,
        directory=directory,
        preset=name,
        command=f"md-to-word hello.md -o hello.docx",
    ))
    return 0
