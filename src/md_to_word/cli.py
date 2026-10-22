"""md_to_word.cli — 跨平台命令行交互入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from md_to_word import __version__
from md_to_word.i18n import SUPPORTED, resolve_lang, t
from md_to_word.pipeline import ExportOptions, run_export_pipeline
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

    manual = Path(__file__).resolve().parent / "resources" / "manual.md"
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

Block markers (one per line, blank lines around): `{{{{< pagebreak >}}}}`, `{{{{< toc 2 >}}}}`,
`{{{{< section 页码=小写罗马 起始=1 >}}}}`.

Style names (a wrong name stops the export with a line number):
{', '.join(_style_names(ascii_only=True))}

Format requirements: without -r the built-in preset is used (zh-academic for Chinese,
--preset en-nature for English journals). One style per line, for example
`Body Text: Times New Roman 12pt not-bold not-italic justify line-spacing 1.5 space-before 0pt space-after 0pt indent 0`.
Start from a preset: copy the file below next to the manuscript and change only the lines you need.

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

块级标记（独占一行，前后留空行）：`{{{{< pagebreak >}}}}`、`{{{{< toc 2 >}}}}`、
`{{{{< section 页码=小写罗马 起始=1 >}}}}`。

样式名（写错会带行号报错）：{'、'.join(_style_names(ascii_only=False))}

格式要求：不传 -r 时用内置预设（中文 zh-academic、英文 --preset en-nature），
每一行一种样式，如 `正文：宋体/Times New Roman 小四 行距1.5倍 首行缩进2字符`。
从预设起步最省事：把下面那份拷到稿件旁，只改需要的行。

手册（完整词表、YAML、公式编号、CSL 清单、能力边界）：{manual}
内置预设：
{presets}
"""


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
    parser.add_argument("-t", "--template", help=t("cli.template", lang))
    parser.add_argument("--lang", choices=["auto", *SUPPORTED], default="auto", help=t("cli.lang", lang))
    parser.add_argument("--no-check", action="store_true", help=t("cli.no_check", lang))
    parser.add_argument("--no-postflight", action="store_true", help=t("cli.no_postflight", lang))
    parser.add_argument("--no-audit", action="store_true", help=t("cli.no_audit", lang))
    parser.add_argument("--pdf", action="store_true", help=t("cli.pdf", lang))
    parser.add_argument("-v", "--verbose", action="store_true", help=t("cli.verbose", lang))
    parser.add_argument("--contract", action="store_true", help=t("cli.contract", lang))
    parser.add_argument(
        "--version",
        action="version",
        version=f"md-to-word {__version__}",
        help=t("cli.version", lang),
    )
    return parser


def main(args: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if args is None else args)
    lang = _message_lang(argv)
    parser = build_parser(lang)
    parsed = parser.parse_args(argv)
    configure_logging("DEBUG" if parsed.verbose else "INFO", force=True)

    if parsed.contract:
        print(contract_cheatsheet(lang))
        return 0
    if not parsed.input:
        parser.error(t("cli.input_required", lang))

    options = ExportOptions(
        input_path=parsed.input,
        output_path=parsed.output,
        requirements_path=parsed.requirements,
        preset=parsed.preset,
        template_path=parsed.template,
        check_md=not parsed.no_check,
        postflight=not parsed.no_postflight,
        audit=not parsed.no_audit,
        make_pdf=parsed.pdf,
        lang=None if parsed.lang == "auto" else parsed.lang,
    )

    result = run_export_pipeline(options)

    for msg in result.messages:
        print(msg)
    # 进度走 stdout、错误走 stderr。管道里 stdout 是块缓冲的，不先 flush 的话
    # 「用了哪份要求文件」会印在报错后面，读起来像事后补的解释。
    sys.stdout.flush()

    if result.returncode != 0 and result.returncode != 3:
        for err in result.errors:
            print(f"❌ {err}", file=sys.stderr)
        return result.returncode

    if result.returncode == 3:
        print(f"⚠️ {t('pipeline.pdf_skipped', result.lang)}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
