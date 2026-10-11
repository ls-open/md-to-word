---
title: "我的第一份规范 Word 文档"
crossref:
  tbl-prefix: "表"
---

# 引言

这是正文。中文首行缩进两个字符，西文用 Times New Roman，行距 1.5 倍——这些都不用你在 Word 里点，全由下面那份 `requirements.txt` 声明。

# 一个三线表

::: {custom-style="Table Caption"}
**表 1** 两种方案的关键指标
:::

| 指标 | 方案 A | 方案 B |
|:---|---:|---:|
| 首次排版耗时（秒） | 1.10 | 1.04 |
| 重复导出耗时（秒） | 1.12 | 1.03 |

::: {custom-style="Table Note"}
注：数据由 `demo/make_demo_figures.py` 实跑测得。
:::
