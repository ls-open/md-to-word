"""md_to_word.template.base_inject — 把正文灌进学校自己的模板。

为什么要有这条：中文学位论文难的不是样式表，是**版式**——封面、原创性声明、双线章名页眉，
这些东西用 `format.txt` 表达不了，用「复制粘贴」又会被 Word 重定义同名样式搞乱。
这里改走另一条：**以学校模板为底模**，把生成的样式与正文注入进去，封面那几节原封不动。

代价是「别人的文件我们不敢保证」，所以整条路径的规矩是：**验不过就不产出文件**。
七条硬规矩都是实测踩出来的，改动前先看 tests/test_base_inject.py 里对应的用例。
"""

from __future__ import annotations

import copy
import posixpath
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from lxml import etree

from md_to_word.visual_qa import word_pdf

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
R_EMBED = R + "embed"
R_ID = R + "id"
R_LINK = R + "link"
# 正文里所有"指向包内别处"的属性，都要随节点一起重挂
_R_ATTRS = (R_ID, R_EMBED, R_LINK)
# 节属性里的页眉页脚引用例外：它们是**部件**的入口，由 copy_hf 专门处理（要重写域代码）
_HF_REF_TAGS = (W + "headerReference", W + "footerReference")

_HEADER_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
_FOOTER_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
_NOTE_SHELL = {
    "footnotes.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:footnotes xmlns:w="{W[1:-1]}">'
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
        '<w:footnote w:type="continuationSeparator" w:id="0">'
        '<w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
        "</w:footnotes>"
    ),
    "endnotes.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:endnotes xmlns:w="{W[1:-1]}">'
        '<w:endnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:endnote>'
        '<w:endnote w:type="continuationSeparator" w:id="0">'
        '<w:p><w:r><w:continuationSeparator/></w:r></w:p></w:endnote>'
        "</w:endnotes>"
    ),
}

_EMPTY = {
    "header": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<w:hdr xmlns:w="{W[1:-1]}"><w:p/></w:hdr>',
    "footer": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<w:ftr xmlns:w="{W[1:-1]}"><w:p/></w:ftr>',
}

# 比对封面时允许的坐标误差（磅）。Word 两次渲染同一份文件不会差，这里留一点余量
# 吸收 pdftotext 的取整。
_TOL = 0.5


class BaseTemplateError(Exception):
    """底模不能这么用。消息直接给人看，带上具体原因。"""

    def __init__(self, reason: str, notes: list[str] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.notes = notes or []


@dataclass
class BaseOutcome:
    """灌入结果：**验到哪一层**是结果的一部分，不是文案自己说了算。

    以前日志里那句「与原件逐页一致」是写死的，没有 Word 的机器上照样打印，紧接着又提醒
    「只做了结构验真」——两行互相打脸，而用户对这条路径的信任正来自那行字。
    """

    cover_sections: int
    layout_verified: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class BaseReport:
    """底模体检结果。blocking 非空就**不生成**。"""

    blocking: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blocking


def inspect_base(path: Path, cover_sections: int | None = None) -> BaseReport:
    """先体检再动手：改不了、验不了的文件，一开始就拒绝，不产出一个"大概能用"的。

    这里只拦**确定会出事**的特征。可疑但不致命的记进 notes，让人自己判断。
    `cover_sections` 给 None 时只做文件体检——按内容/按页换算节数之前也得先知道这份
    文件读不读得了。
    """
    report = BaseReport()
    if path.suffix.lower() != ".docx":
        report.blocking.append(f"只收 .docx，不收 {path.suffix or '无扩展名'}（宏文档会带 vbaProject.bin）")
        return report
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            document = z.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile):
        report.blocking.append("打不开这个 .docx（不是有效的 Word 文件）")
        return report

    if "word/vbaProject.bin" in names:
        report.blocking.append("这是带宏的文档（vbaProject.bin），改不了也不该改")

    # 关系指着包里不存在的部件：这份文件自己就是坏的，python-docx 打开时直接抛 KeyError。
    # 学校模板经过邮件、网盘几道手，页眉部件被剥掉的情况真见过。
    broken = _dangling_rels(path)
    if broken:
        report.blocking.append(f"包里的关系指向不存在的部件（{broken[0]}），这份文件本身是坏的")

    root = etree.fromstring(document)
    sections = list(root.iter(W + "sectPr"))
    if cover_sections is not None and len(sections) < cover_sections:
        report.blocking.append(
            f"文件里只有 {len(sections)} 节，切不出前 {cover_sections} 节做前置件"
        )
    elif cover_sections is not None and len(sections) == cover_sections:
        # 全切走就没有"正文节"可替了，我们的内容会挤进最后一节，沿用它页眉页脚
        report.blocking.append(
            f"前 {cover_sections} 节已经是整份文件，切完没有正文节可换。"
            f"少留一节，或者换一份带正文的模板"
        )
    if cover_sections is not None:
        toc = _toc_section(root)
        if toc is not None and cover_sections >= toc:
            if toc == 1:
                report.blocking.append(
                    "底模的目录就在第 1 节，没有能保留的前置件——先把目录挪到正文之后再来")
            else:
                report.blocking.append(
                    f"底模第 {toc} 节是目录。目录由你的稿件生成（{{{{< toc >}}}}），"
                    f"模板那份留着只会印出模板作者的条目——最多保留前 {toc - 1} 节"
                )
    if any(n.tag == W + "altChunk" for n in root.iter()):
        report.blocking.append("含有 altChunk（外部文档块），合并后内容会错位")

    if any(n.tag in (W + "ins", W + "del") for n in root.iter()):
        report.notes.append("文件里有修订痕迹，封面可能显示为“修订状态”，提交前请在 Word 里接受修订")
    settings = _part_bytes(path, "settings.xml")
    if settings:
        protection = etree.fromstring(settings).find(W + "documentProtection")
        if protection is not None and protection.get(W + "enforcement") in ("1", "true"):
            report.notes.append(
                "底模开着文档保护，产物也带着它——导出后在 Word 里「限制编辑 → 停止保护」再改")
    if any(n.tag == W + "commentReference" for n in root.iter()):
        report.notes.append("文件里有批注，封面会带批注气泡，提交前请删除")

    rels = _rels_of(path, "word/_rels/document.xml.rels")
    external = [t for t in rels if t.get("TargetMode") == "External"]
    if external:
        # 这些是前置件自己的链接，原样保留才对——剥掉就违背了「封面一个字节不动」
        report.notes.append(f"前置件里有 {len(external)} 个外部链接，会原样保留")
    return report


