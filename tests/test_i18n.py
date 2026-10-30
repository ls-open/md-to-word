"""面向用户的消息双语。

判据不是"每条都有英文"，而是：**同一份稿件，中文用户与英文用户读到的进度与结论
等价**，且不会因为 `%% 表题` 这类词表写法把英文稿认成中文稿。
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Formatter

import pytest

from md_to_word.cli import build_parser
from md_to_word.i18n import _MESSAGES, resolve_lang, t
from md_to_word.spec.parser import parse_format

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("key", sorted(_MESSAGES))
def test_every_message_has_both_languages(key: str) -> None:
    zh, en = _MESSAGES[key]
    assert zh.strip() and en.strip(), f"{key} 缺一边"
    assert zh != en, f"{key} 中英两栏一模一样，八成是忘了翻"


_NUMERIC_SPECS = set("gGeEfFdD%")   # `{width:g}` / `{content:.2f}` 这类得喂数字


def _fields(text: str) -> dict[str, object]:
    """这条消息的占位符 → 一个能被格式化的示例值（按格式说明符选字符串还是数字）。

    `{width=8cm}` 这种是代码字面量、不是占位符（`t()` 也不会拿它去 format），
    一律当作「这条没有占位符」处理。
    """
    out: dict[str, object] = {}
    for _, name, spec, _ in Formatter().parse(text):
        if not name:
            continue
        if not name.isidentifier():
            return {}
        out[name] = 1 if spec and spec[-1] in _NUMERIC_SPECS else "sample"
    return out


def test_messages_format_without_keyword_errors() -> None:
    """带占位符的条目必须能被格式化——少一个参数会在导出中途炸掉。"""
    for key, (zh, en) in _MESSAGES.items():
        for text in (zh, en):
            fields = _fields(text)
            if fields:  # 没有占位符的条目不进 format（`{{< pagebreak >}}` 得原样留着）
                text.format(**fields)


def test_gate_messages_with_code_syntax_keep_their_text() -> None:
    """既有占位符、又带代码字面量的几条门禁消息，逐字锁住。"""
    assert t("gate.crossref.undefined", "zh", key="eq-x") == (
        "引用了 eq-x，但稿子里没有 {#eq-x} 这个标签定义"
    )
    assert t("gate.latex.pagebreak", "zh", line=3) == (
        "行 3: 发现 LaTeX 分页命令（请改用 `{{< pagebreak >}}`）"
    )
    assert t("gate.latex.tag", "zh", snippet="E=mc^2") == (
        "发现 `\\tag{}`，这不是本工具的编号写法，整条公式会退化成字面文本（E=mc^2）；"
        "删掉 `\\tag{X}`，改写成 `$$…$$ {#eq-标签}`，编号由 crossref 生成"
    )
    assert t("gate.equation.chapters", "zh", fmt="（{c}-{n}）") == (
        "要求文件的「公式编号格式」是 （{c}-{n}），里面有 {c}（章号），"
        "但稿件 YAML 的 crossref 下没有 chapters: true。二选一："
        "在 `crossref:` 下加 `chapters: true`，或把格式改成不含 {c} 的写法（如 （{n}））"
    )
    # 不带占位符的那条不格式化，双花括号就是最终产物
    assert "`{{< pagebreak >}}`" in t("gate.dialect.html", "zh")
    assert "`{{< pagebreak >}}`" in t("gate.dialect.html", "en")


def test_style_examples_follow_the_message_language() -> None:
    """报错里举例的样式名跟语言走，且中文名取自 `STYLE_MAP` 而不是手抄。"""
    from md_to_word.i18n import style_examples

    assert style_examples("zh") == "摘要 / 关键词 / 表题 / 表注 / 参考文献标题"
    assert style_examples("en") == "Abstract / Keywords / Table Caption / Table Note / References Title"


def test_language_follows_the_manuscript() -> None:
    assert resolve_lang("这是一份中文稿件。") == "zh"
    assert resolve_lang("This is an English manuscript.") == "en"
    # 英文稿里出现中文样式名（词表写法）不算中文稿
    assert resolve_lang("%% 表题 Table 1\n\n# Introduction\n\nEnglish body.\n") == "en"


def test_language_override_wins() -> None:
    assert resolve_lang("中文正文", "en") == "en"
    assert resolve_lang("English body", "zh") == "zh"
    assert resolve_lang("English body", "auto") == "en"


def test_cli_help_follows_the_manuscript(tmp_path: Path) -> None:
    zh = tmp_path / "zh.md"
    zh.write_text('---\n---\n\n# 一 引言\n\n中文正文一段。\n', encoding="utf-8")
    en = tmp_path / "en.md"
    en.write_text('---\n---\n\n# Introduction\n\nEnglish body.\n', encoding="utf-8")

    from md_to_word.cli import _message_lang

    assert _message_lang([str(zh)]) == "zh"
    assert _message_lang([str(en)]) == "en"
    assert _message_lang([str(zh), "--lang", "en"]) == "en"


def test_parser_language_switches_every_help_line() -> None:
    english = build_parser("en").format_help()
    chinese = build_parser("zh").format_help()
    assert "Compile Markdown into Word" in english
    assert "把 Markdown 编译成符合声明格式的 Word" in chinese
    assert "把 Markdown" not in english


def test_reminder_is_localized_end_to_end(tmp_path: Path) -> None:
    from md_to_word.pipeline import ExportOptions, run_export_pipeline

    manuscript = tmp_path / "m.md"
    manuscript.write_text('---\n---\n\n# Introduction\n\nEnglish body.\n', encoding="utf-8")
    result = run_export_pipeline(
        ExportOptions(input_path=manuscript, output_path=tmp_path / "o.docx", preset="en-nature")
    )
    assert result.returncode == 0, result.errors
    assert result.lang == "en"
    assert any("still requires a manual check in Word" in m for m in result.messages), result.messages


# ══════════════════════════════════════════════════════════════════════
# 英文诊断里的「该写的那一行」必须真的能被解析
#
# 英文提示教人写 `Table: center three-line …`，如果 parser 不认这串词，作者照着改还是
# 生成不了模板——比看中文更糟。所以词表里凡是给出**要求文件写法**的英文条目，都要在
# 这里过一遍 `parse_format`。
# ══════════════════════════════════════════════════════════════════════

_CJK = re.compile(r"[一-鿿]")
# 反引号里的「样式名: 属性」——消息里嵌的要求文件示例
_REQ_EXAMPLE_RE = re.compile(r"`([A-Z][A-Za-z0-9 ]*: [^`]+)`")


def _english_requirement_examples() -> list[tuple[str, str]]:
    """词表里所有英文要求文件示例 → [(key, 那一行)]。"""
    found: list[tuple[str, str]] = []
    for key, (_zh, en) in _MESSAGES.items():
        if not key.startswith(("template.", "gate.")):
            continue
        if key.startswith("gate.yaml.form."):
            continue  # 这些是稿件里的 `%%` 样式行，不是要求文件
        if key.startswith("template.example."):
            found.append((key, en))
        for match in _REQ_EXAMPLE_RE.finditer(en):
            line = match.group(1)
            # `Style: properties` 是**语法的**占位说明，不是可解析的示例；真示例在同一条里
            if line.split(":", 1)[1].strip() != "properties":
                found.append((key, line))
    return found


def test_english_requirement_examples_are_parseable() -> None:
    examples = _english_requirement_examples()
    assert examples, "没抽到任何英文示例——抽取规则和词表脱节了"
    for key, line in examples:
        assert not _CJK.search(line), f"{key}: 英文示例里混进了中文：{line}"
        try:
            parse_format(line)
        except Exception as exc:  # noqa: BLE001 —— 任何异常都说明这行教错了
            raise AssertionError(f"{key}: 示例解析不了 -> {line}\n{exc}") from exc


def test_english_field_hints_are_parseable_properties() -> None:
    """字段提示是属性片段：塞进一行样式里必须解析得动，而且真的落到该落的属性上。"""
    spec = parse_format("Title: " + " ".join(
        _MESSAGES[f"template.hint.{field}"][1] for field in
        ("font_name", "font_size", "alignment", "line_spacing", "space_before",
         "space_after", "indent", "bold", "italic")
    ))
    row = spec.styles[0]
    for field in ("font_name", "font_size", "alignment", "line_spacing",
                  "space_before", "space_after", "indent", "bold", "italic"):
        assert field in row, f"英文提示没解析出 {field}：{_MESSAGES[f'template.hint.{field}'][1]}"


def test_no_duplicate_keys_in_messages_source() -> None:
    """_MESSAGES 字典源码中严禁出现重复定义的 key。"""
    import ast
    i18n_path = REPO_ROOT / "src" / "md_to_word" / "i18n.py"
    tree = ast.parse(i18n_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "_MESSAGES":
            keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
            duplicates = [k for k in set(keys) if keys.count(k) > 1]
            assert not duplicates, f"_MESSAGES 包含重复定义的 key: {duplicates}"



def test_every_literal_key_used_in_code_exists() -> None:
    """代码里写字面量的 `t("...")` 必须查得到 —— 查不到就是运行时 KeyError。

    只查字面量：`t(feat_key)`、`t(f"audit.cat.{key}")` 这类拼出来的键交给各自的
    调用点自证（它们的前缀散落在常量表里，静态追不全，追了就成一堆误报）。
    """
    import ast

    missing: list[str] = []
    for path in sorted((REPO_ROOT / "src" / "md_to_word").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "t" and node.args):
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if first.value not in _MESSAGES:
                    rel = path.relative_to(REPO_ROOT)
                    missing.append(f"{rel}:{node.lineno} → {first.value}")
    assert not missing, "这些 t() 的字面量键在 _MESSAGES 里不存在：\n" + "\n".join(missing)
