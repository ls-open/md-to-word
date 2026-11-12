"""TemplateSpec ↔ 格式要求文本的往返。

`parse_format` 与 `build_template` 是一对 API，能解析出来的东西就必须能再生成回去；
否则调用方只能回头找原始文本，组合等于没用。判据是「再解析一遍得到同一个 spec」。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from md_to_word.spec.parser import parse_format
from md_to_word.spec.serializer import serialize_format

PRESETS = Path(__file__).resolve().parents[1] / "presets"


@pytest.mark.parametrize("preset", ["zh-academic", "zh-tw-academic", "zh-report", "en-nature"])
def test_round_trip_is_lossless(preset: str) -> None:
    original = parse_format((PRESETS / f"{preset}.txt").read_text(encoding="utf-8"))
    rewritten = parse_format(serialize_format(original))

    assert rewritten.styles == original.styles
    assert rewritten.table == original.table
    assert rewritten.table_header == original.table_header
    assert rewritten.margins == original.margins
    assert rewritten.page_size == original.page_size
    assert rewritten.proofing_lang == original.proofing_lang
    assert rewritten.default_latin == original.default_latin
    assert rewritten.gutter_cm == original.gutter_cm
    assert rewritten.mirror_margins == original.mirror_margins
    assert rewritten.punctuation_compression == original.punctuation_compression


def test_serialized_text_declares_schema_version() -> None:
    spec = parse_format((PRESETS / "zh-academic.txt").read_text(encoding="utf-8"))
    assert serialize_format(spec).startswith("# schema:")


def test_page_grid_round_trip() -> None:
    """`文档网格：每页N行` 存的是「渲染完真的 N 行」，不是把 N 直接当行距。

    行距倍数会把网格间距再乘一遍（实测 22 行配 1.5 倍只落 14 行），所以写入时除掉了
    倍数；反解把倍数乘回去之后必须还是 22——公文版式（GB/T 9704）靠这个数。
    """
    from md_to_word.template.generator import (
        body_line_spacing_multiple, doc_grid_lines_from_pitch, doc_grid_pitch,
    )

    spec = parse_format(
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
    spec = parse_format(base.rstrip() + "\n公式编号：紧跟\n")
    assert spec.equation_number == "inline"
    assert "公式编号：紧跟" in serialize_format(spec)

    default = parse_format(base)
    assert default.equation_number == "right"
    assert "公式编号" not in serialize_format(default)


def test_gutter_mirror_and_punctuation_round_trip() -> None:
    """装订线、对称页边距、标点压缩要能无损往返；未声明时保持默认，不污染预设文本。"""
    base = (PRESETS / "zh-academic.txt").read_text(encoding="utf-8")
    default = parse_format(base)
    default_text = serialize_format(default)
    assert "装订线" not in default_text
    assert "对称页边距" not in default_text
    assert "标点压缩" not in default_text

    custom_text = (
        base.rstrip()
        + "\n装订线：1.2cm\n对称页边距：开\n标点压缩：不压缩\n"
    )
    spec = parse_format(custom_text)
    serialized = serialize_format(spec)
    assert "装订线：1.2cm" in serialized
    assert "对称页边距：开" in serialized
    assert "标点压缩：不压缩" in serialized

    rewritten = parse_format(serialized)
    assert rewritten.gutter_cm == 1.2
    assert rewritten.mirror_margins is True
    assert rewritten.punctuation_compression == "doNotCompress"


@pytest.mark.parametrize(
    "path",
    [
        Path(__file__).resolve().parents[1] / "demo" / "01_chinese_thesis" / "format.txt",
        Path(__file__).resolve().parents[1] / "demo" / "02_modern_report" / "format.txt",
    ],
    ids=["thesis", "report"],
)
def test_demo_requirements_round_trip_without_loss(path: Path) -> None:
    """真稿件的规格同样要能原样写回去。

    这条测试是在补一个实测出来的洞：`build_template(spec)` 内部先序列化再解析，
    序列化漏掉哪一项，用 Python API 传进来的规格就被悄悄改掉——边框、颜色、字距、
    制表位当时都会丢，而预设里恰好没用到这些，预设往返测试因此一直是绿的。
    """
    original = parse_format(path.read_text(encoding="utf-8"))
    rewritten = parse_format(serialize_format(original))
    assert rewritten.styles == original.styles


def test_join_toc_round_trips_in_both_languages() -> None:
    """样式行上的 `加入目录`/`不入目录` 与 `加入页眉`/`不入页眉` 经序列化再解析后不能丢失。"""
    zh_lines = [
        line.replace("不入目录 不入页眉", "加入目录 加入页眉")
        if line.startswith("摘要标题：")
        else (
            line.replace("加入目录 加入页眉", "加入目录 不入页眉")
            if line.startswith("参考文献标题：")
            else line
        )
        for line in (PRESETS / "zh-academic.txt").read_text(encoding="utf-8").splitlines()
    ]
    zh_orig = parse_format("\n".join(zh_lines) + "\n")
    zh_serialized = serialize_format(zh_orig)
    assert "加入目录" in zh_serialized
    assert "加入页眉" in zh_serialized
    assert "不入页眉" in zh_serialized
    assert parse_format(zh_serialized).styles == zh_orig.styles

    en_lines = [
        line.replace("no-toc no-header", "join-toc join-header")
        if line.startswith("Abstract Title:")
        else (
            line.replace("join-toc join-header", "join-toc no-header")
            if line.startswith("References Title:")
            else line
        )
        for line in (PRESETS / "en-nature.txt").read_text(encoding="utf-8").splitlines()
    ]
    en_orig = parse_format("\n".join(en_lines) + "\n")
    en_serialized = serialize_format(en_orig)
    assert "加入目录" in en_serialized
    assert "加入页眉" in en_serialized
    assert "不入页眉" in en_serialized
    assert parse_format(en_serialized).styles == en_orig.styles

    # 默认预设里的「不入目录」「不入页眉」也能完整往返
    preset_zh = parse_format((PRESETS / "zh-academic.txt").read_text(encoding="utf-8"))
    preset_zh_ser = serialize_format(preset_zh)
    assert "不入目录" in preset_zh_ser
    assert "不入页眉" in preset_zh_ser
    assert parse_format(preset_zh_ser).styles == preset_zh.styles

    preset_en = parse_format((PRESETS / "en-nature.txt").read_text(encoding="utf-8"))
    preset_en_ser = serialize_format(preset_en)
    assert "不入目录" in preset_en_ser
    assert "不入页眉" in preset_en_ser
    assert parse_format(preset_en_ser).styles == preset_en.styles
