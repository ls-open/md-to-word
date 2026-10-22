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


def test_page_grid_round_trip() -> None:
    """`文档网格：每页N行` 存的是「渲染完真的 N 行」，不是把 N 直接当行距。

    行距倍数会把网格间距再乘一遍（实测 22 行配 1.5 倍只落 14 行），所以写入时除掉了
    倍数；反解把倍数乘回去之后必须还是 22——公文版式（GB/T 9704）靠这个数。
    """
    from md_to_word.template.generator import (
        body_line_spacing_multiple, doc_grid_lines_from_pitch, doc_grid_pitch,
    )

    spec = parse_requirements(
        (PRESETS / "zh-academic.txt").read_text(encoding="utf-8").rstrip() + "\n文档网格：每页22行\n"
    )
    assert spec.doc_grid_lines == 22
    pitch = doc_grid_pitch(spec, spec.margins)
    assert pitch > 0
    back = doc_grid_lines_from_pitch(
        pitch, body_line_spacing_multiple(spec.styles), spec.page_size, spec.margins
    )
    assert back == 22


def test_equation_number_placement_round_trip() -> None:
    """`公式编号：紧跟` 要能往返；默认的「右侧」不写进文本（保持预设干净）。"""
    base = (PRESETS / "zh-academic.txt").read_text(encoding="utf-8")
    spec = parse_requirements(base.rstrip() + "\n公式编号：紧跟\n")
    assert spec.equation_number == "inline"
    assert "公式编号：紧跟" in serialize_requirements(spec)

    default = parse_requirements(base)
    assert default.equation_number == "right"
    assert "公式编号" not in serialize_requirements(default)


@pytest.mark.parametrize(
    "path",
    [
        Path(__file__).resolve().parents[1] / "demo" / "01_chinese_thesis" / "requirements.txt",
        Path(__file__).resolve().parents[1] / "demo" / "02_modern_report" / "requirements.txt",
    ],
    ids=["thesis", "report"],
)
def test_demo_requirements_round_trip_without_loss(path: Path) -> None:
    """真稿件的规格同样要能原样写回去。

    这条测试是在补一个实测出来的洞：`build_template(spec)` 内部先序列化再解析，
    序列化漏掉哪一项，用 Python API 传进来的规格就被悄悄改掉——边框、颜色、字距、
    制表位当时都会丢，而预设里恰好没用到这些，预设往返测试因此一直是绿的。
    """
    original = parse_requirements(path.read_text(encoding="utf-8"))
    rewritten = parse_requirements(serialize_requirements(original))
    assert rewritten.styles == original.styles