def _toc_section(root) -> int | None:
    """底模的目录在第几节；没有目录就返回 None。

    目录**不能保留**：模板里那份是作者照着他自己的正文排的，留着只会印出和他内容对不上的
    条目，而且它是域，Word 排版时会按我们的新标题重算——两份永远不一样，验真也就没法比。
    用户自己写 `{{< toc >}}` 生成，页码才是对的。
    """
    body = root if root.tag == W + "body" else root.find(W + "body")
    seen = 0
    for child in (body if body is not None else []):
        if child.tag == W + "sectPr":
            seen += 1
            continue
        if child.tag != W + "p":
            continue
        if _is_toc_paragraph(child):
            return seen + 1
        if child.find(f"{W}pPr/{W}sectPr") is not None:
            seen += 1
    return None


_TOC_STYLE = re.compile(r"^toc\s*\d?$", re.I)


def _is_toc_paragraph(p) -> bool:
    """目录条目：域代码（Word 插的）或者目录样式（手工一条条排的）。"""
    for el in p.iter():
        if el.tag == W + "instrText" and (el.text or "").strip().upper().startswith("TOC"):
            return True
        if el.tag == W + "fldSimple" \
                and (el.get(W + "instr") or "").strip().upper().startswith("TOC"):
            return True
    style = p.find(f"{W}pPr/{W}pStyle")
    return style is not None and bool(_TOC_STYLE.match(style.get(W + "val") or ""))


def _dangling_rels(path: Path) -> list[str]:
    """包里每条内部关系都得有对应部件，返回断掉的那些（「哪个 .rels → 指向哪」）。"""
    missing: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for member in sorted(names):
            if not member.endswith(".rels"):
                continue
            try:
                root = etree.fromstring(z.read(member))
            except etree.XMLSyntaxError:
                missing.append(member)
                continue
            # `_rels/.rels` 的基准是包根，`word/_rels/document.xml.rels` 的基准是 `word/`
            base_dir = posixpath.dirname(posixpath.dirname(member))
            for rel in root:
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target") or ""
                if not target:
                    continue
                resolved = (
                    target.lstrip("/") if target.startswith("/")
                    else posixpath.normpath(posixpath.join(base_dir, target))
                )
                if resolved not in names:
                    missing.append(f"{member} → {target}")
    return missing


def _drop_attached_template(doc, set_part_xml) -> str | None:
    r"""摘掉底模挂着的 .dot 模板，返回它原来的路径。

    学校那份 docx 常挂着作者机器上的模板（如 `file:///D:/templates/school_thesis.dot`）。
    到了别人的机器上这个文件根本不存在，Word 打开时会问「此文档包含可能引用其他文件的域，
    是否更新」——点「是」，它去加载那个不存在的模板，加载失败，域就没更新成；目录页码于是
    停在 1，得手动再按一次 F9 才对。

    它属于对方的写作环境，不属于交付物：样式已经在 styles.xml 里，摘掉不影响排版。

    不单独提示：用户对此做不了任何事——摘掉总是对的，而且封面与版面各有验真兜着。
    报一句他没法处理的话，只是噪音。
    """
    part = _part(doc, "settings.xml")
    if part is None:
        return None
    root = etree.fromstring(part.blob)
    node = root.find(W + "attachedTemplate")
    if node is None:
        return None
    rid = node.get(R_ID)
    target = ""
    if rid and rid in part.rels:
        rel = part.rels[rid]
        target = rel.target_ref or ""
        part.drop_rel(rid)
    root.remove(node)
    set_part_xml(part, root)
    return target


def sections_until_text(base: Path, needle: str) -> list[int]:
    """底模里包含这段文字的节号（从 1 起）。找不到返回空列表。

    人说的是内容——「留到版权使用授权书那一页」——机器要的是节数。这里把前者翻成后者。
    只看 XML 不看排版，所以在没装 Word 的机器上一样能用。
    """
    want = re.sub(r"\s+", "", needle)
    if not want:
        return []
    with zipfile.ZipFile(base) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    hits: list[int] = []
    sect = 1
    for el in root.find(W + "body"):
        text = re.sub(r"\s+", "", "".join(t.text or "" for t in el.iter(W + "t")))
        if want in text and sect not in hits:
            hits.append(sect)
        if el.tag == W + "sectPr" or el.find(".//" + W + "sectPr") is not None:
            sect += 1  # sectPr 归它上面那一节，所以先记内容再进一节
    return hits


def section_outline(base: Path) -> list[str]:
    """每节的第一句非空文字：定位失败时摆给人看，好让他自己数该留几节。"""
    with zipfile.ZipFile(base) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    outline, sect = [], 1
    for el in root.find(W + "body"):
        text = "".join(t.text or "" for t in el.iter(W + "t")).strip()
        if text and (len(outline) < sect):
            outline.append(text[:34])
        if el.tag == W + "sectPr" or el.find(".//" + W + "sectPr") is not None:
            if len(outline) < sect:
                outline.append("（空）")
            sect += 1
    return outline


def section_count(path: Path) -> int:
    """底模有几节。给「这台机器算不了页数」那条提示用：至少让人知道一共有几节可数。"""
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    return len(list(root.iter(W + "sectPr")))


def _rels_of(path: Path, member: str) -> list:
    try:
        with zipfile.ZipFile(path) as z:
            if member not in z.namelist():
                return []
            return list(etree.fromstring(z.read(member)))
    except (OSError, zipfile.BadZipFile, etree.XMLSyntaxError):
        return []


# ── 注入 ────────────────────────────────────────────────────────────────


