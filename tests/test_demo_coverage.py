"""四份样例合起来必须覆盖每一种支持的写法。

样例是最终验收面：结构都在样例里真导出过，才有资格说"用户这么写也行"。这条测试是
那张覆盖表的机器版本——某次改动把样例里的引用块删了、或者新加一种写法忘了在样例里
落一格，这里会红。

判据只看**写法有没有出现**，跑得通不通由 `test_demos.py` 负责，两件事分开。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMOS = {
    "00": REPO_ROOT / "demo" / "00_quickstart" / "hello.md",
    "01": REPO_ROOT / "demo" / "01_chinese_thesis" / "thesis_sample.md",
    "02": REPO_ROOT / "demo" / "02_modern_report" / "report_sample.md",
    "03": REPO_ROOT / "demo" / "03_english_paper" / "paper.md",
}

# 写法 → 至少出现在一份样例里
COVERAGE = {
    "一级标题": r"^# ",
    "二级标题": r"^## ",
    "三级标题": r"^### ",
    "摘要": r"^%%\s*(摘要|Abstract)\s",
    "关键词": r"^%%\s*(关键词|Keywords)\s",
    "目录域": r"\{\{<\s*toc",
    "分节与页码格式": r"\{\{<\s*section",
    "分页符": r"\{\{<\s*pagebreak",
    "脚注": r"\[\^",
    "图片与题注": r"^%%\s*(图片题注|Image Caption)",
    "表题": r"^%%\s*(表题|Table Caption)",
    "表注": r"^%%\s*(表注|Table Note)",
    "公式编号": r"\$\$.*\{#eq-",
    "交叉引用": r"@eq-",
    "参考文献标题": r"^%%\s*(参考文献标题|References Title)",
    "有序列表": r"^\d+\.\s+\S",
    "无序列表": r"^[-*]\s+\S",
    "引用块": r"^> \S",
    "代码块": r"^```",
    "行内代码": r"`[^`]+`",
    "链接": r"\[[^\]]+\]\(http",
    "删除线": r"~~[^~]+~~",
    "下划线": r"\{\.underline\}",
    "上下标": r"\^\{|_\{",
}


@pytest.mark.parametrize("feature", sorted(COVERAGE))
def test_feature_appears_in_some_demo(feature: str) -> None:
    pattern = re.compile(COVERAGE[feature], re.M)
    hit = [name for name, path in DEMOS.items() if pattern.search(path.read_text(encoding="utf-8"))]
    assert hit, f"没有任何样例演示「{feature}」——样例之外没人验收这条路径"


def test_every_demo_is_listed_in_the_coverage_table() -> None:
    """样例目录与表格对不上时，读文档的人会以为有几个样例。"""
    table = (REPO_ROOT / "demo" / "README.md").read_text(encoding="utf-8")
    for folder in DEMOS.values():
        assert folder.parent.name in table, f"demo/README.md 的覆盖表漏了 {folder.parent.name}"
