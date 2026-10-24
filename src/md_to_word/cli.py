"""md_to_word.cli — 跨平台命令行交互入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from md_to_word import __version__
from md_to_word.i18n import SUPPORTED, resolve_lang, t
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.status import EXIT_OK, EXIT_PDF_SKIPPED, EXIT_USAGE
from md_to_word.utils.skill_utils import configure_logging


def _message_lang(argv: list[str]) -> str:
    """先粗读一遍参数，按稿件语种决定帮助文本用哪国话。

    只为把 `--help` 说清楚：完整解析还是交给 `build_parser`。读不到稿件时按项目
    主语言中文处理。
    """
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("input", nargs="?")
    pre.add_argument("--lang", default="auto")
    known, _ = pre.parse_known_args(argv)
    text = ""
    if known.input and Path(known.input).is_file():
        try:
            text = Path(known.input).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    override = None if known.lang == "auto" else known.lang
    return resolve_lang(text, override) if text else (override if override in SUPPORTED else "zh")


def _style_names(ascii_only: bool) -> list[str]:
    """每个样式取第一个名字，按词表声明顺序。

    排序会排成「一级、三级、二级」，读的人以为词表就这么乱。`ascii_only` 取英文
    正典名（`Body Text`），否则取中文名（`正文`）。
    """
    from md_to_word.spec.constants import STYLE_MAP

    seen: set[str] = set()
    names: list[str] = []
    for name, target in STYLE_MAP.items():
        if name.isascii() != ascii_only or target in seen:
            continue
        seen.add(target)
        names.append(name)
    return names


def contract_cheatsheet(lang: str = "zh") -> str:
    """稿件契约速查 + 手册与预设的真实路径。

    给「只装了包、手上没有任何文档」的调用方一个自足入口：一份够用的速查，加上
    去哪儿读全部内容、去哪儿拿一份现成的要求文件。路径从安装位置现算，不写死。
    """
    from md_to_word.config import resolve_preset_path

    # 手册按语言各一份：中文版 manual.md，英文版 manual_en.md。两份都随包发布。
    resources = Path(__file__).resolve().parent / "resources"
    manual = resources / ("manual_en.md" if lang == "en" else "manual.md")
    # 入门文档与技能入口是同一份流程（tests/test_resource_sync.py 盯着两者不许分叉）：
    # 只装 pip 包、手上没有 SKILL.md 的 Agent 从这里读“按什么顺序做”。
    guide = resources / "guide.md"
    presets = "\n".join(
        f"  {name:<12} {resolve_preset_path(name)}" for name in ("zh-academic", "en-nature")
    )
    if lang == "en":
        return f"""A manuscript = plain Markdown + three conventions
===============================================

1. Headings: # / ## / ###, consecutive levels, never skipped.
2. One line is one paragraph. To style a paragraph, start the line with
   `%% Style Name content` (no closing fence):
       %% Abstract Title Abstract
       %% Abstract This paper proposes ...
       %% Table Caption **Table 1** Comparison of methods
       %% Image Caption Figure 1 System overview
3. A numbered equation is `$$formula$$ {{#eq-label}}`, referred to as `@eq-label`.
   Citations are `[@key]`, with `bibliography: refs.bib` and `csl: apa.csl` in the YAML.

A break inside one paragraph: end the line with a backslash or two spaces (otherwise every
line is its own paragraph).

Block markers (one per line, blank lines around): `{{{{< pagebreak >}}}}`, `{{{{< toc 2 >}}}}`,
`{{{{< section page_number=lowerRoman start=1 >}}}}`.

Style names (a wrong name stops the export with a line number):
{', '.join(_style_names(ascii_only=True))}

Format requirements: without -r only a file named exactly `format.txt` beside the manuscript is
used, otherwise the built-in preset chosen by the manuscript's language (zh-academic for Chinese,
en-nature otherwise). One style per line, for example
`Body Text: Times New Roman 12pt not-bold not-italic justify line-spacing 1.5 space-before 0pt space-after 0pt indent 0`.
Starting from a preset is recommended: copy the file below next to the manuscript and change only the lines you need.

Getting-started guide (identical to SKILL.md at the skill entry; one copy suffices): {guide}
Manual (full vocabulary, YAML keys, equation numbering, CSL inventory, limits): {manual}
Built-in presets:
{presets}
"""
    return f"""稿件 = 普通 Markdown + 三条约定
================================

1. 标题用 # / ## / ###，层级连续不跳级。
2. 一行一段；要给某一段指定样式，在行首写 `%% 样式名 内容`（一行即一段，没有闭合符号）：
       %% 摘要标题 摘要
       %% 摘要 本文提出……
       %% 表题 **表 1** 各方案对照
       %% 图片题注 图 1 系统架构
3. 带编号公式写 `$$公式$$ {{#eq-标签}}`，正文用 `@eq-标签` 引用。
   文献用 `[@key]`，在 YAML 里写 `bibliography: refs.bib` 与 `csl: apa.csl`。

同一段落内换行：行尾写一个 `\\` 或两个空格（不写标记时，每一行各自成段）。

块级标记（独占一行，前后留空行）：`{{{{< pagebreak >}}}}`、`{{{{< toc 2 >}}}}`、
`{{{{< section 页码=小写罗马 起始=1 >}}}}`。

样式名（写错会带行号报错）：{'、'.join(_style_names(ascii_only=False))}

格式要求：不传 -r 时只认同目录的 format.txt，没有则用内置预设（按稿件语种：中文 zh-academic、其他 en-nature），
每一行一种样式，如 `正文：宋体/Times New Roman 小四 行距1.5倍 首行缩进2字符`。
推荐从预设起步：将下面那份复制到稿件旁，仅修改需要的行。