def inject_into_base(
    base: Path, rendered: Path, cover_sections: int, out: Path
) -> None:
    """把 rendered（我们导出的产物）灌进 base（学校模板），写到 out。

    前置件保留 base 的前 cover_sections 节，其余换成 rendered 的全部内容。
    """
    from docx import Document
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    school, ours = Document(str(base)), Document(str(rendered))
    _cut_after_section(school.element.body, cover_sections, qn)

    style_ids: dict[str, str] = {}
    style_names: dict[str, str] = {}
    _merge_styles(ours, school, style_ids, style_names, qn)
    _merge_doc_level_settings(ours, school, qn)

    counters: dict[str, int] = {}
    empty_refs: dict[str, str] = {}

    def set_part_xml(part, root) -> None:
        """XmlPart 认 _element，普通 Part 认 _blob——NumberingPart 是前者，写 _blob 会悄悄丢。"""
        if hasattr(part, "_element"):
            part._element = root
        else:
            part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    _drop_attached_template(school, set_part_xml)
    num_map = _copy_numbering(ours, school, qn, set_part_xml)
    note_map = _copy_notes(ours, school, "footnotes.xml", "w:footnote", qn, set_part_xml)
    note_map |= _copy_notes(ours, school, "endnotes.xml", "w:endnote", qn, set_part_xml)

    def copy_hf(sect) -> None:
        """页眉页脚部件按关系重挂；部件里的 pStyle 与 STYLEREF 也要跟着改名。"""
        for kind, tag, rel, ct in (
            ("header", "w:headerReference", RT.HEADER, _HEADER_CT),
            ("footer", "w:footerReference", RT.FOOTER, _FOOTER_CT),
        ):
            for ref in sect.findall(qn(tag)):
                rid = ref.get(qn("r:id"))
                if not rid or rid not in ours.part.related_parts:
                    continue
                src = ours.part.related_parts[rid]
                blob = _rewrite_part(src.blob, style_ids, style_names)
                counters[kind] = counters.get(kind, 0) + 1
                part = Part(
                    PackURI(f"/word/{kind}-mdw{counters[kind]}.xml"), ct, blob, school.part.package
                )
                # 页眉页脚自己也可能引用别的东西（图片、域），同样得重挂
                blob_root = etree.fromstring(blob)
                _rehome_rels(blob_root, src, part)
                part._blob = etree.tostring(
                    blob_root, xml_declaration=True, encoding="UTF-8", standalone=True
                )
                new_rid = school.part.relate_to(part, rel)
                ref.set(qn("r:id"), new_rid)
                have = {r.get(qn("w:type")) for r in sect.findall(qn(tag))}
                for extra in ("even", "first"):
                    if extra in have:
                        continue
                    clone = OxmlElement(tag)
                    clone.set(qn("w:type"), extra)
                    clone.set(qn("r:id"), new_rid)
                    ref.addnext(clone)

    def ensure_hf(sect) -> None:
        """「不要页眉」不能靠不写引用——不写等于沿用上一节，接在别人模板后面就会继承别人的页眉。

        另外，文件开了奇偶页不同时，只给 default 是不够的，偶数页仍会用继承来的页眉。
        """
        for kind, tag, rel, ct in (
            ("header", "w:headerReference", RT.HEADER, _HEADER_CT),
            ("footer", "w:footerReference", RT.FOOTER, _FOOTER_CT),
        ):
            if sect.findall(qn(tag)):
                continue
            if kind not in empty_refs:
                part = Part(
                    PackURI(f"/word/{kind}-mdw-empty.xml"), ct, _EMPTY[kind].encode("utf-8"),
                    school.part.package,
                )
                empty_refs[kind] = school.part.relate_to(part, rel)
            want = ["default", "even"]
            if sect.find(qn("w:titlePg")) is not None:
                want.append("first")
            for t in want:
                ref = OxmlElement(tag)
                ref.set(qn("w:type"), t)
                ref.set(qn("r:id"), empty_refs[kind])
                sect.insert(0, ref)

    sbody, obody = school.element.body, ours.element.body
    final = sbody.find(qn("w:sectPr"))
    our_sect = copy.deepcopy(obody.find(qn("w:sectPr")))
    copy_hf(our_sect)
    ensure_hf(our_sect)

    for child in [c for c in obody if c.tag != qn("w:sectPr")]:
        _remap_refs(child, style_ids, num_map, note_map, qn)
        _rehome_rels(child, ours.part, school.part)
        for sect in child.iter(qn("w:sectPr")):
            copy_hf(sect)
            ensure_hf(sect)
        sbody.insert(list(sbody).index(final), child)

    sbody.replace(final, our_sect)
    _copy_meta_part(ours, school, RT, PackURI, Part)
    school.save(str(out))


def _copy_meta_part(ours, school, RT, PackURI, Part) -> None:
    """把页眉联动的元数据部件（`customXml/mdw_meta.xml`）带到产物里。

    灌入只搬正文、样式、编号、页眉页脚；`customXml` 不在搬运清单里，于是产物丢掉了
    「哪些样式加入了页眉」这条自描述——之后拿它去 `md-to-word-template` 反推时，
    只能保守地说「有 STYLEREF 但不知道谁进页眉」。本工具的产物该带着自己的说明。
    """
    name = "customXml/mdw_meta.xml"
    source = next(
        (p for p in ours.part.package.iter_parts() if str(p.partname).lstrip("/") == name),
        None,
    )
    if source is None:
        return
    blob = source.blob
    existing = next(
        (p for p in school.part.package.iter_parts() if str(p.partname).lstrip("/") == name),
        None,
    )
    if existing is not None:
        existing._blob = blob
        return
    part = Part(PackURI("/" + name), source.content_type, blob, school.part.package)
    school.part.relate_to(part, RT.CUSTOM_XML)


def dropped_head(base: Path, cover_sections: int) -> str:
    """切点之后第一个非空段落：用来在提示里说清"丢掉了哪一截"。

    验真只能证明"留下的封面没被改动"，证明不了"没切太早"——切早了丢的是后面的封面，
    留下来的那几页照样分毫不差。所以必须把丢掉的那一截摆到人眼前。
    """
    from docx import Document

    school = Document(str(base))
    seen, after = 0, False
    for child in school.element.body:
        if child.find(".//" + W + "sectPr") is not None:
            seen += 1
            if seen == cover_sections:
                after = True
                continue
        if not after:
            continue
        text = "".join(n.text or "" for n in child.iter(W + "t")).strip()
        if text:
            return text[:24]
    return ""


def _cut_after_section(body, keep: int, qn) -> None:
    """留下前 keep 节（含收尾那个分节符），其余全删，body 级 sectPr 保留。"""
    seen = 0
    for idx, child in enumerate(list(body)):
        if child.tag == qn("w:sectPr") or child.find(".//" + qn("w:sectPr")) is not None:
            seen += 1
            if seen == keep:
                for extra in list(body)[idx + 1:]:
                    if extra.tag != qn("w:sectPr"):
                        body.remove(extra)
                return
    raise BaseTemplateError(f"切不出前 {keep} 节")


