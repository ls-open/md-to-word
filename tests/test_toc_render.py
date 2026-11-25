"""打开即好用的目录：只有真 Word 能证。

我们不给 TOC 域存缓存结果（存了就会过期），只打 `dirty` 标记。要证明的是用户双击打开
docx 的那一刻目录就已经排好，而不是停在「（打开文档后目录会自动生成）」等 F9。
这条要驱动 Word，没装 Word 的机器整文件跳过；`dirty` 标记本身由
test_docx_writer.py 里的结构测试守着。
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from md_to_word.i18n import t
from md_to_word.model.reader import read_markdown
from md_to_word.template.builder import build_template
from md_to_word.visual_qa.word_pdf import can_render_word_pdf
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt").read_text(encoding="utf-8")

pytestmark = pytest.mark.skipif(
    not can_render_word_pdf()[0], reason="需要本机 Microsoft Word 才能验真"
)

# 「打开 → 等它排完 → 读正文 → 关窗」。**不调用 repaginate / update field**：
# 要验的就是打开本身够不够，调了就等于自己替 Word 把域算了。
_OPEN_AND_READ = r"""
on run argv
    set p to item 1 of argv
    set inName to item 2 of argv
    set txt to ""
    with timeout of 150 seconds
        tell application "Microsoft Word"
            set d to open file name p
            delay 3
            set txt to (content of (text object of d))
            repeat 3 times
                delay 1
                try
                    close d saving no
                end try
                set remaining to 0
                try
                    repeat with doc in documents
                        if (name of doc as text) contains inName then
                            set remaining to remaining + 1
                        end if
                    end repeat
                on error
                    set remaining to 1
                end try
                if remaining is 0 then exit repeat
            end repeat
        end tell
    end timeout
    return txt
end run
"""


def test_toc_is_populated_when_word_opens_the_file(tmp_path: Path) -> None:
    template = tmp_path / "tpl.docx"
    build_template(PRESET, template)
    out = write_docx(
        read_markdown(
            "{{< toc 2 >}}\n\n"
            "# 第一章 绪论\n\n正文。\n\n"
            "## 1.1 研究背景\n\n正文。\n\n"
            "# 第二章 方法\n\n正文。\n"
        ),
        template,
        tmp_path / "doc.docx",
    )

    container = Path.home() / "Library/Containers/com.microsoft.Word/Data"
    probe = container / f"_md2word_toc_check_{os.getpid()}.docx"
    probe.write_bytes(out.read_bytes())
    try:
        res = subprocess.run(
            ["osascript", "-", str(probe), probe.name],
            input=_OPEN_AND_READ,
            capture_output=True,
            text=True,
            timeout=200,
        )
    finally:
        probe.unlink(missing_ok=True)

    assert res.returncode == 0, res.stderr
    text = res.stdout
    assert t("markers.toc_placeholder", "zh") not in text, "目录还停在占位文字上，Word 没有重算域"
    # 目录条目：标题 + 制表符 + 页码，排在正文之前
    assert re.search(r"第一章 绪论\s+\d+", text), text[:300]
    assert "1.1 研究背景" in text, text[:300]
