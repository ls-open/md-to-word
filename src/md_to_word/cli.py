"""md_to_word.cli — 跨平台命令行交互入口。"""

from __future__ import annotations

import argparse
import sys

from md_to_word.pipeline import ExportOptions, run_export_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-to-word",
        description="现代学术 Markdown 到期刊/学位规范 Word (.docx) 编译引擎",
        epilog="退出码: 0=成功 / 1=稿件或门禁问题 / 2=环境问题（缺 Quarto 或依赖）/ 3=docx 已生成但 PDF 未渲染",
    )
    parser.add_argument("input", help="输入的 Markdown 论文或报告稿件 (.md)")
    parser.add_argument("-o", "--output", help="输出的 Word 文档路径 (.docx)")
    parser.add_argument(
        "-r",
        "--requirements",
        help="格式要求文件 (.txt)；未传时优先按同目录唯一 .txt 或内置预设",
    )
    parser.add_argument(
        "--preset",
        help="内置格式预设：zh-academic（中文学术默认）或 en-nature（英文国际期刊）",
    )
    parser.add_argument("-t", "--template", help="可选：指定现成 Word 样式模板 (.docx)")
    parser.add_argument(
        "--strip-comments",
        action="store_true",
        help="导出前剔除 Markdown 中的 HTML 注释",
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="跳过导前语法与排版契约预检（不推荐）",
    )
    parser.add_argument(
        "--no-postflight",
        action="store_true",
        help="跳过产物数值防丢检查（不推荐）",
    )
    parser.add_argument(
        "--no-audit",
        action="store_true",
        help="跳过产物与格式要求逐条对账抽查",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="导出后再渲染一份 PDF 供核对（macOS + 本机 Word 专享）",
    )
    parser.add_argument(
        "--eq-number-style",
        choices=["asis", "cjk"],
        default="asis",
        help="公式编号外观：asis=原生 (1)/(1.1)；cjk=中文学位论文 （5-1）",
    )
    return parser


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

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
        eq_number_style=parsed.eq_number_style,
    )

    result = run_export_pipeline(options)

    for msg in result.messages:
        print(msg)

    if result.returncode == 2:
        for err in result.errors:
            print(f"❌ {err}", file=sys.stderr)
        print("   这是环境问题（缺渲染引擎或依赖），不是稿件问题；装好后再跑一次即可。", file=sys.stderr)
        return 2

    if result.returncode != 0 and result.returncode != 3:
        for err in result.errors:
            print(f"❌ {err}", file=sys.stderr)
        return result.returncode

    if result.returncode == 3:
        print("⚠️ docx 已正常生成，但 PDF 渲染被跳过或未完成。", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