def _merge_styles(src, dst, ids: dict[str, str], names: dict[str, str], qn) -> None:
    """注入我们的样式：ID 和**名字**都加前缀。

    名字也必须改：同名不同义的两条样式会让 Word 挑错那一条，整页行高跟着变——
    这个现象表现为「空白页凭空消失」，极难从报错里看出来。
    """
    src_root, dst_root = src.styles.element, dst.styles.element
    by_id = {s.get(qn("w:styleId")): s for s in dst_root.findall(qn("w:style"))}
    by_name = {}
    for s in dst_root.findall(qn("w:style")):
        n = s.find(qn("w:name"))
        if n is not None:
            by_name.setdefault(n.get(qn("w:val")).lower(), s)
    defaults = {s.get(qn("w:type")) for s in dst_root.findall(qn("w:style"))
                if s.get(qn("w:default")) == "1"}

    added = []
    for st in src_root.findall(qn("w:style")):
        sid = st.get(qn("w:styleId"))
        name_el = st.find(qn("w:name"))
        name = "" if name_el is None else name_el.get(qn("w:val"))
        target = by_id.get(sid)
        if target is None:
            target = by_name.get(name.lower())
        if target is None:
            clone = copy.deepcopy(st)
            if clone.get(qn("w:type")) in defaults:
                clone.attrib.pop(qn("w:default"), None)  # 一种类型只能有一个默认样式
            dst_root.append(clone)
            added.append(clone)
            continue
        if _canon(st) == _canon(target):
            continue
        clone = copy.deepcopy(st)
        clone.set(qn("w:styleId"), f"mdw-{sid}")
        clone.attrib.pop(qn("w:default"), None)
        # 别名一律丢掉：留着它，两条样式都自称「Heading 1」，域代码与 Word 挑哪条全看运气
        for alias in clone.findall(qn("w:aliases")):
            clone.remove(alias)
        if name_el is not None:
            names[name] = f"{name}（模板）"
            clone.find(qn("w:name")).set(qn("w:val"), names[name])
        dst_root.append(clone)
        added.append(clone)
        ids[sid] = f"mdw-{sid}"

    # 改过名的样式，引用它的地方也要跟着改——**包括没改名的那些**：一条样式自己不撞名，
    # 它 basedOn 的那条却可能撞了。只遍历改名的那几条，`next` 还指着学校的正文样式，
    # Word 里标题后按回车接上来的就不是我们的正文。
    for clone in added:
        for tag in ("w:basedOn", "w:next", "w:link"):
            ref = clone.find(qn(tag))
            if ref is not None and ref.get(qn("w:val")) in ids:
                ref.set(qn("w:val"), ids[ref.get(qn("w:val"))])


def verify_doc_level_settings(rendered: Path, injected: Path) -> None:
    """灌完之后，我们声明的文档级设置还在不在。

    这两项不属于任何一条样式，丢了不会在 Word 里报错，只会安静地不起作用：校对语言退回
    底模的值（中文满篇红波浪线），标点压缩退回底模的值（全角标点不再压缩）。所以在
    「验不过就不产出」这一关也要看一眼。
    """
    import zipfile

    def read(path: Path, member: str):
        with zipfile.ZipFile(path) as z:
            return etree.fromstring(z.read(member))

    want = read(rendered, "word/styles.xml")
    got = read(injected, "word/styles.xml")
    wanted_lang = want.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr/{W}lang")
    got_lang = got.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr/{W}lang")
    want_east = None if wanted_lang is None else wanted_lang.get(W + "eastAsia")
    got_east = None if got_lang is None else got_lang.get(W + "eastAsia")
    if want_east and got_east != want_east:
        raise BaseTemplateError(
            f"校对语言没搬进底模：要求 {want_east}，产物 {got_east or '未设置'}"
        )

    want_s = read(rendered, "word/settings.xml")
    got_s = read(injected, "word/settings.xml")
    for tag, label in (("characterSpacingControl", "标点压缩"),
                       ("mirrorMargins", "对称页边距")):
        source = want_s.find(W + tag)
        if source is None:
            continue
        actual = got_s.find(W + tag)
        if actual is None or actual.get(W + "val") != source.get(W + "val"):
            raise BaseTemplateError(
                f"{label}没搬进底模：要求 {source.get(W + 'val') or '开'}，"
                f"产物 {None if actual is None else (actual.get(W + 'val') or '开')}"
            )


def _merge_doc_level_settings(src, dst, qn) -> None:
    """把**我们声明的**文档级设置搬进底模：校对语言、标点压缩、对称页边距。

    只搬 `w:style` 是不够的。`docDefaults` 里的校对语言与 `settings.xml` 里的标点压缩
    都不属于任何一条样式，灌完之后底模的旧值还在，而生成器专门写这两项的理由（不写中文
    语言，Word 就拿英文词典查中文，整篇标红）恰恰在底模这条路上失效。声明了却不起作用，
    比没声明更坏——用户以为自己设过了。

    `format.txt` 为准：底模的前置件有自己的样式，正文的排版仍然按我们的声明来。
    底模独有的设置（`evenAndOddHeaders`、`titlePg`、`compat` 等）一律不碰。
    """
    from copy import deepcopy

    # 1. 校对语言走 docDefaults：只覆盖 eastAsia 槽，西文槽保持底模的值
    src_lang = None
    node = src.styles.element.find(qn("w:docDefaults"))
    for tag in ("w:rPrDefault", "w:rPr", "w:lang"):
        node = None if node is None else node.find(qn(tag))
    src_lang = node
    east_asia = None if src_lang is None else src_lang.get(qn("w:eastAsia"))
    if east_asia:
        root = dst.styles.element
        defaults = root.find(qn("w:docDefaults"))
        if defaults is None:
            defaults = deepcopy(src.styles.element.find(qn("w:docDefaults")))
            root.insert(0, defaults)
        rpr_default = defaults.find(qn("w:rPrDefault"))
        if rpr_default is None:
            rpr_default = etree.SubElement(defaults, qn("w:rPrDefault"))
        rpr = rpr_default.find(qn("w:rPr"))
        if rpr is None:
            rpr = etree.SubElement(rpr_default, qn("w:rPr"))
        lang = rpr.find(qn("w:lang"))
        if lang is None:
            lang = etree.SubElement(rpr, qn("w:lang"))
        lang.set(qn("w:eastAsia"), east_asia)

    # 2. settings.xml 里的几项：有就搬，没有就按 schema 顺序插
    from md_to_word.template.generator import _SETTINGS_ORDER, ensure_ordered_child

    src_settings = src.settings.element
    dst_settings = dst.settings.element
    for tag in ("characterSpacingControl", "mirrorMargins"):
        source = src_settings.find(qn(f"w:{tag}"))
        if source is None:
            continue
        target = ensure_ordered_child(dst_settings, tag, _SETTINGS_ORDER)
        for attr in list(target.attrib):
            del target.attrib[attr]
        target.attrib.update(source.attrib)


