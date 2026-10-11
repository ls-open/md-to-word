#!/usr/bin/env python3
"""expand_markers.py — 渲染前把结构标记展开成 OOXML 块（预检之后、渲染之前）

标记写法与 `{{< pagebreak >}}` 同一形制（块级规则见 skill_utils.block_marker_issues）：

    {{< toc >}}                        目录域，默认收 1–3 级
    {{< toc 2 >}}                      同上，指定收到第几级
    {{< section 页码=小写罗马 起始=1 >}}  在此收尾的**这一节**的页码设置

分节符与目录域都不是 Pandoc 语法，但 `{=openxml}` 围栏块会被 Quarto 原样写进
`word/document.xml`，故停在标记层就能表达（机制见 design.md §1.8.2）。`{{< section >}}`
的参数描述**它结束的那一节**（OOXML 里 sectPr 归属前一节）；正文节的页码仍由 requirements
的 `页码：` 走模板 sectPr。

新节的 sectPr 从模板正文节整段复制，只换分节类型与页码：页脚引用（PAGE 域就在那些部件里）
跟着过来，页眉引用剥掉（前置件不排页眉）。rId 是模板自己的编号，pandoc 会照搬。
"""

import argparse
import copy
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

# 页码格式是**同一套词**，从生成器 import——两处各写一份时，改一处忘一处就会出现
# 「requirements 认这种写法、标记不认」。生成器连带 python-docx 一起进来（+0.08s 冷启），
# 而 docx 本就是导出链的硬依赖，不值得为省它再抄一份词表。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_template import PAGE_NUMBER_FMT  # noqa: E402
from skill_utils import TOC_MARKER_RE as _TOC_RE  # noqa: E402
sys.path.pop(0)

_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
_W = '{' + _NS + '}'

# sectPr 子元素顺序（OOXML schema 强制）：引用类在最前。新节点按位置插入，
# 顺序错 Word 会整段忽略且不报错。
_SECTPR_ORDER = ('headerReference', 'footerReference', 'footnotePr', 'endnotePr', 'type',
                 'pgSz', 'pgMar', 'paperSrc', 'pgBorders', 'lnNumType', 'pgNumType', 'cols',
                 'formProt', 'vAlign', 'noEndnote', 'titlePg', 'textDirection', 'bidi',
                 'rtlGutter', 'docGrid', 'printerSettings')

_SECTION_RE = re.compile(r'^\s*\{\{<\s*section\b(?P<params>[^>]*)>\}\}\s*$')
_FENCE_RE = re.compile(r'^\s*(```|~~~)')

_MAX_TOC_DEPTH = 9


class MarkerError(Exception):
    """标记写法错误 —— 由调用方转成面向作者的可读报错。"""


def _insert_ordered(parent, element, tag):
    """按 schema 顺序插入（插在第一个「顺序在它后面」的兄弟之前，没有就追加）。"""
    idx = _SECTPR_ORDER.index(tag)
    for child in parent:
        name = etree.QName(child).localname
        if name in _SECTPR_ORDER and _SECTPR_ORDER.index(name) > idx:
            child.addprevious(element)
            return
    parent.append(element)


def _openxml_block(xml: str) -> str:
    return '```{=openxml}\n' + xml + '\n```'


def toc_block(depth: int) -> str:
    """目录域。用真域（fldChar）而非 Pandoc --toc 的静态列表：页码要 Word 现算。

    `docPartGallery=Table of Contents` 让 Word 认它是目录内容控件（右键有"更新域"）。
    `w:dirty="true"` 让 Word 打开文档时自动更新一次（实测有效）；中间那串占位文字只在
    更新前可见。代价是每次打开都弹一次确认框——取舍见 design.md §2.20。
    """
    instr = f' TOC \\o "1-{depth}" \\h \\z \\u '
    return _openxml_block(
        '<w:sdt><w:sdtPr><w:docPartObj>'
        '<w:docPartGallery w:val="Table of Contents"/><w:docPartUnique/>'
        '</w:docPartObj></w:sdtPr><w:sdtContent>'
        '<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve">{instr}</w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>（打开文档后目录会自动生成）</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        '</w:sdtContent></w:sdt>'
    )


def parse_section_params(raw: str) -> dict:
    """`页码=小写罗马 起始=1` → {'fmt': 'lowerRoman', 'start': 1}"""
    params = {}
    for token in raw.split():
        if '=' not in token:
            raise MarkerError(f'分节标记的参数要写成 键=值，收到 {token!r}')
        key, val = token.split('=', 1)
        if key in params:
            raise MarkerError(f'分节标记的参数重复：{key}')
        params[key] = val

    unknown = set(params) - {'页码', '起始'}
    if unknown:
        raise MarkerError(f'分节标记不认识参数 {sorted(unknown)}，只支持 页码= / 起始=')

    out: dict[str, object] = {}
    if '页码' in params:
        if params['页码'] not in PAGE_NUMBER_FMT:
            raise MarkerError(
                f'页码格式只能是 {"|".join(PAGE_NUMBER_FMT)}，收到 {params["页码"]!r}')
        out['fmt'] = PAGE_NUMBER_FMT[params['页码']]
    if '起始' in params:
        if not params['起始'].isdigit():
            raise MarkerError(f'起始页码要写正整数，收到 {params["起始"]!r}')
        out['start'] = int(params['起始'])
    return out


