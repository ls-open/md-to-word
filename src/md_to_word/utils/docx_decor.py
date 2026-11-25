"""页眉/页脚部件的内容写入。

格式文件把页眉/页脚写成 `[("text", …) | ("field", …)]` 序列；模板生成与按节切换
页眉页脚都要把它落进一个 header/footer 容器。两处共用这一份实现——各写一套时，
`{样式标题}` 的域代码写法会悄悄分叉。
"""

from __future__ import annotations

from lxml import etree
from docx.oxml.ns import qn


def clear_runs(paragraph) -> None:
    for run in list(paragraph.runs):
        run._r.getparent().remove(run._r)


def append_field(paragraph, instr: str) -> None:
    """在段落里插入一个 Word 域（begin → instrText → separate → end）。

    不写缓存结果：值由 Word 在更新域/打印时算出，故导出链在出 PDF 前会
    调用 Word 的 update field（页眉里的 STYLEREF 尤其需要）。
    """
    r = paragraph.add_run()._r
    etree.SubElement(r, qn("w:fldChar")).set(qn("w:fldCharType"), "begin")
    it = etree.SubElement(r, qn("w:instrText"))
    it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    it.text = instr
    etree.SubElement(r, qn("w:fldChar")).set(qn("w:fldCharType"), "separate")
    etree.SubElement(r, qn("w:fldChar")).set(qn("w:fldCharType"), "end")


def write_decor_container(container, parts, style_name: str) -> None:
    """把格式文件里解析出来的页眉/页脚内容写进容器。"""
    container.is_linked_to_previous = False  # 先强制建出部件，否则写进去会被继承覆盖
    p = container.paragraphs[0] if container.paragraphs else container.add_paragraph()
    clear_runs(p)
    p.style = style_name
    for kind, val in parts:
        if kind == "text":
            p.add_run(val)
        else:
            append_field(p, val)


def clear_decor_container(container) -> None:
    """显式的空页眉/页脚：留一个不带段落样式的空段落。

    不能套「页眉」样式——那份样式可能带下边框（中文报告常见），空页眉上会留下一条横线。
    """
    container.is_linked_to_previous = False
    p = container.paragraphs[0] if container.paragraphs else container.add_paragraph()
    clear_runs(p)
    ppr = p._p.find(qn("w:pPr"))
    if ppr is not None:
        p._p.remove(ppr)