def _canon(el) -> bytes:
    x = copy.deepcopy(el)
    for node in x.iter():
        for attr in list(node.attrib):
            if attr.startswith(W + "rsid") or attr.endswith(("}paraId", "}textId")):
                del node.attrib[attr]
    return etree.tostring(x, method="c14n")


def _rewrite_part(blob: bytes, ids: dict[str, str], names: dict[str, str]) -> bytes:
    r"""域代码里的样式名要跟着改。

    `STYLEREF` 的域文本是 `STYLEREF  "Heading 1"   \* MERGEFORMAT`——STYLEREF 后面是
    **两个空格**，而样式名在 styles.xml 里常是小写的 `heading 1`。按字面替换既对不上空格、
    也对不上大小写，会静默留下旧名（别名在时还能蒙对，别名一去页眉就空）。所以用正则，
    空白数量与大小写都不敏感。
    """
    text = blob.decode("utf-8")
    for old, new in names.items():
        text = re.sub(
            r'(STYLEREF\s+)"%s"' % re.escape(old),
            lambda m: f'{m.group(1)}"{new}"',
            text,
            flags=re.IGNORECASE,
        )
    for old, new in ids.items():
        text = re.sub(
            r'(w:(?:pStyle|rStyle|tblStyle) w:val=")%s(")' % re.escape(old),
            r"\g<1>%s\g<2>" % new,
            text,
        )
    return text.encode("utf-8")


def _remap_refs(el, ids, num_map, note_map, qn) -> None:
    for tag in ("w:pStyle", "w:rStyle", "w:tblStyle"):
        for node in el.iter(qn(tag)):
            val = node.get(qn("w:val"))
            if val in ids:
                node.set(qn("w:val"), ids[val])
    for node in el.iter(qn("w:numId")):
        val = node.get(qn("w:val"))
        if val in num_map:
            node.set(qn("w:val"), num_map[val])
    for tag, mapping in (("w:footnoteReference", note_map), ("w:endnoteReference", note_map)):
        for node in el.iter(qn(tag)):
            val = node.get(qn("w:id"))
            if val in mapping:
                node.set(qn("w:id"), mapping[val])


def _carry_rel(src_part, dst_part, rid: str, counters: dict[str, int]) -> str | None:
    """把源部件里的一个关系在目标部件里重建，返回目标包里的 rId。

    关系属于**包**，不属于内容流。正文搬到另一个包里，节点上的 `rId8` 就不再是原来那个
    东西了——它可能指向主题，也可能不存在。图片以前单独处理过，超链接没有，于是正文链接
    指到了别处，而结构验真看不出来。所以这里走一条统一的路：凡是被搬的节点引用到的关系，
    都按目标包的编号重建。
    """
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part

    rel = src_part.rels.get(rid)
    if rel is None:
        return None
    if rel.reltype == RT.IMAGE:
        return dst_part.get_or_add_image(BytesIO(rel.target_part.blob))[0]
    if rel.is_external:
        return dst_part.relate_to(rel.target_ref, rel.reltype, is_external=True)
    # 其余内部部件（OLE、嵌入对象等）原样复制一份，换个不会被现有部件占住的名字
    counters["part"] = counters.get("part", 0) + 1
    head, _, tail = str(rel.target_part.partname).rpartition("/")
    part = Part(
        PackURI(f"{head}/mdw{counters['part']}-{tail}"),
        rel.target_part.content_type,
        rel.target_part.blob,
        dst_part.package,
    )
    return dst_part.relate_to(part, rel.reltype)


def _rehome_rels(root, src_part, dst_part) -> None:
    """把 root 里所有关系引用改指到目标包里的对应关系。

    页眉页脚引用不在此列，归 `copy_hf`（要按改名后的样式重写域代码）。顺手搬走的话，
    部件会被原样复制、`STYLEREF` 里的旧名留在里面，`copy_hf` 随后查不到这个 rId 就静默
    跳过，页眉上印出「错误!使用"开始"选项卡…」。
    """
    counters: dict[str, int] = {}
    for el in root.iter():
        if el.tag in _HF_REF_TAGS:
            continue
        for attr in _R_ATTRS:
            rid = el.get(attr)
            if not rid:
                continue
            new = _carry_rel(src_part, dst_part, rid, counters)
            if new:
                el.set(attr, new)


def _copy_numbering(src_doc, dst_doc, qn, set_part_xml) -> dict[str, str]:
    src_part = _part(src_doc, "numbering.xml")
    dst_part = _part(dst_doc, "numbering.xml")
    if src_part is None or dst_part is None:
        return {}
    src_root, dst_root = etree.fromstring(src_part.blob), etree.fromstring(dst_part.blob)
    next_abs = max([int(n.get(W + "abstractNumId")) for n in dst_root.iter(W + "abstractNum")] or [0]) + 1
    next_num = max([int(n.get(W + "numId")) for n in dst_root.iter(W + "num")] or [0]) + 1
    abs_map, num_map = {}, {}
    for absn in src_root.findall(W + "abstractNum"):
        abs_map[absn.get(W + "abstractNumId")] = str(next_abs)
        clone = copy.deepcopy(absn)
        clone.set(W + "abstractNumId", str(next_abs))
        next_abs += 1
        dst_root.append(clone)
    for num in src_root.findall(W + "num"):
        clone = copy.deepcopy(num)
        clone.set(W + "numId", str(next_num))
        ref = clone.find(W + "abstractNumId")
        if ref is not None and ref.get(W + "val") in abs_map:
            ref.set(W + "val", abs_map[ref.get(W + "val")])
        num_map[num.get(W + "numId")] = str(next_num)
        next_num += 1
        dst_root.append(clone)
    # abstractNum 必须全部排在 num 之前，顺序错了 Word 会忽略新加的编号
    nums = [n for n in dst_root if n.tag == W + "num"]
    for n in nums:
        dst_root.remove(n)
    for n in nums:
        dst_root.append(n)
    set_part_xml(dst_part, dst_root)
    return num_map