def template_section(template_path):
    """模板 body 末尾那个 sectPr —— 新节的模板底子。

    整段抄它（而非只抄页脚引用）：纸张、页边距、分栏、文档网格这些也都要跟着原文节。
    rId 是模板自己的编号，pandoc 会照搬，故页脚引用抄过来同样有效。
    """
    if not template_path:
        return None
    try:
        with zipfile.ZipFile(template_path) as z:
            doc = z.read('word/document.xml')
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise MarkerError(f'读不出模板的分节信息：{template_path}（{exc}）') from exc

    root = etree.fromstring(doc)
    body = root.find(_W + 'body')
    # pandoc 只取参考文档**第一个** sectPr，故新节也从同一个取：页面几何要与正文节一致。
    return body.find(_W + 'sectPr') if body is not None else None


def section_block(params: dict, template_sect) -> str:
    """新节的 sectPr：整段继承模板正文节的页面几何，只改分节类型与页码。

    不这么抄的话，没写的属性（pgSz/pgMar/cols/docGrid…）不会有任何来源——本节是文档
    第一节，前面没有可继承的节，Word 会套它自己的默认值，页边距就悄悄变成 1 英寸。
    """
    sect = (copy.deepcopy(template_sect) if template_sect is not None
            else etree.Element(_W + 'sectPr', nsmap={'w': _NS}))
    # 前置件不排页眉：去掉页眉引用，本节就什么都不继承、什么都不显示。
    # titlePg 是「文档起始页」的概念，中间节带着它只会让本节首页改用 first 页脚。
    for tag in ('headerReference', 'titlePg', 'type', 'pgNumType'):
        for el in sect.findall(_W + tag):
            sect.remove(el)

    type_el = etree.Element(_W + 'type')
    type_el.set(_W + 'val', 'nextPage')
    _insert_ordered(sect, type_el, 'type')

    pg = etree.Element(_W + 'pgNumType')
    if 'fmt' in params:
        pg.set(_W + 'fmt', params['fmt'])
    if 'start' in params:
        pg.set(_W + 'start', str(params['start']))
    _insert_ordered(sect, pg, 'pgNumType')

    return _openxml_block(
        '<w:p><w:pPr>' + etree.tostring(sect, encoding='unicode') + '</w:pPr></w:p>'
    )


def expand(text: str, template_path=None) -> tuple:
    """展开全部标记 → (新文本, 展开条数明细)。

    代码块内的标记不动（示例语法不该被执行，同 skill_utils.mask_code_fences 的理由）。
    """
    template_sect = None
    counts = {'toc': 0, 'section': 0}
    out = []
    in_fence = False

    for line in text.split('\n'):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue

        m = _TOC_RE.match(line)
        if m:
            depth = int(m.group('depth') or 3)
            if not 1 <= depth <= _MAX_TOC_DEPTH:
                raise MarkerError(f'目录层级要在 1–{_MAX_TOC_DEPTH} 之间，收到 {depth}')
            out.append(toc_block(depth))
            counts['toc'] += 1
            continue

        m = _SECTION_RE.match(line)
        if m:
            if template_sect is None:
                template_sect = template_section(template_path)
            out.append(section_block(parse_section_params(m.group('params')), template_sect))
            counts['section'] += 1
            continue

        out.append(line)

    return '\n'.join(out), counts


def main() -> int:
    ap = argparse.ArgumentParser(description='把结构标记展开成 OOXML 块')
    ap.add_argument('md', help='输入稿')
    ap.add_argument('-o', '--output', help='输出稿（默认写 stdout）')
    ap.add_argument('-t', '--template', help='参考模板 docx（分节标记要读它的页脚引用）')
    args = ap.parse_args()

    text = Path(args.md).read_text(encoding='utf-8')
    try:
        expanded, counts = expand(text, args.template)
    except MarkerError as exc:
        print(f'❌ 标记展开失败：{exc}', file=sys.stderr)
        return 1

    if not any(counts.values()):
        print('（稿中无结构标记，未改动）', file=sys.stderr)
    else:
        print(f"已展开 {counts['toc']} 个目录标记、{counts['section']} 个分节标记", file=sys.stderr)

    if args.output:
        Path(args.output).write_text(expanded, encoding='utf-8')
    else:
        sys.stdout.write(expanded)
    return 0


if __name__ == '__main__':
    sys.exit(main())
