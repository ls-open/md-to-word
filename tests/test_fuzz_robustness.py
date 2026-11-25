"""确定性的组合输入不该让解析器吐出未预料的异常。

这里不追求「随机发现新语法」，而是用固定种子把标题、公式、表格、引用、注释与
控制字符拼在一起，确认三层入口（文档模型、格式词表、预检）对任意组合都只有两种
结果：正常返回，或按契约报错（`MarkdownError` / `ValueError`）。出现 `KeyError`、
`IndexError`、`AssertionError` 这类内部异常，就是用户会看到的 traceback。
"""

from __future__ import annotations

import random
from pathlib import Path

from md_to_word.model.reader import MarkdownError, read_markdown
from md_to_word.spec.parser import parse_format
from md_to_word.validator.check import validate_manuscript

MARKDOWN_FRAGMENTS = [
    "# 一级", "## 二级", "### 三级", "#### 四级", "##### 五级", "###### 六级",
    "正文一段。", "English body.", "**加粗**", "*斜体*", "~~删除~~", "[字]{.underline}",
    "H~2~O", "x^2^", "`code`", "```", "```python", "- 项", "  - 子项", "1. 一", "2. 二",
    "> 引用", "| A | B |", "|:--|--:|", "| 1 | 2 |", "%% 摘要 摘要",
    "%% 表题 **表 1** 题", "$$E=mc^2$$", "$$\\frac{a}{b}$$ {#eq-a}", "@eq-a",
    "[@smith2024]", "[^1]", "[^1]: 注", "![](x.png)", "![](https://x/y.png)",
    "{{< toc >}}", "{{< pagebreak >}}", "{{< section 正文 >}}", "<!-- 注释 -->",
    "<div>html</div>", "---", "...", "---\ntitle: x\n---", "\\", "  ", "\t",
    "😀", "中文🚀", "<script>alert(1)</script>", "&amp;", "a  b", "$x$", "$$",
    "%%", "%% ", "#", "{}", "[]", "()",
]

FORMAT_FRAGMENTS = [
    "纸张：A4", "纸张：Letter",
    "页边距：上2.54cm 下2.54cm 左2.54cm 右2.54cm",
    "正文：宋体 小四 行距1.5倍 首行缩进2字符",
    "一级标题：黑体 三号 加粗 居中 行距1.5倍 段前18磅 段后12磅",
    "页眉：宋体 小五 居中 下边框双线", "页眉内容：{样式标题:Heading 1}",
    "页脚内容：{页码}", "页码：阿拉伯 起始1", "表格：居中 三线表 线宽上1.5磅",
    "表头：宋体 五号 加粗 居中 跨页重复", "目录标题：黑体 四号 加粗 居中",
    "目录一级：宋体 小四 左对齐", "分节：封面", "封面页眉内容：无", "# 注释",
    "", "   ", "未知行：abc", "正文：", "纸张：", "页边距：", "页眉内容：无",
    "对称页边距：开", "校对语言：zh-CN", "公式编号格式：({n})", "图表：居中",
    "段落颜色：颜色#GGGGGG", "页眉内容：{样式标题:不存在的样式}", "页脚内容：{总页数}",
    "装订线：1cm", "页眉距边界：1.5cm",
]


def _texts(fragments: list[str], seed: int, count: int) -> list[str]:
    rnd = random.Random(seed)
    return [
        "\n".join(rnd.choice(fragments) for _ in range(rnd.randint(1, 20)))
        for _ in range(count)
    ]


def test_document_reader_only_raises_contract_errors() -> None:
    for text in _texts(MARKDOWN_FRAGMENTS, seed=20261125, count=300):
        try:
            read_markdown(text)
        except MarkdownError:
            pass


def test_format_parser_only_raises_value_errors() -> None:
    for text in _texts(FORMAT_FRAGMENTS, seed=9704, count=400):
        try:
            parse_format(text, lang="zh")
        except ValueError:
            pass


def test_preflight_only_returns_a_report(tmp_path: Path) -> None:
    manuscript = tmp_path / "m.md"
    for text in _texts(MARKDOWN_FRAGMENTS, seed=42, count=40):
        manuscript.write_text(text, encoding="utf-8")
        report = validate_manuscript(manuscript, lang="zh")  # 不许抛出任何异常
        assert isinstance(report.valid, bool)
