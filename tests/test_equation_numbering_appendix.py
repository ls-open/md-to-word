"""附录里的公式编号：单独一套编号，且前缀能由格式文件表达。

学校的两种要求长得很不一样——「（附2-1）」和「（B-1）」——所以这里钉的不是"我们选了
哪种"，而是**写什么就落成什么**：附录标识取标题里的那个字，没写就按出现顺序给 A、B、C；
序号在附录内重新从 1 起；正文的章号不因为附录而跳号。

顺带钉住一条相邻的旧缺陷：**格式里没有 `{c}` 时编号是全文连续序号**，不能在每章开头
清零（那会数出 （1）（2）（1））。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from md_to_word.model.reader import read_markdown
from md_to_word.spec.parser import parse_format
from md_to_word.spec.serializer import serialize_format
from md_to_word.template.builder import build_template
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt").read_text(encoding="utf-8")

BY_CHAPTER = '---\ncrossref:\n  chapters: true\n---\n\n'


@pytest.fixture()
def template(tmp_path: Path) -> Path:
    out = tmp_path / "template.docx"
    build_template(PRESET, out)
    return out


def _numbers(out: Path) -> list[str]:
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    # 编号本身在正文里是纯文本，括号随格式模板变：中英文全半角都收
    return re.findall(r"（[^）]{1,12}）|\([^()]{1,12}\)", xml)


def _write(model, template: Path, tmp_path: Path, name: str, **kwargs) -> list[str]:
    return _numbers(write_docx(model, template, tmp_path / f"{name}.docx", **kwargs))


def test_appendix_resets_and_uses_the_label_in_the_title(template: Path, tmp_path: Path) -> None:
    """`# 附录2` → （附2-1），序号在附录内从 1 起，正文的章号不受影响。"""
    model = read_markdown(
        BY_CHAPTER + "# 第一章\n\n$$a$$ {#eq-1}\n\n# 第二章\n\n$$b$$ {#eq-2}\n\n"
        "# 附录2 补充推导\n\n$$c$$ {#eq-3}\n\n$$d$$ {#eq-4}\n"
    )
    numbers = _write(model, template, tmp_path, "ap",
                     equation_number_format="（{c}-{n}）",
                     appendix_equation_number_format="（附{c}-{n}）")

    assert numbers == ["（1-1）", "（2-1）", "（附2-1）", "（附2-2）"]


def test_written_label_wins_over_automatic_letter(template: Path, tmp_path: Path) -> None:
    """标题里写了的标识优先——`# 附录B` 就是 B，不要按顺序改成 A。"""
    model = read_markdown(
        BY_CHAPTER + "# 一\n\n$$a$$ {#eq-1}\n\n# 附录B 证明\n\n$$b$$ {#eq-2}\n"
    )
    numbers = _write(model, template, tmp_path, "labeled",
                     equation_number_format="（{c}-{n}）",
                     appendix_equation_number_format="（{c}-{n}）")

    assert numbers == ["（1-1）", "（B-1）"]


def test_unlabelled_appendix_gets_letters_in_order(template: Path, tmp_path: Path) -> None:
    model = read_markdown(
        BY_CHAPTER + "# 一\n\n$$a$$ {#eq-1}\n\n# 附录 实验数据\n\n$$b$$ {#eq-2}\n\n"
        "# 附录 补充\n\n$$c$$ {#eq-3}\n"
    )
    numbers = _write(model, template, tmp_path, "auto",
                     equation_number_format="（{c}-{n}）",
                     appendix_equation_number_format="（{c}-{n}）")

    assert numbers == ["（1-1）", "（A-1）", "（B-1）"]


def test_english_appendix_title_and_format(template: Path, tmp_path: Path) -> None:
    model = read_markdown(
        '---\ncrossref:\n  chapters: true\n---\n\n# Intro\n\n$$a$$ {#eq-1}\n\n'
        "# Appendix B Proof\n\n$$b$$ {#eq-2}\n"
    )
    numbers = _write(model, template, tmp_path, "en",
                     equation_number_format="({c}.{n})",
                     appendix_equation_number_format="(App {c}.{n})")

    assert numbers == ["(1.1)", "(App B.1)"]


def test_appendix_falls_back_to_the_body_format(template: Path, tmp_path: Path) -> None:
    """没写「附录公式编号格式」就沿用正文那一套，不发明默认。"""
    model = read_markdown(
        BY_CHAPTER + "# 一\n\n$$a$$ {#eq-1}\n\n# 附录1\n\n$$b$$ {#eq-2}\n"
    )
    numbers = _write(model, template, tmp_path, "fallback",
                     equation_number_format="（{c}-{n}）")

    assert numbers == ["（1-1）", "（1-1）"]


def test_continuous_numbering_does_not_restart_per_chapter(template: Path, tmp_path: Path) -> None:
    """格式里没有 `{c}` 时全文是一个连续序号——不能每章清零数出 （1）（2）（1）。"""
    model = read_markdown("# 一\n\n$$a$$ {#eq-1}\n\n$$b$$ {#eq-2}\n\n# 二\n\n$$c$$ {#eq-3}\n")
    numbers = _write(model, template, tmp_path, "cont")

    assert numbers == ["（1）", "（2）", "（3）"]


def test_crossref_shows_the_appendix_number(template: Path, tmp_path: Path) -> None:
    """正文里引用附录公式，显示的是附录那套编号——两处不能各算一遍。"""
    model = read_markdown(
        BY_CHAPTER + "# 一\n\n$$a$$ {#eq-x}\n\n# 附录1\n\n$$b$$ {#eq-y}\n\n见 @eq-y。\n"
    )
    xml = zipfile.ZipFile(
        write_docx(model, template, tmp_path / "ref.docx",
                   equation_number_format="（{c}-{n}）",
                   appendix_equation_number_format="（附{c}-{n}）")
    ).read("word/document.xml").decode("utf-8")

    assert "（附1-1）" in xml and "式（附1-1）" in xml


def test_appendix_format_line_round_trips() -> None:
    """新的一行要能被解析、被回写——否则「读参考 .docx 反推」会把它丢掉。"""
    spec = parse_format(PRESET + "附录公式编号格式：（附{c}-{n}）\n")
    assert spec.appendix_equation_number_format == "（附{c}-{n}）"
    assert "附录公式编号格式：（附{c}-{n}）" in serialize_format(spec)


def test_appendix_format_needs_a_serial_number() -> None:
    """`{n}` 是必写的——只有 {c} 的模板会渲染出没有序号的编号。"""
    with pytest.raises(ValueError, match="序号"):
        parse_format(PRESET + "附录公式编号格式：（附{c}-）\n")


def test_english_unlabelled_appendix_does_not_capture_ordinary_words(template: Path, tmp_path: Path) -> None:
    """`# Appendix Raw Data` / `One` / `in Detail` / `For Proof` 里的首词不是附录字母编号，不能抓成 Raw/One/in/For。"""
    model = read_markdown(
        '---\ncrossref:\n  chapters: true\n---\n\n'
        "# Introduction\n\n$$a$$ {#eq-1}\n\n"
        "# Appendix Raw Data\n\n$$b$$ {#eq-2}\n\n"
        "# Appendix One\n\n$$c$$ {#eq-3}\n\n"
        "# Appendix in Detail\n\n$$d$$ {#eq-4}\n\n"
        "# Appendix IV Proof\n\n$$e$$ {#eq-5}\n\n"
        "# 附录B—补充推导\n\n$$f$$ {#eq-6}\n"
    )
    numbers = _write(
        model,
        template,
        tmp_path,
        "en_words",
        equation_number_format="({c}.{n})",
        appendix_equation_number_format="(App {c}.{n})",
    )
    assert numbers == ["(1.1)", "(App A.1)", "(App B.1)", "(App C.1)", "(App IV.1)", "(App B.1)"]


def test_appendixes_word_is_not_misread_as_suffix_label(template: Path, tmp_path: Path) -> None:
    """`# Appendixes` 不能把结尾的 `es` 抓成附录编号 `{c}=es`。"""
    model = read_markdown(
        '---\ncrossref:\n  chapters: true\n---\n\n# Intro\n\n$$a$$ {#eq-1}\n\n# Appendixes\n\n$$b$$ {#eq-2}\n'
    )
    numbers = _write(
        model,
        template,
        tmp_path,
        "appendixes",
        equation_number_format="({c}.{n})",
        appendix_equation_number_format="(App {c}.{n})",
    )
    assert numbers == ["(1.1)", "(2.1)"]
