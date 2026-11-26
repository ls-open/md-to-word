"""md_to_word.audit.postflight — 产物防丢完整性检查。

三样东西原稿有、产物就必须有：每一个数字串、每一个汉字、每一个拉丁词。前两者是
数值与中文内容，后者补上英文稿的缺口——英文整段消失时，产物照样打得开、退出码也还是 0。
"""

from __future__ import annotations

import html
import re
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from md_to_word.utils.masking import HTML_COMMENT_RE
from md_to_word.utils.skill_utils import split_frontmatter
from md_to_word.utils.textio import read_text_file

_RE_OPENXML_FENCE = re.compile(
    r"^(?:```|~~~)\{=openxml\}.*?^(?:```|~~~)\s*$", re.DOTALL | re.MULTILINE
)


def load_source_text(md_path: Path | str) -> str:
    text, _ = read_text_file(md_path)
    _, text = split_frontmatter(text)
    for pattern in (HTML_COMMENT_RE, _RE_OPENXML_FENCE, _RE_IMAGE):
        text = pattern.sub(" ", text)
    return text


_RE_CJK = re.compile(r"[㐀-䶿一-鿿]")
# 下面几条都在**去掉对文字的硬性要求**，方向只会让检查更松，不会误报
_RE_SHORTCODE = re.compile(r"\{\{<.*?>\}\}", re.DOTALL)   # 短码参数是指令，不落成文字
_RE_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")           # 替代文字进 descr、路径进关系，都不在正文
_RE_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")           # 链接留文字、丢地址
_RE_LABEL = re.compile(r"\{#[^}]*\}")
_RE_CITE = re.compile(r"@[\w:.\-]+")                        # 引用键渲染成 [1]
_RE_STYLE_LINE = re.compile(r"^(\s*)%%\s*\S+", re.MULTILINE)  # `%% 表题 …` 里那个词是指令
_RE_UNLISTED_ATTR = re.compile(
    r"^(\s*#{1,6}\s+\S[^\n]*?)\s*\{(?:\.unlisted|不入目录)\}\s*$", re.MULTILINE
)
_RE_FENCE_INFO = re.compile(r"^\s*(?:```|~~~)[^\n]*$", re.MULTILINE)


def verify_chinese_integrity(md_path: Path | str, docx_path: Path | str) -> tuple[bool, list[str]]:
    """原稿里的汉字，产物里一个都不能少。返回 (是否齐全, 缺的字)。

    只比汉字：字母数字在公式、文献库、URL 里本来就该变形，比不出结论；汉字是纯内容。
    也是只查"少"不查"多"——目录、图题、编号都是引擎加上去的。
    """
    wanted = Counter(_RE_CJK.findall(_source_for_chinese(md_path)))
    if not wanted:
        return True, []
    rendered = Counter(_RE_CJK.findall(docx_text(docx_path)))
    missing = wanted - rendered
    return not missing, sorted(missing.elements())


def _source_for_chinese(md_path: Path | str) -> str:
    text = load_source_text(md_path)
    for pattern, repl in ((_RE_SHORTCODE, " "), (_RE_LINK, r"\1"),
                          (_RE_LABEL, " "), (_RE_CITE, " "),
                          (_RE_STYLE_LINE, r"\1"), (_RE_UNLISTED_ATTR, r"\1"),
                          (_RE_FENCE_INFO, "")):
        text = pattern.sub(repl, text)
    return text


def docx_text(docx_path: Path | str) -> str:
    """正文 + 脚注 + 尾注的文字。脚注不在 document.xml 里，漏了就会把注释里的数字误判为丢失。

    页眉页脚**不算**：它们的内容来自要求文件而不是稿件，算进来只会让「正文里真的丢了
    一个数字」被页眉上恰好相同的数字盖过去——这是把闸门放松，不是修误报。

    一个词可能被 Word 拆进多个 `<w:t>`（部分加粗）或跨 `<w:br/>`。同一段里把 run 直接
    接起来、段与段之间留换行，才既不会把 `Hel` + `lo` 拆成两个词，也不会把相邻两段的
    末词与首词粘成一个。制表符/换行按分隔符算。
    """
    parts = []
    with zipfile.ZipFile(docx_path) as z:
        for name in z.namelist():
            if name == "word/document.xml" or name.startswith(("word/footnotes", "word/endnotes")):
                try:
                    xml = z.read(name).decode("utf-8")
                except Exception:
                    continue
                for para in re.findall(r"<w:p[ >].*?</w:p>", xml, re.DOTALL):
                    # 换行/制表符要变成一个**能被下面的 w:t 提取看到**的空格；
                    # 只替换成裸空格会被丢掉，相邻两行就粘成一个词（`--no-audithttps`）。
                    para = re.sub(
                        r"<w:(?:tab|br|cr)\b[^>]*/>",
                        '<w:t xml:space="preserve"> </w:t>',
                        para,
                    )
                    chunks = re.findall(r"<[wm]:t[^>]*>([^<]*)</[wm]:t>", para)
                    if chunks:
                        parts.append(html.unescape("".join(chunks)))
    return "\n".join(parts)


