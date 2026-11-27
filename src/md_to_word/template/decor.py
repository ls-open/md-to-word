"""页眉页脚、页码格式与「加入页眉」的样式元数据。"""

from __future__ import annotations

import json
import zipfile

from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from lxml import etree

from md_to_word.i18n import t
from md_to_word.spec.constants import STYLE_MAP, W
from md_to_word.template.checks import collect_styleref_names, ensure_style_alias
from md_to_word.template.core import (
    TemplateError, _SECTPR_ORDER, ensure_ordered_child, logger,
)
from md_to_word.utils.docx_decor import write_decor_container

def apply_page_decorations(doc, spec, lang: str = "zh"):
    """写入页眉/页脚内容、奇偶与首页开关、页码格式。

    只在格式文件里**真的出现了**的容器上动手：没写的容器保持"链接上一节"，
    不会凭空建出空页眉把偶数页刷白。
    """
    if not spec.decor and not spec.page_number and not spec.section_roles:
        return

    if len(doc.sections) != 1:
        raise TemplateError(t('template.multiple_sections', lang, count=len(doc.sections)))

    section = doc.sections[0]

    uses_even = any(which == 'even' for _, which in spec.decor)
    uses_first = any(which == 'first' for _, which in spec.decor)

    # 一旦开启奇偶/首页不同，**没显式写的那几套容器会变成空白，而不是继承默认那一套**。
    # 例如只写「页脚内容：{页码}」再开奇偶不同，偶数页会整页没有页码。
    # 故把默认内容补进空缺的槽位——让「页码每页都有」这类常理成立；要覆盖就显式写。
    for kind, cn, en in (('header', '页眉', 'header'), ('footer', '页脚', 'footer')):
        base = spec.decor.get((kind, 'default'))
        if base is None:
            continue
        for which, label_cn, label_en in (
            ('even', '偶数页', 'even-page'), ('first', '首页', 'first-page')
        ):
            if (uses_even if which == 'even' else uses_first) and (kind, which) not in spec.decor:
                spec.decor[(kind, which)] = base
                logger.info(t(
                    "template.decor_inherited", lang,
                    label=label_en if lang == "en" else label_cn,
                    kind=en if lang == "en" else cn,
                ))

    if uses_even:
        doc.settings.odd_and_even_pages_header_footer = True
        logger.debug(' ✓ 页眉页脚: 已开启奇偶页不同')
    if uses_first:
        section.different_first_page_header_footer = True
        logger.debug(' ✓ 页眉页脚: 已开启首页不同')

    which_prefix = {'default': '', 'even': 'even_page_', 'first': 'first_page_'}
    kind_name = {'header': ('header', 'Header', '页眉'), 'footer': ('footer', 'Footer', '页脚')}
    for (kind, which), parts in spec.decor.items():
        attr, style_name, cn = kind_name[kind]
        write_decor_container(getattr(section, which_prefix[which] + attr), parts, style_name)
        label = {'default': '', 'even': '偶数页', 'first': '首页'}[which]
        logger.debug(f' ✓ {label}{cn}: 已设置内容与域')

    for nm in collect_styleref_names(spec):
        if ensure_style_alias(doc, nm, nm):
            logger.debug(f' ✓ 页眉/页脚域: 已把「{nm}」注册为样式别名（STYLEREF 才能解析）')
            continue
        # STYLEREF 只认 **Word 样式名**（Heading 1 这种），中文写法（一级标题）不是样式名，
        # 写进去 Word 会在页眉显示「错误!未找到引用源」。这里是导出最后一道能拦的地方。
        cn = STYLE_MAP.get(nm)
        hint = t('template.styleref_alias_hint', lang, name=nm, cn=cn) if cn else ''
        raise TemplateError(t('template.styleref_unknown', lang, name=nm, hint=hint))

    # 「页码：」只往 sectPr 写编号格式与起始值；页码要真的印在纸上，得有一行页眉/页脚
    # 内容带 {页码} 域。写了「页码：」却没有 {页码} 域 = 写了等于没写，且三道闸门全绿。
    if spec.page_number and not any(
            kind == 'field' and val.split()[0] == 'PAGE'
            for parts in spec.decor.values() for kind, val in parts):
        raise TemplateError(t('template.page_number_without_field', lang))

    # 节角色声明了页码，就必须有地方印出来：这一节自己的页脚，或者全局页脚内容。
    for role in spec.section_roles.values():
        if not role.page_number:
            continue
        footer = role.footer if role.footer is not None else spec.decor.get(('footer', 'default'), [])
        if not any(kind == 'field' and val.split()[0] == 'PAGE' for kind, val in footer):
            raise TemplateError(t('template.section_page_number_without_field', lang, role=role.name))

    if spec.page_number:
        fmt, start = spec.page_number
        pg = ensure_ordered_child(section._sectPr, 'pgNumType', _SECTPR_ORDER)
        pg.set(W('fmt'), fmt)
        if start is not None:
            pg.set(W('start'), str(start))
        else:
            pg.attrib.pop(W('start'), None)
        logger.debug(f' ✓ 页码: 格式={fmt}' + (f' 起始={start}' if start is not None else ''))

_MDW_META_PART = "customXml/mdw_meta.xml"


def write_header_styles_meta(doc, header_styles: set[str], kind: str = "template") -> None:
    """将声明加入页眉（join-header）的样式名集合以确定性 XML 写入 /customXml/mdw_meta.xml。

    `kind` 区分这份文件是模板（`template`）还是导出的成品（`product`）。反推器靠它
    拒绝成品：成品里的样式是我们自己写的，再反推只会把底模里同名的样式读错。
    """
    payload = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<mdw-meta version="1" kind="{kind}">'
        f'<header-styles>{json.dumps(sorted(header_styles), ensure_ascii=False)}'
        "</header-styles></mdw-meta>\n"
    ).encode("utf-8")
    for rel in doc.part.rels.values():
        if rel.reltype == RT.CUSTOM_XML and str(rel.target_part.partname).lstrip("/") == _MDW_META_PART:
            rel.target_part._blob = payload
            return
    part = Part(PackURI("/" + _MDW_META_PART), "application/xml", payload, doc.part.package)
    doc.part.relate_to(part, RT.CUSTOM_XML)


def _read_meta_root(source):
    """读 /customXml/mdw_meta.xml 的根节点；没有或坏了返回 None。"""
    raw: bytes | None = None
    if isinstance(source, dict):
        raw = source.get(_MDW_META_PART)
    elif isinstance(source, zipfile.ZipFile):
        try:
            raw = source.read(_MDW_META_PART)
        except KeyError:
            return None
    else:
        try:
            with zipfile.ZipFile(str(source), "r") as zf:
                raw = zf.read(_MDW_META_PART)
        except (OSError, KeyError, zipfile.BadZipFile):
            return None
    if not raw:
        return None
    try:
        return etree.fromstring(raw)
    except etree.XMLSyntaxError:
        return None


def read_header_styles_meta(source) -> set[str] | None:
    """从 docx（Path / str / ZipFile / parts dict）读取 header_styles 元数据；无元数据返回 None。"""
    root = _read_meta_root(source)
    if root is None:
        return None
    el = root.find("header-styles")
    if el is None or not el.text:
        return set()
    try:
        data = json.loads(el.text)
        return {str(x) for x in data}
    except (ValueError, TypeError):
        return None


def read_meta_kind(source) -> str:
    """读 mdw-meta 的 kind；没有元数据或没写 kind 时返回空串。"""
    root = _read_meta_root(source)
    return "" if root is None else (root.get("kind") or "")

