"""TemplateSpec ↔ 格式要求文本的往返。

`parse_requirements` 与 `build_template` 是一对 API，能解析出来的东西就必须能再生成回去；
否则调用方只能回头找原始文本，组合等于没用。判据是「再解析一遍得到同一个 spec」。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from md_to_word.spec.parser import parse_requirements
from md_to_word.spec.serializer import serialize_requirements

PRESETS = Path(__file__).resolve().parents[1] / "presets"


@pytest.mark.parametrize("preset", ["zh-academic", "en-nature"])
def test_round_trip_is_lossless(preset: str) -> None:
    original = parse_requirements((PRESETS / f"{preset}.txt").read_text(encoding="utf-8"))
    rewritten = parse_requirements(serialize_requirements(original))

    assert rewritten.styles == original.styles
    assert rewritten.table == original.table
    assert rewritten.table_header == original.table_header
    assert rewritten.margins == original.margins
    assert rewritten.page_size == original.page_size
    assert rewritten.proofing_lang == original.proofing_lang
    assert rewritten.default_latin == original.default_latin


def test_serialized_text_declares_schema_version() -> None:
    spec = parse_requirements((PRESETS / "zh-academic.txt").read_text(encoding="utf-8"))
    assert serialize_requirements(spec).startswith("# schema:")
