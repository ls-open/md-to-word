"""导前预检的门禁回归。

这四道门禁在 V2 重写校验器时丢过一次（结构样式缺失、图片宽度超过版心、
`\\tag{}` 公式编号、custom-style 与模板比对），而当时两条流水线各走一半，
问题在 CLI 路径上无人察觉。下面每条用例锁住一道门禁的判定，防止再丢。

比对的是「拦不拦」，不是文案——文案可以改，判定必须只有一套。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from md_to_word.template.builder import build_template
from md_to_word.validator.check import validate_manuscript

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "presets" / "zh-academic.txt"
FIGURE = REPO_ROOT / "demo" / "01_chinese_thesis" / "figures" / "qa_pipeline.png"

BASE_YAML = '---\n---\n\n# 一 引言\n\n正文一段。\n'
CROSSREF_YAML = (
    '---\ncrossref:\n  eq-prefix: "式"\n  fig-prefix: "图"\n'
    '  tbl-prefix: "表"\n---\n\n# 一 引言\n'
)


def _requirements_without(*rows: str) -> str:
    """内置预设删掉指定前缀的行——模拟「要求文件漏声明某结构」。"""
    kept = [
        line
        for line in PRESET.read_text(encoding="utf-8").splitlines()
        if not any(line.startswith(row) for row in rows)
    ]
    return "\n".join(kept) + "\n"


# name -> (稿件正文, 要删掉的要求文件行；None=不给要求文件, 期望是否拦)
CASES = {
    "clean": (BASE_YAML, None, False),
    "table_without_style_rows": (
        BASE_YAML
        + "\n%% 表题 表 1 测试\n| 甲 | 乙 |\n|:--|:--|\n| 1 | 2 |\n",
        ("表格：", "表头："),
        True,
    ),
    "latex_tag": (BASE_YAML + "\n$$E = mc^2 \\tag{1}$$\n", None, True),
    # 图片宽度超版心只提醒：图还在页内，看得见，不阻断
    "image_wider_than_text_block": (
        BASE_YAML + "\n![](figures/qa_pipeline.png){width=30cm}\n",
        (),  # 版心要从要求文件算，故必须给文件，但不删任何行
        False,
    ),
    "citation_without_bibliography": (BASE_YAML + "\n见 [@smith2024]。\n", None, True),
    "crossref_without_bibliography": (
        CROSSREF_YAML + "\n$$E = mc^2$$ {#eq-a}\n\n见 @eq-a。\n",
        None,
        False,
    ),
    "undefined_crossref": (CROSSREF_YAML + "\n见 @eq-missing。\n", None, True),
    # 引擎只认正文的样式行：YAML 里的摘要/关键词没有任何排版位置，静默丢一段摘要
    # 比报错难查得多，所以这里拦下来并说清该写成什么样。
    "yaml_abstract": (
        '---\nabstract: |\n  摘要正文。\n---\n\n# 一 引言\n\n正文。\n',
        None,
        True,
    ),
    "yaml_keywords": ('---\nkeywords: [甲, 乙]\n---\n\n正文。\n', None, True),
    # 标题、作者、日期同理：位置由作者定（可能排在封面之后），YAML 没有位置
    "yaml_title": ('---\ntitle: "题目"\n---\n\n正文。\n', None, True),
    "yaml_author": ('---\nauthor: [张三]\n---\n\n正文。\n', None, True),
    # 正文写法才是正典
    "title_as_style_line": ('%% 文档标题 题目\n\n# 一 引言\n\n正文。\n', None, False),
    # 题注写在 `![…]` 里：引擎不把它当题注排，等于丢内容
    "caption_in_alt": (
        BASE_YAML + "\n![图 1-1 框架图](figures/qa_pipeline.png){width=10cm}\n",
        None,
        True,
    ),
    # 正规写法：独立题注段 + 只留无障碍文字的图片行
    "caption_as_style_line": (
        BASE_YAML + "\n%% 图片题注 图 1-1 框架图\n\n![](figures/qa_pipeline.png){width=10cm}\n",
        None,
        False,
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_preflight_verdict(name: str, tmp_path: Path) -> None:
    body, dropped_rows, expected_blocked = CASES[name]
    (tmp_path / "manuscript.md").write_text(body, encoding="utf-8")
    (tmp_path / "figures").mkdir(exist_ok=True)
    if FIGURE.exists():
        shutil.copy(FIGURE, tmp_path / "figures" / "qa_pipeline.png")

    requirements = None
    if dropped_rows is not None:
        requirements = tmp_path / "requirements.txt"
        requirements.write_text(_requirements_without(*dropped_rows), encoding="utf-8")

    report = validate_manuscript(tmp_path / "manuscript.md", spec_path=requirements)

    assert report.valid is not expected_blocked, (
        f"{name}: 期望{'拦' if expected_blocked else '放'}，实际"
        f"{'拦' if not report.valid else '放'}：{report.errors}"
    )


def test_custom_style_must_exist_in_template(tmp_path: Path) -> None:
    """模板里没有该样式，段落只能退回普通段落，格式不生效；不认识的样式名预检直接拦。"""
    template = tmp_path / "template.docx"
    build_template(PRESET.read_text(encoding="utf-8"), template)

    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text(
        BASE_YAML + "\n%% 不存在的样式 正文。\n", encoding="utf-8"
    )

    report = validate_manuscript(manuscript, template_docx=template)
    assert not report.valid
    assert any("不存在的样式" in error for error in report.errors)


def test_visible_issues_warn_instead_of_blocking(tmp_path: Path) -> None:
    """看得见的问题只提醒：多一页、宽度被钳、题注离得远，作者可以自行收尾。"""
    (tmp_path / "figures").mkdir()
    if FIGURE.exists():
        shutil.copy(FIGURE, tmp_path / "figures" / "qa_pipeline.png")
    manuscript = tmp_path / "m.md"
    manuscript.write_text(
        '---\n---\n\n# 一 引言\n\n### 跳级标题\n\n正文。\n\n'
        "%% 表题 表 1 测试\n\n正文隔开了题注和表格。\n\n| 甲 | 乙 |\n|:--|:--|\n| 1 | 2 |\n",
        encoding="utf-8",
    )
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(PRESET.read_text(encoding="utf-8"), encoding="utf-8")

    report = validate_manuscript(manuscript, spec_path=requirements)
    assert report.valid, f"看得见的问题不该阻断：{report.errors}"
    assert any("标题" in w for w in report.warnings)
    assert any("题注" in w for w in report.warnings)


def test_bibliography_without_title_warns(tmp_path: Path) -> None:
    """文献列表是引擎生成的，抬头得稿子自己写——没写只提醒，内容没丢。"""
    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{smith2024,\n  author={Smith, J.},\n  title={T},\n  year={2024},\n  journal={J}\n}\n",
        encoding="utf-8",
    )
    manuscript = tmp_path / "m.md"
    manuscript.write_text(
        '---\nbibliography: refs.bib\ncsl: apa.csl\n---\n\n# 一 引言\n\n见 [@smith2024]。\n',
        encoding="utf-8",
    )

    report = validate_manuscript(manuscript)
    assert report.valid, report.errors
    assert any("文献区标题" in w for w in report.warnings), report.warnings


def test_reference_section_title_in_yaml_only_warns(tmp_path: Path) -> None:
    """写 YAML 的 reference-section-title 不拦：抬头缺失只影响观感，内容没丢。"""
    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{smith2024,\n  author={Smith, J.},\n  title={T},\n  year={2024},\n  journal={J}\n}\n",
        encoding="utf-8",
    )
    manuscript = tmp_path / "m.md"
    manuscript.write_text(
        '---\nbibliography: refs.bib\ncsl: apa.csl\n'
        'reference-section-title: 参考文献\n---\n\n# 一 引言\n\n见 [@smith2024]。\n',
        encoding="utf-8",
    )

    report = validate_manuscript(manuscript)
    assert report.valid, report.errors
    assert any("reference-section-title" in w for w in report.warnings), report.warnings


# ══════════════════════════════════════════════════════════════════════
# 门禁消息的语种
#
# 英文作者被拦下时必须读到英文：提示里的样式名举例也得是 `Abstract` 而不是「摘要」。
# 判定与语言无关（上面那批用例锁的是判定），这里锁的是「同一份稿子换个读者，读到
# 等价的话」。
# ══════════════════════════════════════════════════════════════════════

CJK_RE = re.compile(r"[一-鿿]")

# 一份稿件同时踩四道阻断门禁：未定义交叉引用、图片不存在、未知样式名、
# `[@key]` 却没有 bibliography。中英各写一份，结构一一对应。
GATE_BODY = {
    "en": (
        '---\n---\n\n# 1 Introduction\n\n%% NoSuchStyleName hello\n\n'
        "See [@missing2020] and @eq-nowhere.\n\n![](nope.png)\n"
    ),
    "zh": (
        '---\n---\n\n# 1 引言\n\n%% 不存在的样式名 你好\n\n'
        "见 [@missing2020] 与 @eq-nowhere。\n\n![](nope.png)\n"
    ),
}


def _gate_report(tmp_path: Path, lang: str) -> list[str]:
    manuscript = tmp_path / f"m_{lang}.md"
    manuscript.write_text(GATE_BODY[lang], encoding="utf-8")
    report = validate_manuscript(manuscript, lang=lang)
    assert not report.valid, f"{lang}: 这份稿子应当被拦下"
    return report.errors + report.warnings


def test_english_manuscript_gets_english_gate_messages(tmp_path: Path) -> None:
    messages = _gate_report(tmp_path, "en")
    joined = "\n".join(messages)

    assert "cross-reference target missing" in joined, joined
    assert "image file not found" in joined, joined
    assert "unknown style name" in joined, joined
    assert "no `bibliography:`" in joined, joined
    # 中文一个都不能漏进来（含样式名举例）
    assert not CJK_RE.search(joined), [m for m in messages if CJK_RE.search(m)]


def test_chinese_manuscript_keeps_chinese_gate_messages(tmp_path: Path) -> None:
    messages = _gate_report(tmp_path, "zh")
    joined = "\n".join(messages)

    assert "交叉引用缺失目标" in joined, joined
    assert "图片文件不存在" in joined, joined
    assert "不认识样式名" in joined, joined
    assert "但稿件未声明 `bibliography:`" in joined, joined
    # 中文消息里不该冒出英文句子（bib key 一类标识符除外）
    assert "cross-reference target missing" not in joined
    assert "image file not found" not in joined


def test_style_name_examples_follow_the_manuscript_language(tmp_path: Path) -> None:
    """同一道「样式名不认识」门禁，中文稿举中文名，英文稿举正典名。"""
    en = "\n".join(_gate_report(tmp_path, "en"))
    zh = "\n".join(_gate_report(tmp_path, "zh"))

    assert "Abstract / Keywords / Table Caption / Table Note / References Title" in en
    assert "摘要 / 关键词 / 表题 / 表注 / 参考文献标题" in zh


def test_gate_language_does_not_change_the_verdict(tmp_path: Path) -> None:
    """语种只换措辞：同一条判据的中英两栏必须一起拦、一起放。"""
    cases = (
        ("---\n---\n\n# 1 Introduction\n\nSee [@missing2020].\n",
         "---\n---\n\n# 1 引言\n\n见 [@missing2020]。\n"),
        ("---\n---\n\n# 1 Introduction\n\nSee @eq-nowhere.\n",
         "---\n---\n\n# 1 引言\n\n见 @eq-nowhere。\n"),
        ("---\n---\n\n# 1 Introduction\n\n%% BadStyleName hello\n",
         "---\n---\n\n# 1 引言\n\n%% 不存在的样式名 你好\n"),
        ("---\n---\n\n# 1 Introduction\n\n![](nope.png)\n",
         "---\n---\n\n# 1 引言\n\n![](nope.png)\n"),
        ("---\n---\n\n# 1 Introduction\n\nBody text.\n",
         "---\n---\n\n# 1 引言\n\n正文一段。\n"),
    )
    for i, (en_body, zh_body) in enumerate(cases):
        verdicts = {}
        for lang, body in (("en", en_body), ("zh", zh_body)):
            manuscript = tmp_path / f"v{i}_{lang}.md"
            manuscript.write_text(body, encoding="utf-8")
            verdicts[lang] = validate_manuscript(manuscript, lang=lang).valid
        assert verdicts["en"] == verdicts["zh"], f"case {i}: {verdicts}"


def test_pipeline_passes_the_manuscript_language_to_the_gate(tmp_path: Path) -> None:
    """端到端：英文稿经流水线被拦下时，报错是英文（`lang` 一路传到门禁）。"""
    from md_to_word.pipeline import ExportOptions, run_export_pipeline

    manuscript = tmp_path / "paper.md"
    manuscript.write_text(
        '---\n---\n\n# 1 Introduction\n\nSee [@missing2020].\n', encoding="utf-8"
    )
    result = run_export_pipeline(
        ExportOptions(input_path=manuscript, output_path=tmp_path / "o.docx", preset="en-nature")
    )
    assert result.returncode == 1
    joined = "\n".join(result.errors)
    assert "no `bibliography:`" in joined, joined
    assert not CJK_RE.search(joined), result.errors


# ══════════════════════════════════════════════════════════════════════
# 文献区标题：认名字走词表，别只认中文
#
# 曾经写成 `^%%\s*参考文献标题\s` 的中文字面量正则：英文稿写 `%% References Title …`
# 时文献列表其实生成成功，预检却还提醒「没写抬头」，而让他补的就是他已写的那一行——
# 按提示改永远清不掉。
# ══════════════════════════════════════════════════════════════════════

BIB_REF = "@article{smith2024,\n  author={Smith, J.},\n  title={T},\n  year={2024},\n  journal={J}\n}\n"


def _reference_title_report(tmp_path: Path, lang: str, title_line: str | None):
    (tmp_path / "refs.bib").write_text(BIB_REF, encoding="utf-8")
    body = "# 1 Introduction\n\nSee [@smith2024].\n" if lang == "en" else "# 1 引言\n\n见 [@smith2024]。\n"
    if title_line:
        body += f"\n{title_line}\n"
    manuscript = tmp_path / f"m_{lang}.md"
    manuscript.write_text(
        f"---\nbibliography: refs.bib\ncsl: apa.csl\n---\n\n{body}", encoding="utf-8"
    )
    return validate_manuscript(manuscript, lang=lang)


@pytest.mark.parametrize("lang,title_line", [
    ("en", "%% References Title References"),
    ("en", "%% Bibliography Title References"),   # 词表里的别名
    ("zh", "%% 参考文献标题 参考文献"),
])
def test_reference_section_title_accepts_every_vocabulary_spelling(
    tmp_path: Path, lang: str, title_line: str
) -> None:
    """词表里指向 `References Title` 的写法都算写了抬头——提醒不该对着已写的行喊。"""
    report = _reference_title_report(tmp_path, lang, title_line)
    assert not any("文献区标题" in w or "reference-section title" in w for w in report.warnings), \
        report.warnings


@pytest.mark.parametrize("lang,missing", [("en", "reference-section title"), ("zh", "文献区标题")])
def test_missing_reference_section_title_warns_in_the_right_language(
    tmp_path: Path, lang: str, missing: str
) -> None:
    report = _reference_title_report(tmp_path, lang, None)
    assert any(missing in w for w in report.warnings), report.warnings
    assert report.valid, report.errors


# ══════════════════════════════════════════════════════════════════════
# 写出器 / 公式 / 文献渲染的报错也得跟语言走
#
# 这些异常的原文会经 `pipeline.unsupported` / `pipeline.csl_error` 露给用户。外壳双语了、
# 里面还是中文，英文作者看到的仍是半截话。
# ══════════════════════════════════════════════════════════════════════

def test_writer_errors_follow_the_language(tmp_path: Path) -> None:
    from md_to_word.model.reader import read_markdown
    from md_to_word.template.builder import build_template
    from md_to_word.writer import UnsupportedFeature, write_docx

    template = tmp_path / "tpl.docx"
    build_template(PRESET.read_text(encoding="utf-8"), template)

    # 交叉引用指向不存在的标签：写出器是最后一道，按语言报错
    for lang, fragment in (("en", "the label eq-nowhere does not exist"),
                           ("zh", "指向的标签不存在")):
        model = read_markdown("见 @eq-nowhere。\n")
        with pytest.raises(UnsupportedFeature) as exc:
            write_docx(model, template, tmp_path / f"{lang}.docx", lang=lang)
        message = str(exc.value)
        assert fragment in message, message
        assert not (CJK_RE.search(message) if lang == "en" else ""), message


def test_math_errors_follow_the_language() -> None:
    from md_to_word.transform.mathml2omml import UnsupportedMath, latex_to_omml, mathml_to_omml

    # 没覆盖的 MathML 元素
    mathml = "<math><reallweird/></math>"
    with pytest.raises(UnsupportedMath) as exc:
        mathml_to_omml(mathml, "en")
    assert "unsupported MathML element: reallweird" in str(exc.value), str(exc.value)
    assert not CJK_RE.search(str(exc.value))

    with pytest.raises(UnsupportedMath) as exc:
        mathml_to_omml(mathml, "zh")
    assert "尚未支持的 MathML 元素" in str(exc.value), str(exc.value)

    # LaTeX 解析失败（`\frac{1}{` 括号不闭合，latex2mathml 直接抛）
    with pytest.raises(UnsupportedMath) as exc:
        latex_to_omml(r"\frac{1}{", "en")
    assert "LaTeX could not be parsed" in str(exc.value), str(exc.value)
    assert not CJK_RE.search(str(exc.value))


def test_citation_errors_follow_the_language(tmp_path: Path) -> None:
    from md_to_word.config import default_csl_path
    from md_to_word.transform.citations import CitationEngine, CitationError

    csl = default_csl_path("# Introduction\n\nBody.\n")
    for lang, fragment in (("en", "the bibliography has no usable entries"),
                           ("zh", "文献库里没有可用条目")):
        with pytest.raises(CitationError) as exc:
            CitationEngine("", csl, lang)
        assert fragment in str(exc.value), str(exc.value)


def test_pipeline_reports_writer_failure_in_the_manuscript_language(tmp_path: Path) -> None:
    """端到端：跳过门禁、让写出器自己撞上未定义的交叉引用，理由也必须是英文。"""
    from md_to_word.pipeline import ExportOptions, run_export_pipeline

    manuscript = tmp_path / "paper.md"
    manuscript.write_text(
        '---\n---\n\n# 1 Introduction\n\nSee @eq-nowhere.\n', encoding="utf-8"
    )
    result = run_export_pipeline(
        ExportOptions(
            input_path=manuscript, output_path=tmp_path / "o.docx",
            preset="en-nature", check_md=False,
        )
    )
    assert result.returncode == 1
    joined = "\n".join(result.errors)
    assert "the label eq-nowhere does not exist" in joined, joined
    assert not CJK_RE.search(joined), result.errors


def test_toc_depth_overflow_errors_instead_of_crashing(tmp_path: Path) -> None:
    """`{{< toc 99 >}}` 以前会带着中文 traceback 崩掉；现在走正常的「写不出来」路径。"""
    from md_to_word.pipeline import ExportOptions, run_export_pipeline

    for lang, fragment in (("en", "the TOC depth must be between 1 and 9; got 99"),
                           ("zh", "目录收录级数要在 1–9 之间，收到 99")):
        manuscript = tmp_path / f"toc_{lang}.md"
        body = "# 1 Introduction\n\nBody.\n" if lang == "en" else "# 一 引言\n\n正文。\n"
        manuscript.write_text(
            f"---\n---\n\n{body}\n{{{{< toc 99 >}}}}\n", encoding="utf-8"
        )
        result = run_export_pipeline(
            ExportOptions(
                input_path=manuscript, output_path=tmp_path / f"o_{lang}.docx",
                preset="en-nature" if lang == "en" else "zh-academic",
            )
        )
        assert result.returncode == 1, result.errors
        joined = "\n".join(result.errors)
        assert fragment in joined, joined
