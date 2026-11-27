"""Given-name initialisation shared by the CSL engine and disambiguation."""

from __future__ import annotations


def initialize_given(given: str, mark: str, hyphen: bool = True) -> str:
    """`Mary Jane` → `M. J.`, `Jean-Luc` → `J.-L.`（CSL 的 `initialize-with`）。

    首字母之间用 `mark` 连接；连字符部件各自缩写，再用 `-` 接回（`hyphen=False`
    时当空格处理）；小写的 particle 原样保留。返回值不带末尾空格——`initials`
    按自己的约定补，`Name.initialize` 直接使用。
    """
    chunks = given.split('-') if hyphen else [given.replace('-', ' ')]
    results = []
    for chunk in chunks:
        words = chunk.replace('.', ' ').split()
        text = ''
        group = []
        for word in words:
            if word[0].isupper():
                group.append(word[0])
            else:
                text += mark.join(group) + mark + ' ' + word + ' '
                group = []
        text += mark.join(group) + mark
        results.append(' '.join(text.split()))
    return '-'.join(results)
