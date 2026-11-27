"""Page-range helpers shared by the CSL engine and post-processing."""

from __future__ import annotations


def pad_expanded_page_end(first: str, last: str) -> str:
    """`321-8` → `328`：把起始页的公共前缀补到缩写了的末页。"""
    if len(last) < len(first):
        return first[: len(first) - len(last)] + last
    return last