_RE_DIGITS = re.compile(r"\d+")


def verify_numeric_integrity(
    md_path: Path | str, docx_path: Path | str
) -> tuple[bool, list[str]]:
    """比对原稿与产物中的所有数字串。返回 (是否全部保留, 丢失的数字列表)。

    以前只比三位以上小数（防浮点格式化掉精度）；但表格里的一整列整数、年份、
    样本量同样可能整块消失，而产物看上去没毛病。数字从**模型文本**取，公式、
    引文 key、链接地址、图片路径里的数字不参与比对——它们本来就不该逐字出现。
    """
    wanted = Counter(_RE_DIGITS.findall(_source_content_text(md_path)))
    if not wanted:
        return True, []

    rendered = Counter(_RE_DIGITS.findall(docx_text(docx_path)))
    missing = wanted - rendered
    return not missing, sorted(missing.elements())


# 拉丁/希腊/西里尔字母：覆盖英文正文与常见的带重音人名。汉字不在这里——
# 中文由上面的逐字守恒单独管，混在一起会因为分词边界产生误报。
_RE_LATIN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ɏḀ-ỿͰ-ϿЀ-ӿ]+")


def _latin_words(text: str) -> Counter:
    """大小写、全角、重音都归一后再数词。

    NFKD 会把 `é` 拆成 `e` + 组合符，把全角 `Ａ` 折回 `A`；去掉组合符与统一
    大小写后，"Café"/"CAFÉ"/"Cafe" 是同一个词，不会因为排版换了写法就误报。
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return Counter(m.group(0).casefold() for m in _RE_LATIN.finditer(text))


def _source_content_text(md_path: Path | str) -> str:
    """原稿里真正会落成正文的文字。

    不直接拿 Markdown 原文数词：`#`、`**`、链接地址、引用键、公式、图片替代文字
    本来就不该出现在正文里。这里走与导出同一个读取器，只取会被写出的文本节点；
    数学、引文、交叉引用、脚注标记由引擎另行生成，不算原稿字符。
    """
    text, _ = read_text_file(md_path)
    _, text = split_frontmatter(text)
    text = HTML_COMMENT_RE.sub("", text)
    text = _RE_OPENXML_FENCE.sub(" ", text)

    from md_to_word.model.document import (
        Code, CodeBlock, Emphasis, Heading, LineBreak, Link, ListBlock, Paragraph,
        Quote, Strikethrough, Strong, Subscript, Superscript, Table, Text, Underline,
    )
    from md_to_word.model.reader import read_markdown

    def inline_text(inlines) -> str:
        parts: list[str] = []

        def walk(node) -> None:
            if isinstance(node, Text):
                parts.append(node.value)
            elif isinstance(node, Code):
                parts.append(node.value)
            elif isinstance(node, LineBreak):
                parts.append("\n")
            elif isinstance(node, (
                Strong, Emphasis, Strikethrough, Underline, Superscript, Subscript, Link,
            )):
                for child in node.children:
                    walk(child)
            # Math / Citation / CrossRef / FootnoteRef：渲染成公式、编号或文献表，
            # 原文里的 LaTeX、key 本来就不该逐字落到正文。

        for node in inlines:
            walk(node)
        return "".join(parts)

    def blocks_text(blocks) -> list[str]:
        out: list[str] = []
        for block in blocks:
            if isinstance(block, (Heading, Paragraph)):
                out.append(inline_text(block.inlines))
            elif isinstance(block, ListBlock):
                for item in block.items:
                    out.extend(blocks_text(item.blocks))
            elif isinstance(block, Table):
                for row in [block.header, *block.rows]:
                    for cell in row:
                        out.append(inline_text(cell))
            elif isinstance(block, Quote):
                out.extend(blocks_text(block.blocks))
            elif isinstance(block, CodeBlock):
                out.append(block.value)
            # Figure 的 alt 进 descr；Equation 进 OMML；Toc/PageBreak/SectionBreak
            # 是结构指令，都不产生可逐字核对的正文。
        return out

    doc = read_markdown(text)
    parts = blocks_text(doc.blocks)
    for footnote in doc.footnotes:
        parts.extend(blocks_text(footnote.blocks))
    return "\n".join(parts)


def verify_latin_integrity(
    md_path: Path | str, docx_path: Path | str
) -> tuple[bool, list[str]]:
    """原稿里的英文/拉丁词，产物里一个都不能少。返回 (是否齐全, 缺的词)。

    只查"少"不查"多"：目录、题注编号、文献表都是引擎加上去的。用词频而不是集合，
    是因为同一个词重复出现时，丢其中一处同样要能看见。
    """
    wanted = _latin_words(_source_content_text(md_path))
    if not wanted:
        return True, []
    rendered = _latin_words(docx_text(docx_path))
    missing = wanted - rendered
    return not missing, sorted(missing.elements())
