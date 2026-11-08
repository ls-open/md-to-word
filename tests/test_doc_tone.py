"""对外文档不许给产品「加封号」。

上一版的 README 与 GitHub About 写着「出版级」「企业级」「一键」「最原生」，它们不是
事实，是一种评价。这类话的危害不在于难看，而在于**它替读者做了判断**：读者看不出
「出版级」到底验过什么，只能选择信或不信。工具说自己能做什么、验到哪一层、哪儿不行，
这些都能核；「出版级」一个字都核不了。

所以这里封的不是词，是**给产品加等级、加称号**这个动作。词表要窄：`完整`、`稳健`、
`绝对路径` 这些是正常用词，被误封会逼着维护的人把准确的说法改坏，那比留着「出版级」更糟。

真有正当用处（例如引用别人的原话），加进 ALLOW 并写清为什么——加白名单这个动作本身
就是一次复核。
"""

from __future__ import annotations

from pathlib import Path

import md_to_word

RESOURCES = Path(md_to_word.__file__).resolve().parent / "resources"
REPO = Path(md_to_word.__file__).resolve().parents[2]

DOCS = (
    REPO / "README.md",
    REPO / "README_EN.md",
    REPO / "SKILL.md",
    RESOURCES / "guide.md",
    RESOURCES / "manual.md",
    RESOURCES / "manual_en.md",
    # 演示站的页面是**另一份**文案，和 app.py 里的模板数据不共源：改了 app.py，
    # 页面上那句「企业级技术报告」照样在。所以它也得进这张网。
    REPO / "web" / "static" / "index.html",
)

# 只收「给产品加等级 / 加称号」的说法。比较级如实取舍（「三条路里最费手工的那条」）
# 不在此列，那是描述，不是封号。
BANNED = (
    "出版级",
    "生产级",
    "企业级",
    "工业级",
    "专业级",
    "印刷级",
    "零门槛",
    "一键",
    "最原生",
    "最智能",
    "最确定",
    "业界领先",
    "完美支持",
    "publication-grade",
    "production-grade",
    "enterprise-grade",
    "professional-grade",
    "print-quality",
    "world-class",
    "best-in-class",
    "state-of-the-art",
    "cutting-edge",
    "seamless",
    "flawless",
)

# (文件, 词, 理由)。空着是对的。
ALLOW: set[tuple[str, str]] = set()


def test_public_docs_do_not_grade_the_product() -> None:
    hits = []
    for path in DOCS:
        assert path.is_file(), f"要扫的文档不存在：{path}"
        text = path.read_text(encoding="utf-8").lower()
        for term in BANNED:
            key = (path.name, term)
            if term in text and key not in ALLOW:
                hits.append(f"{path.name}: {term}")
    assert not hits, (
        "这些文档给产品加了等级或称号：" + "、".join(hits) +
        "\n写它能做什么、验到哪一层、哪里不行；不写它有多好。"
    )
