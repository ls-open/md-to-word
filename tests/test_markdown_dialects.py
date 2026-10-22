"""我们不支持的 Markdown 方言，必须在导出前拦下。

判据只有一条：这种写法写下去，原始语法会不会漏进 Word。会漏的（`---` 印成三条短横、
`<br>` 印成尖括号、`**` 跨行时印成星号）**静默印错比报错难查得多**，因此一律阻断。

这组用例是那张「不支持清单」的机器版本：某天有人顺手加了一条放行规则，这里会红。
"""

from __future__ import annotations

import pytest

from md_to_word.utils.skill_utils import dialect_issues

# (名称, 正文, 是否应当被拦)
CASES = [
    ("html 标签", "第一行<br>第二行\n", True),
    ("html 注释里的标签样式", "文字 <span>标</span> 文字\n", True),
    ("裸 URL 尖括号", "见 <https://example.com> 说明\n", True),
    ("横向分隔线", "上一段。\n\n---\n\n下一段。\n", True),
    ("星号分隔线", "上一段。\n\n***\n\n下一段。\n", True),
    ("setext 标题", "标题文字\n====\n", True),
    ("定义列表", "术语\n: 定义文字\n", True),
    ("任务列表", "- [ ] 未完成\n- [x] 已完成\n", True),
    ("无外竖线表格", "名称 | 值\n--- | ---\na | 1\n", True),
    ("嵌套引用", "> 一级\n>\n> > 二级\n", True),
    ("全角样式标记", "％％ 摘要 内容\n", True),
    ("四空格代码块", "    print(1)\n    print(2)\n", True),
    ("跨行加粗", "这是**加粗\n文字**的例子。\n", True),
    ("跨行行内公式", "公式 $a +\nb$ 结束。\n", True),
    ("列表项第二段", "- 一\n\n  补充说明。\n", True),
    ("井号后没空格", "#标题\n", True),
    ("图片行带对齐属性", "![](a.png){align=right}\n", True),
    ("图片宽度写百分比", "![](a.png){width=50%}\n", True),
    ("只有井号没有标题", "#\n\n正文。\n", True),
    # 支持的写法一条都不能误伤
    ("围栏代码块里的尖括号", "```html\n<br>\n```\n", False),
    ("行内代码里的分隔线", "写 `---` 表示分隔线。\n", False),
    ("注释里的标签", "<!-- 说明 <br> -->\n正文。\n", False),
    ("正常表格", "| 甲 | 乙 |\n|:--|--:|\n| 1 | 2 |\n", False),
    ("三级标题", "### 小节\n\n正文。\n", False),
    ("嵌套列表", "1. 一\n   - 一之一\n2. 二\n", False),
    ("引用块内列表", "> 说明：\n>\n> - 项一\n", False),
    ("表格分隔行", "| 甲 | 乙 |\n|---|---|\n| 1 | 2 |\n", False),
    ("正常加粗", "这是**加粗**的字。\n", False),
    ("图片只写宽度", "![](a.png){width=8cm}\n", False),
    ("公式块", "$$\na = b\n$$\n", False),
    ("单行公式块", "$$a = b$$\n", False),
    ("块级公式内不查符号", "$$\na $ b\n$$\n", False),
    ("单行公式后仍查行内公式", "$$a=b$$\n\n公式 $x\n结束\n", True),
]

@pytest.mark.parametrize(("name", "body", "blocked"), CASES)
def test_dialect_verdict(name: str, body: str, blocked: bool) -> None:
    issues = dialect_issues(body)
    assert bool(issues) is blocked, f"{name}: {issues}"


def test_line_numbers_point_at_the_offending_line() -> None:
    text = "---\ntitle: t\n---\n\n# 一\n\n上一段。\n\n---\n\n下一段。\n"
    issues = dialect_issues(text)
    assert issues and issues[0][0] == 9, "报错行号要落在原稿的那一行上"
