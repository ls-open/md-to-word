#!/usr/bin/env python3
"""check_md.py — 导前预检的命令行入口（实现见 md_to_word.validator.check）。

保留这个文件，是因为文档里 `python3 scripts/check_md.py 稿件.md -t 模板.docx -r 要求.txt`
是给人和 Agent 直接调的命令；实现只有一份，在包里。

退出码：0=通过（可能带「未校验」项）/ 1=发现问题，阻断导出
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from md_to_word.validator.check import validate_manuscript  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="check_md.py",
        description="导出前预检：拦下会造成静默失败的稿件写法",
    )
    parser.add_argument("md", help="待检查的 Markdown 稿件")
    parser.add_argument("-f", "--format", dest="format_path", help="（可选）格式要求文件，用于校验稿件结构是否有对应样式")
    parser.add_argument("-r", "--requirements", dest="format_path", help=argparse.SUPPRESS)
    args = parser.parse_args()

    report = validate_manuscript(
        args.md,
        spec_path=args.format_path,
    )

    for warning in report.warnings:
        print(f" ⚠ {warning}")
    if report.errors:
        print(f"❌ 发现 {len(report.errors)} 个问题，已终止（请按上方提示修复后重新导出）:")
        for error in report.errors:
            print(f" ✗ {error}")
        return 1

    print("✅ 已跑的检查全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
