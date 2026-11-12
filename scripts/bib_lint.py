#!/usr/bin/env python3
"""bib_lint.py — `.bib` 文献库体检的命令行入口（实现见 md_to_word.utils.bib_lint）。

文献表走样的多数起因不在样式文件，而在 .bib 本身：从知网、Google Scholar、DBLP 混导
出来的库常有作者没用 `and` 分隔、缺刊名、标题里的缩写没加大括号。这个脚本用**导出时那套
解析器**先过一遍，把会印成空白或印成另一种样子的地方指出来。

用法：
    python3 scripts/bib_lint.py refs.bib
    python3 scripts/bib_lint.py demo/01_chinese_thesis/references.bib

退出码：0=没有错误（可能有提示）/ 1=有错误
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from md_to_word.utils.bib_lint import lint_bibtex_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bib_lint.py",
        description=".bib 体检：用导出时的解析器查，指出会印成空白或走样的地方",
    )
    parser.add_argument("bib", nargs="+", help="待检查的 .bib 文件")
    args = parser.parse_args()

    errors = 0
    warnings = 0
    for name in args.bib:
        path = Path(name)
        findings, failure = lint_bibtex_file(path)
        if failure is not None:
            print(f"✗ 读不了 {path}：{failure}")
            errors += 1
            continue

        file_errors = [f for f in findings if f.level == "error"]
        file_warnings = [f for f in findings if f.level == "warning"]
        head = "✗" if file_errors else "✓"
        print(f"{head} {path.name}："
              f"{len(file_errors)} 处错误，{len(file_warnings)} 处提示")
        for finding in file_errors + file_warnings:
            print(finding.format())
        if not findings:
            print("  没有发现问题")
        errors += len(file_errors)
        warnings += len(file_warnings)

    if len(args.bib) > 1:
        print(f"\n合计：{errors} 处错误，{warnings} 处提示")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
