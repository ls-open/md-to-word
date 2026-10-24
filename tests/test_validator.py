"""Unit tests for validator checks (md_to_word.validator)."""

from __future__ import annotations

from md_to_word.validator.check import caption_adjacency_issues


def test_caption_adjacent_above_table():
    md = """
%% 表题 表 1 样本测试表

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

%% 表题 表 1 样本测试表
"""
    issues = caption_adjacency_issues(md)
    assert len(issues) == 0


def test_orphaned_table_caption_fails():
    md = """
%% 表题 表 1 孤立的表格题注

这里是一段毫无表格相伴的正文内容……

# 下一节
"""
    issues = caption_adjacency_issues(md)
    assert len(issues) == 1
    assert "未紧邻表格" in issues[0][1]


def test_orphaned_image_caption_fails():
    md = """
%% 图片题注 图 1 孤立的图片题注

这里也是一段没有任何图片的正文内容……
"""
    issues = caption_adjacency_issues(md)
    assert len(issues) == 1
    assert "未紧邻图片" in issues[0][1]


def test_image_caption_adjacent_above_and_below():
    md1 = """
%% 图片题注 图 1 架构图

![架构图](figures/arch.png)
"""
    assert len(caption_adjacency_issues(md1)) == 0

    md2 = """
![架构图](figures/arch.png)

%% 图片题注 图 1 架构图
"""
    assert len(caption_adjacency_issues(md2)) == 0


def test_body_text_penetration_detected():
    """测试正文穿透漏洞已被修复：题注与远方图片之间夹带正文必须被判定为孤立题注。"""
    md = """
%% 图片题注 图 1 孤立题注
这是一段正文，分析了系统性能，但作者忘记在此处插入图表。
这是一段更多的正文解释。
![图 2 另外一个图](figures/arch.png)
"""
    issues = caption_adjacency_issues(md)
    assert len(issues) == 1
    assert "未紧邻图片" in issues[0][1]


def test_ghost_container_detected():
    """测试空壳容器伪装漏洞已被修复：无真实实体的空容器不能欺骗门禁。"""
    md = """
::: {#fig-ghost}
%% 图片题注 图 1 幽灵题注
:::
"""
    issues = caption_adjacency_issues(md)
    assert len(issues) == 1
    assert "未紧邻图片" in issues[0][1]


def test_table_with_multiline_table_note_passes():
    """测试多行学术表注合法共存场景不被误报。"""
    md = """
| 排版要素 | Pandoc | 本方案 |
|---|---|---|
| 中西文分离 | 否 | 是 |

%% 表注 注1：数据来源于基准测试环境； 注2：判定以各家默认导出为准； 注3：多行统计显著性 P < 0.01； 注4：补充说明细节； 注5：置信区间分析。

%% 表题 表 1 主流方案特性对照表
"""
    issues = caption_adjacency_issues(md)
    assert len(issues) == 0
