#!/usr/bin/env python3
"""Post-flight 完整性检查：确认导出的 docx 没丢掉正文里的数字。

这是导出链上**唯一**的数据丢失守护，做法是**确定性比对**——稿件里出现的每个三位以上
小数，都必须能在 docx 文本里找到；**缺任何一个即非零退出**，由 export.sh 阻断导出。

不用百分比阈值：丢 1~2 个高精度数值时占比远低于任何合理阈值，而那恰恰是最该拦下的事故。
`fix_docx_equations.py` 的后处理会把公式段重构成表格，历史上有过丢段记录。

比对前先剔掉稿件里**本来就不会出现在正文文本里**的部分，免得误报：
HTML 注释（pandoc 的 docx writer 丢弃 raw HTML）、YAML frontmatter、以及 `{=openxml}` 围栏块
（Quarto 把它整段当 XML 注入 `document.xml`，数字落在属性/域代码里，产物文本查不到）。

逃逸：export.sh 的 `--no-postflight`（不推荐——静默丢数据由你承担）。
"""
import os
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skill_utils import split_frontmatter  # noqa: E402
sys.path.pop(0)

# 三位以上小数。四位以上算高精度（β、p 值这类），三位是普通数据。
_RE_NUMBER = re.compile(r'\b\d+\.\d{3,}\b')
_RE_YEAR_LIKE = re.compile(r'^20\d{2}\.\d+$')
_RE_HTML_COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)
# 只有 `{=openxml}` 这一类要剔：它的数字进不了产物**文本**（属性值、域代码落在 XML 标记里），
# 计进来只会误报。**普通围栏代码块相反**——pandoc 把它渲染成 Source Code 段落，文字进 `w:t`
# （实测），是货真价实的正文，照旧要比对；一律剔掉等于给「代码清单整段丢失」开了后门。
_RE_OPENXML_FENCE = re.compile(
    r'^(?:```|~~~)\{=openxml\}.*?^(?:```|~~~)\s*$', re.DOTALL | re.MULTILINE)


def load_source_text(md_path: str) -> str:
    """读稿件并剔除不会进入产物文本的部分（YAML frontmatter、HTML 注释、`{=openxml}` 块）。"""
    text = Path(md_path).read_text(encoding='utf-8')
    _, text = split_frontmatter(text)
    text = _RE_HTML_COMMENT.sub(' ', text)
    text = _RE_OPENXML_FENCE.sub(' ', text)
    return text


def extract_numbers(text: str) -> set:
    return {n for n in _RE_NUMBER.findall(text) if not _RE_YEAR_LIKE.match(n)}


def docx_text(docx_path: str) -> str:
    """取 docx 全部可见文本。

    **必须连 `<m:t>` 一起取**：公式里的数字（如 `\\beta = 0.1128`）会被渲染成 OMML，
    落在 `m:t` 而不是 `w:t` 里；只取后者会把它们全判成"丢失"。
    """
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read('word/document.xml').decode('utf-8')
    return ' '.join(re.findall(r'<[wm]:t[^>]*>([^<]*)</[wm]:t>', xml))


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: post_flight_check.py <稿件.md> <产物.docx>", file=sys.stderr)
        return 2
    md_path, docx_path = sys.argv[1], sys.argv[2]

    try:
        wanted = extract_numbers(load_source_text(md_path))
    except Exception as e:
        print(f"❌ Post-flight 未判定：读不了稿件 {md_path}: {e}", file=sys.stderr)
        return 1
    if not wanted:
        print("✓  Post-flight: 稿件无三位以上小数，无可比对项")
        return 0

    try:
        rendered = docx_text(docx_path)
    except Exception as e:
        print(f"❌ Post-flight 未判定：读不了产物 {docx_path}: {e}", file=sys.stderr)
        return 1

    missing = sorted(n for n in wanted if n not in rendered)
    if missing:
        shown = '、'.join(missing[:10])
        more = f"（共 {len(missing)} 个，此处列前 10）" if len(missing) > 10 else ''
        print(
            f"❌ Post-flight：稿件里 {len(wanted)} 个小数有 {len(missing)} 个没进 docx。{more}\n"
            f"   缺失：{shown}\n"
            f"   这通常意味着后处理（fix_docx_equations.py）丢段。请核对产物后再导出。\n"
            f"   确需放过：加 --no-postflight（不推荐）。",
            file=sys.stderr,
        )
        return 1

    print(f"✓  Post-flight: 稿件 {len(wanted)} 个小数全部保留")
    return 0


if __name__ == "__main__":
    sys.exit(main())
