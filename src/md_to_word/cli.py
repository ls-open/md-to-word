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


def build_parser(lang: str = "zh") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-to-word",
        description=t("cli.description", lang),
        epilog=t("cli.exit_codes", lang),
    )
    parser.add_argument("input", help=t("cli.input", lang))
    parser.add_argument("-o", "--output", help=t("cli.output", lang))
    parser.add_argument("-r", "--requirements", help=t("cli.requirements", lang))
    parser.add_argument("--preset", help=t("cli.preset", lang))
    parser.add_argument("-t", "--template", help=t("cli.template", lang))
    parser.add_argument("--lang", choices=["auto", *SUPPORTED], default="auto", help=t("cli.lang", lang))
    parser.add_argument("--strip-comments", action="store_true", help=t("cli.strip_comments", lang))
    parser.add_argument("--no-check", action="store_true", help=t("cli.no_check", lang))
    parser.add_argument("--no-postflight", action="store_true", help=t("cli.no_postflight", lang))
    parser.add_argument("--no-audit", action="store_true", help=t("cli.no_audit", lang))
    parser.add_argument("--pdf", action="store_true", help=t("cli.pdf", lang))
    parser.add_argument("--version", action="version", version=f"md-to-word {__version__}")
    return parser


def main(args: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if args is None else args)
    configure_logging()
    lang = _message_lang(argv)
    parser = build_parser(lang)
    parsed = parser.parse_args(argv)

    options = ExportOptions(
        input_path=parsed.input,
        output_path=parsed.output,
        requirements_path=parsed.requirements,
        preset=parsed.preset,
        template_path=parsed.template,
        strip_comments=parsed.strip_comments,
        check_md=not parsed.no_check,
        postflight=not parsed.no_postflight,
        audit=not parsed.no_audit,
        make_pdf=parsed.pdf,
        lang=None if parsed.lang == "auto" else parsed.lang,
    )

    result = run_export_pipeline(options)

    for msg in result.messages:
        print(msg)

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