入门文档（与技能入口 SKILL.md 同文，读其一即可）：{guide}
手册（完整词表、YAML、公式编号、CSL 清单、能力边界）：{manual}
内置预设：
{presets}
"""


def guide_document(lang: str = "zh") -> str:
    """入门文档：与技能入口 `SKILL.md` 同一份正文（测试盯着两者不许分叉）。

    只装了包、手上没有技能目录的调用方，从这一份读"按什么顺序做"；手册仍是细节的
    唯一出处，中文稿读中文手册。
    """
    resources = Path(__file__).resolve().parent / "resources"
    text = (resources / "guide.md").read_text(encoding="utf-8")
    if lang == "zh":
        text += f"\n---\n\n中文细节见手册：{resources / 'manual.md'}\n"
    return text


def build_parser(lang: str = "zh") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-to-word",
        description=t("cli.description", lang),
        epilog=t("cli.epilog", lang),
        # 反参自己带换行：让 argparse 原样输出，别把两行压成一行
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help=t("cli.help", lang))
    parser.add_argument("input", nargs="?", help=t("cli.input", lang))
    parser.add_argument("-o", "--output", help=t("cli.output", lang))
    parser.add_argument("-r", "--requirements", help=t("cli.requirements", lang))
    parser.add_argument("--preset", help=t("cli.preset", lang))
    parser.add_argument("--lang", choices=["auto", *SUPPORTED], default="auto", help=t("cli.lang", lang))
    parser.add_argument("--no-check", action="store_true", help=t("cli.no_check", lang))
    parser.add_argument("--no-postflight", action="store_true", help=t("cli.no_postflight", lang))
    parser.add_argument("--no-audit", action="store_true", help=t("cli.no_audit", lang))
    parser.add_argument("--pdf", action="store_true", help=t("cli.pdf", lang))
    parser.add_argument("-v", "--verbose", action="store_true", help=t("cli.verbose", lang))
    parser.add_argument("--contract", action="store_true", help=t("cli.contract", lang))
    parser.add_argument("--json", dest="as_json", action="store_true", help=t("cli.json", lang))
    parser.add_argument("--guide", action="store_true", help=t("cli.guide", lang))
    parser.add_argument(
        "--version",
        action="version",
        version=f"md-to-word {__version__}",
        help=t("cli.version", lang),
    )
    return parser


def _run_init(args: list[str], lang: str) -> int:
    """`md-to-word init [目录]`：第一条命令就把可导出的文件放好。"""
    from md_to_word.scaffold import run_init

    parser = argparse.ArgumentParser(
        prog="md-to-word init",
        description=t("init.description", lang),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("directory", nargs="?", default=".", help=t("init.directory", lang))
    parser.add_argument("--preset", help=t("init.preset", lang))
    parser.add_argument("--force", action="store_true", help=t("init.force", lang))
    parser.add_argument("--lang", choices=["auto", *SUPPORTED], default="auto")
    parsed = parser.parse_args(args)
    effective = lang if parsed.lang == "auto" else parsed.lang
    return run_init(Path(parsed.directory), preset=parsed.preset, force=parsed.force, lang=effective)


def main(args: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if args is None else args)
    lang = _message_lang(argv)
    if argv and argv[0] == "init":
        return _run_init(argv[1:], lang)
    parser = build_parser(lang)
    parsed = parser.parse_args(argv)
    configure_logging("DEBUG" if parsed.verbose else "INFO", force=True)

    if parsed.guide:
        print(guide_document(lang))
        return EXIT_OK
    if parsed.contract:
        print(contract_cheatsheet(lang))
        return EXIT_OK
    if not parsed.input:
        # 没有参数时给人一段能照着敲的简述（描述 + 三条示例 + 去哪儿读全部），
        # 而不是 argparse 的 usage 加一句 "the following arguments are required"。
        print(t("cli.brief", lang, version=__version__), file=sys.stderr)
        return EXIT_USAGE

    options = ExportOptions(
        input_path=parsed.input,
        output_path=parsed.output,
        requirements_path=parsed.requirements,
        preset=parsed.preset,
        check_md=not parsed.no_check,
        postflight=not parsed.no_postflight,
        audit=not parsed.no_audit,
        make_pdf=parsed.pdf,
        lang=None if parsed.lang == "auto" else parsed.lang,
    )

    result = run_export_pipeline(options)

    if parsed.as_json:
        # 给程序与 Agent 用：stdout 只有这一行，键名是契约（不随版本改），值原样透传——
        # 消息按稿件语种可能中可能英，解析方读的是键，不是措辞。进度与报错仍走 stderr。
        print(json.dumps({
            "ok": result.ok,
            "returncode": result.returncode,
            "input": str(parsed.input),
            "output": str(result.output_docx) if result.output_docx else None,
            "pdf": str(result.output_pdf) if result.output_pdf else None,
            "lang": result.lang,
            "messages": list(result.messages),
            "errors": list(result.errors),
        }, ensure_ascii=False))
        return result.returncode

    for msg in result.messages:
        print(f"⚠️ {msg}" if msg in result.warnings else msg)
    # 进度走 stdout、错误走 stderr。管道里 stdout 是块缓冲的，不先 flush 的话
    # 「用了哪份要求文件」会印在报错后面，读起来像事后补的解释。
    sys.stdout.flush()

    if result.returncode not in (EXIT_OK, EXIT_PDF_SKIPPED):
        for err in result.errors:
            print(f"❌ {err}", file=sys.stderr)
        return result.returncode

    if result.returncode == EXIT_PDF_SKIPPED:
        print(f"⚠️ {t('pipeline.pdf_skipped', result.lang)}", file=sys.stderr)
        return EXIT_PDF_SKIPPED

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