def _copy_notes(src_doc, dst_doc, member: str, tag: str, qn, set_part_xml) -> dict[str, str]:
    """脚注/尾注必须跟着搬：引用指向一个不存在的 id，Word 直接判文件损坏。"""
    src_part, dst_part = _part(src_doc, member), _part(dst_doc, member)
    if src_part is None:
        return {}
    if dst_part is None:
        # 底模里没有脚注部件时得新建一个：引用留下了、部件没有，Word 一样判损坏
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        from docx.opc.packuri import PackURI
        from docx.opc.part import Part

        ct = ("application/vnd.openxmlformats-officedocument.wordprocessingml."
              + member.replace(".xml", "") + "+xml")
        rel = RT.FOOTNOTES if member.startswith("footnotes") else RT.ENDNOTES
        dst_part = Part(PackURI(f"/word/{member}"), ct,
                        _NOTE_SHELL[member].encode("utf-8"), dst_doc.part.package)
        dst_doc.part.relate_to(dst_part, rel)
    src_root, dst_root = etree.fromstring(src_part.blob), etree.fromstring(dst_part.blob)
    existing = [int(n.get(W + "id")) for n in dst_root.iter(qn(tag))]
    nxt = max([i for i in existing if i > 0] or [0]) + 1
    mapping = {}
    clones = []
    for note in src_root.findall(qn(tag)):
        nid = int(note.get(W + "id"))
        if nid < 1:  # -1 / 0 是分隔符，目标里本来就有
            continue
        clone = copy.deepcopy(note)
        clone.set(W + "id", str(nxt))
        dst_root.append(clone)
        clones.append(clone)
        mapping[str(nid)] = str(nxt)
        nxt += 1
    # 脚注里也能有超链接和图片，它们同样指向源包的关系编号
    for clone in clones:
        _rehome_rels(clone, src_part, dst_part)
    set_part_xml(dst_part, dst_root)
    return mapping


def _part(doc, member: str):
    return next(
        (p for p in doc.part.package.iter_parts() if str(p.partname).endswith(member)), None
    )


# ── 验收一：封面一个字节都不许动（跨平台，永远跑） ──────────────────────


def verify_structure(base: Path, result: Path, cover_sections: int) -> tuple[bool, str]:
    """结构层面能确定的东西：前置件逐节点一致、原件的东西一样没少、没引入致命冲突。

    这条不依赖 Word，Windows 上也跑。它保证的是"我们没动封面"，**保证不了"Word 排出来
    的页一样"**——后者要真排版才知道，只能在装了 Word 的机器上补做。
    """
    from docx import Document

    try:
        base_doc, result_doc = Document(str(base)), Document(str(result))
        base_nodes, base_sect = _front_signature(base_doc, cover_sections)
        result_nodes, result_sect = _front_signature(result_doc, cover_sections)
    except Exception as exc:  # noqa: BLE001 - 打不开就是打不开，不必细分
        return False, f"打不开文件：{exc}"

    if len(base_nodes) != len(result_nodes):
        return False, f"前置件的节点数变了：原件 {len(base_nodes)}，产物 {len(result_nodes)}"
    for i, (a, b) in enumerate(zip(base_nodes, result_nodes), 1):
        if a != b:
            return False, f"前置件第 {i} 个节点被改动了"
    if base_sect is not None and base_sect != result_sect:
        return False, "前置件最后一节的分节属性被改动了"

    ok, why = _check_styles_preserved(base_doc, result_doc)
    if not ok:
        return False, why
    ok, why = _check_numbering_preserved(base, result)
    if not ok:
        return False, why
    ok, why = _check_theme_preserved(base, result)
    if not ok:
        return False, why
    ok, why = _check_notes_resolvable(result)
    if not ok:
        return False, why
    ok, why = _check_rels_resolvable(result)
    if not ok:
        return False, why
    ok, why = _check_style_refs_resolvable(result)
    if not ok:
        return False, why
    ok, why = _check_body_shape(result)
    if not ok:
        return False, why
    return True, ""


def _front_signature(doc, cover_sections: int) -> tuple[list[bytes], bytes | None]:
    """前置件的签名：(除最后一节分节符以外的全部节点, 最后一节的分节属性)。

    最后一节的分节符位置会变：原件里它在 body 末尾，产物里它在段落里——位置不同但内容
    必须一样，所以单独取出来比。
    """
    nodes, seen = [], 0
    for child in doc.element.body:
        inner = child.find(".//" + W + "sectPr")
        if inner is not None:
            seen += 1
            if seen == cover_sections:
                return nodes, _canon(inner)
            nodes.append(_canon(child))
        elif child.tag == W + "sectPr":
            if seen + 1 == cover_sections:
                return nodes, _canon(child)
            break
        else:
            nodes.append(_canon(child))
    return nodes, None


def _check_styles_preserved(base_doc, result_doc) -> tuple[bool, str]:
    """原件每一条样式都得原样还在；另外不能有重名、每种类型只能有一个默认。"""
    result_styles = result_doc.styles.element.findall(W + "style")
    by_id = {s.get(W + "styleId"): s for s in result_styles}
    for st in base_doc.styles.element.findall(W + "style"):
        sid = st.get(W + "styleId")
        got = by_id.get(sid)
        if got is None:
            return False, f"产物里丢了原件样式 {sid}"
        if _canon(st) != _canon(got):
            return False, f"原件样式 {sid} 的定义被改动了"
    names, defaults = set(), set()
    for st in result_styles:
        name = st.find(W + "name")
        if name is not None:
            key = name.get(W + "val").lower()
            if key in names:
                return False, f"样式名重复：{name.get(W + 'val')}（Word 会挑错定义）"
            names.add(key)
        if st.get(W + "default") == "1":
            kind = st.get(W + "type")
            if kind in defaults:
                return False, f"同一类型有两个默认样式：{kind}"
            defaults.add(kind)
    return True, ""


def _check_numbering_preserved(base: Path, result: Path) -> tuple[bool, str]:
    b, r = _part_bytes(base, "numbering.xml"), _part_bytes(result, "numbering.xml")
    if b is None:
        return True, ""
    if r is None:
        return False, "产物里丢了 numbering.xml"
    src, dst = etree.fromstring(b), etree.fromstring(r)
    have = {n.get(W + "abstractNumId") for n in dst.iter(W + "abstractNum")}
    for n in src.iter(W + "abstractNum"):
        if n.get(W + "abstractNumId") not in have:
            return False, f"原件的编号定义 {n.get(W + 'abstractNumId')} 丢了"
    return True, ""


