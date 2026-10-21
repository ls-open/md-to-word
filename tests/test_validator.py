"""Unit tests for validator checks (md_to_word.validator)."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from md_to_word.validator.check import caption_adjacency_issues


def test_caption_adjacent_above_table():
    md = """
::: {custom-style="Table Caption"}
表 1 样本测试表
:::

| 列 1 | 列 2 |
|---|---|
| A | B |
"""
    issues = caption_adjacency_issues(md)
    assert len(issues) == 0


def test_caption_adjacent_below_table():
    md = """
| 列 1 | 列 2 |
|---|---|
| A | B |

::: {custom-style="Table Caption"}
表 1 样本测试表
:::
"""
    issues = caption_adjacency_issues(md)
    assert len(issues) == 0


def test_orphaned_table_caption_fails():
    md = """
::: {custom-style="Table Caption"}
表 1 孤立的表格题注
:::

这里是一段毫无表格相伴的正文内容……

# 下一节
"""
    issues = caption_adjacency_issues(md)
    assert len(issues) == 1
    assert "未紧邻表格" in issues[0][1]


def test_orphaned_image_caption_fails():
    md = """
::: {custom-style="Image Caption"}
图 1 孤立的图片题注
:::

这里也是一段没有任何图片的正文内容……
"""
    issues = caption_adjacency_issues(md)
    assert len(issues) == 1
    assert "未紧邻图片" in issues[0][1]


def test_image_caption_adjacent_above_and_below():
    md1 = """
::: {custom-style="Image Caption"}
图 1 架构图
:::

![架构图](figures/arch.png)
"""
    assert len(caption_adjacency_issues(md1)) == 0

    md2 = """
![架构图](figures/arch.png)

::: {custom-style="Image Caption"}
图 1 架构图
:::
"""
    assert len(caption_adjacency_issues(md2)) == 0