def _check_theme_preserved(base: Path, result: Path) -> tuple[bool, str]:
    """主题部件必须一个字节都没变。

    主题决定字体表与默认配色，改了它，封面上任何没显式指定字体的字都会跟着变——而这种
    变化在结构比对里看不出来（前置件的段落 XML 一模一样）。文档里一直写着"主题也验过"，
    以前其实没验。

    只比部件，不比目录项：有的模板带一个零字节的 `word/theme/` 目录条目，python-docx
    存盘时不写它，照字面比会把没动过主题的产物判成"主题被改动"（实测的一份模板就是）。
    """
    def themes(path: Path) -> dict[str, bytes]:
        with zipfile.ZipFile(path) as z:
            return {
                n: z.read(n) for n in z.namelist()
                if n.startswith("word/theme/") and not n.endswith("/")
            }

    before, after = themes(base), themes(result)
    if before != after:
        return False, "主题部件被改动了"
    return True, ""


def _check_notes_resolvable(result: Path) -> tuple[bool, str]:
    """脚注/尾注引用指向不存在的 id，Word 直接判文件损坏——这条得挡住。"""
    try:
        document = etree.fromstring(_part_bytes(result, "document.xml") or b"")
    except etree.XMLSyntaxError:
        return False, "document.xml 解析不了"
    for ref_tag, part, note_tag in (
        ("footnoteReference", "footnotes.xml", "footnote"),
        ("endnoteReference", "endnotes.xml", "endnote"),
    ):
        used = {n.get(W + "id") for n in document.iter(W + ref_tag)}
        if not used:
            continue
        blob = _part_bytes(result, part)
        if blob is None:
            return False, f"有 {ref_tag} 却没有 {part}"
        defined = {n.get(W + "id") for n in etree.fromstring(blob).iter(W + note_tag)}
        missing = used - defined
        if missing:
            return False, f"脚注引用指向不存在的脚注：{sorted(missing)[:3]}"
    return True, ""


def _check_rels_resolvable(result: Path) -> tuple[bool, str]:
    """每个 `r:id` / `r:embed` / `r:link` 都必须在同一部件的 .rels 里找得到，且类型对得上。

    关系是**包**级的：正文搬了家，`rId8` 就不再是原来那个东西。这条不查，装了 Word 的机器
    会拒绝打开产物，没装 Word 的机器却一路放行、以成功状态交出去——最坏的那一种失败。
    """
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    expect = {"hyperlink": RT.HYPERLINK, "blip": RT.IMAGE, "imagedata": RT.IMAGE}
    pkg_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    with zipfile.ZipFile(result) as z:
        members = set(z.namelist())
        for member in sorted(members):
            if not member.startswith("word/") or not member.endswith(".xml"):
                continue
            head, _, tail = member.rpartition("/")
            rels_member = f"{head}/_rels/{tail}.rels"
            rels = {}
            if rels_member in members:
                for rel in etree.fromstring(z.read(rels_member)).iter(f"{pkg_ns}Relationship"):
                    rels[rel.get("Id")] = rel.get("Type", "")
            root = etree.fromstring(z.read(member))
            for el in root.iter():
                for attr in _R_ATTRS:
                    rid = el.get(attr)
                    if not rid:
                        continue
                    local = etree.QName(el).localname
                    if rid not in rels:
                        return False, f"{member} 里的 <{local}> 指向不存在的 {rid}，Word 会判文件损坏"
                    want = expect.get(local)
                    if want and not rels[rid].endswith("/" + want.split("/")[-1]):
                        return False, (
                            f"{member} 里的 <{local}> 指向的 {rid} 是"
                            f"{rels[rid].rsplit('/', 1)[-1]}，不是它要的那种关系"
                        )
    return True, ""


def _check_style_refs_resolvable(result: Path) -> tuple[bool, str]:
    """正文和页眉页脚引用的每条样式都得在 styles.xml 里找得到。

    改名的意义就在这儿：样式 ID 改成了 `mdw-` 前缀，正文里的引用也要跟着改。漏一处，
    Word 会悄悄退回普通段落——字体、字号、行距全丢，而包是完整的、打不开才怪。
    """
    with zipfile.ZipFile(result) as z:
        styles = etree.fromstring(z.read("word/styles.xml"))
        have = {s.get(W + "styleId") for s in styles.findall(W + "style")}
        for member in z.namelist():
            if not re.match(r"word/(document|header[^/]*|footer[^/]*)\.xml$", member):
                continue
            root = etree.fromstring(z.read(member))
            for tag in ("pStyle", "rStyle", "tblStyle"):
                for node in root.iter(W + tag):
                    val = node.get(W + "val")
                    if val and val not in have:
                        return False, f"{member} 引用了不存在的样式「{val}」"
    return True, ""


def _check_body_shape(result: Path) -> tuple[bool, str]:
    body = etree.fromstring(_part_bytes(result, "document.xml") or b"").find(W + "body")
    if body is None:
        return False, "document.xml 里没有 body"
    if body[-1].tag != W + "sectPr":
        return False, "body 的最后一个元素不是 sectPr"
    if sum(1 for c in body if c.tag == W + "sectPr") > 1:
        return False, "body 层有多个 sectPr"
    return True, ""


def _part_bytes(path: Path, member: str) -> bytes | None:
    try:
        with zipfile.ZipFile(path) as z:
            return z.read(f"word/{member}")
    except (OSError, KeyError, zipfile.BadZipFile):
        return None


# ── 验收二：版面得和原件一样（要有 Word，macOS） ────────────────────────


def verify_cover_pages(base: Path, result: Path, sentinels: str | list[str]) -> tuple[bool, str]:
    """拿原件和产物逐词比坐标，比到我们的正文出现为止。

    比对基准**不能**是「把前置件单独切出来」——实测切出来的那份会多出一页：前置件最后
    一节的长相取决于后面接什么，它不是自足的。所以直接用原件做基准，用正文首句定位
    前置件占了几页，再把这几页逐词比一遍。

    哨兵不能是"看起来像正文"就算数，得先证明它**不在前置件里**：很多学校模板的前置件
    放了一份示例目录，里面就有「第一章 绪论」，而论文稿第一段往往正是这几个字。撞上了，
    定位到的就不是正文起点——轻则少比几页，重则把正确的切点判成错的。所以候选给一串，
    先用原件自己的渲染结果把在前置件里出现过的剔掉。
    """
    render_pdf_via_word = word_pdf.render_pdf_via_word

    ok, why = word_pdf.can_render_word_pdf()
    if not ok:
        return False, f"需要本机 Microsoft Word 才能验真（{why}）；验不了就不产出文件"
    for tool in ("pdftotext", "pdfinfo"):
        if shutil.which(tool) is None:
            return False, f"需要 {tool} 才能逐词比对；验不了就不产出文件"

    work = result.parent
    base_pdf, out_pdf = work / ".base.pdf", work / ".result.pdf"
    try:
        for src, pdf in ((base, base_pdf), (result, out_pdf)):
            rendered, reason = render_pdf_via_word(src, pdf)
            if not rendered:
                return False, f"Word 打不开 {src.name}：{reason}"

        candidates = [sentinels] if isinstance(sentinels, str) else list(sentinels)
        candidates = [c for c in candidates if c]
        front_text = "".join(_page_texts(base_pdf))
        usable = [c for c in candidates if c not in front_text]
        if not usable:
            return False, (
                "正文前几句话在底模的前置件里也出现过（模板里常带示例目录），"
                "没法用它定位正文从哪一页开始。请人工核对前置件页数"
            )
        start = None
        for cand in usable:
            start = _first_page_with(out_pdf, cand)
            if start is not None:
                break
        if start is None:
            return False, f"产物里找不到正文首句「{usable[0]}」，没法定位前置件到哪一页"
        cover_pages = start - 1
        if cover_pages < 1:
            return False, "前置件在产物里只有 0 页，说明切点不对"

        for page in range(1, cover_pages + 1):
            want, got = _words(base_pdf, page), _words(out_pdf, page)
            if len(want) != len(got):
                return False, f"第 {page} 页对不上：原件 {len(want)} 个词，产物 {len(got)} 个"
            for (x, y, word), (x2, y2, word2) in zip(want, got):
                if word != word2 or abs(float(x) - float(x2)) > _TOL \
                        or abs(float(y) - float(y2)) > _TOL:
                    return False, f"第 {page} 页位置对不上：「{word}」"
        return True, ""
    finally:
        for pdf in (base_pdf, out_pdf):
            pdf.unlink(missing_ok=True)


def _page_texts(pdf: Path) -> list[str]:
    """每一页的纯文本（空白压掉），用来判断某个串是不是也长在前置件里。"""
    texts = []
    for page in range(1, _pages(pdf) + 1):
        text = subprocess.run(
            ["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"],
            capture_output=True, text=True,
        ).stdout
        texts.append(re.sub(r"\s+", "", text))
    return texts


def _first_page_with(pdf: Path, needle: str) -> int | None:
    for page in range(1, _pages(pdf) + 1):
        text = subprocess.run(
            ["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"],
            capture_output=True, text=True,
        ).stdout
        if needle and needle in re.sub(r"\s+", "", text):
            return page
    return None


def _pages(pdf: Path) -> int:
    res = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    m = re.search(r"^Pages:\s+(\d+)", res.stdout, re.M)
    return int(m.group(1)) if m else 0


def _words(pdf: Path, page: int) -> list[tuple[str, str, str]]:
    res = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-bbox", str(pdf), "-"],
        capture_output=True, text=True,
    )
    return re.findall(
        r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="[\d.]+">([^<]*)<', res.stdout
    )


def resolve_sections_for_pages(
    base: Path, rendered: Path, pages: int, work: Path, sentinel: str
) -> int:
    """按"保留前几页"反推该切在第几节——页是人说的话，节是机器说的话。

    页切不了：分页是 Word 排出来的结果，切 XML 的时候还不知道第 N 页从哪个段落开始，
    而且切完再排可能又不是那么多页。所以这里逐个节试切一次、渲染数页，找到页数正好
    对上的那一节，把结果报出来记进模板元数据，以后直接按节走。
    """
    from docx import Document

    render_pdf_via_word = word_pdf.render_pdf_via_word

    total = len(Document(str(base)).sections)
    staged = work / ".probe.docx"
    pdf = work / ".probe.pdf"
    try:
        for n in range(1, min(pages + 2, total + 1)):
            inject_into_base(base, rendered, n, staged)
            ok, why = render_pdf_via_word(staged, pdf)
            if not ok:
                raise BaseTemplateError(f"试切到第 {n} 节时 Word 打不开：{why}")
            start = _first_page_with(pdf, sentinel)
            got = (start - 1) if start else _pages(pdf)
            if got == pages:
                return n
            if got > pages:
                raise BaseTemplateError(f"切到第 {n} 节是 {got} 页，已经超过你要的 {pages} 页")
        raise BaseTemplateError(f"切到 {total} 节也凑不出 {pages} 页前置件")
    finally:
        staged.unlink(missing_ok=True)
        pdf.unlink(missing_ok=True)


def apply_base_template(
    base: Path, rendered: Path, cover_sections: int, out: Path, sentinels: str | list[str]
) -> BaseOutcome:
    """体检 → 注入 → 验真。任何一步不过都抛 BaseTemplateError，**不写出 out**。"""
    report = inspect_base(base, cover_sections)
    if not report.ok:
        raise BaseTemplateError("；".join(report.blocking), report.notes)
    head = dropped_head(base, cover_sections)
    if head:
        report.notes.append(
            f"保留前 {cover_sections} 节；切点之后第一段是「{head}」，确认没切错"
        )

    staged = out.with_suffix(".base-staged.docx")
    try:
        inject_into_base(base, rendered, cover_sections, staged)

        ok, why = verify_structure(base, staged, cover_sections)
        if not ok:
            raise BaseTemplateError(f"结构验真没通过：{why}", report.notes)

        verify_doc_level_settings(rendered, staged)

        # 版面验真只有在装了 Word 的机器上才做得了。做不了不等于不做——
        # 结构那一关已经保证封面一个字节没动，剩下的"排出来一样不一样"只能请人看。
        layout_verified = word_pdf.can_render_word_pdf()[0]
        if layout_verified:
            ok, why = verify_cover_pages(base, staged, sentinels)
            if not ok:
                raise BaseTemplateError(why, report.notes)
        else:
            report.notes.append(
                "这台机器没有 Microsoft Word，只做了结构验真（封面内容逐节点一致）；"
                "版面请自己用 Word 打开对照原件看一遍"
            )
        staged.replace(out)
    finally:
        staged.unlink(missing_ok=True)
    return BaseOutcome(cover_sections, layout_verified, report.notes)
