"""md_to_word.spec.constants — 格式规范词表与常量体系（中英双语）。

作为全局单一真相源，避免在解析、写入、反推和审计多处分散维护常量。
提供中英文一一对应的排版词法定义。
"""

from __future__ import annotations

import re
from typing import Optional
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

# ── XML 命名空间 ──
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def W(tag: str) -> str:
    return f"{{{NS_W}}}{tag}"


def M(tag: str) -> str:
    return f"{{{NS_M}}}{tag}"


# ── 字号映射（中文字号 → pt）──
SIZE_MAP: dict[str, Pt] = {
    "初号": Pt(42),
    "小初": Pt(36),
    "小初号": Pt(36),
    "一号": Pt(26),
    "小一": Pt(24),
    "小一号": Pt(24),
    "二号": Pt(22),
    "小二": Pt(18),
    "小二号": Pt(18),
    "三号": Pt(16),
    "小三": Pt(15),
    "小三号": Pt(15),
    "四号": Pt(14),
    "小四": Pt(12),
    "小四号": Pt(12),
    "五号": Pt(10.5),
    "小五": Pt(9),
    "小五号": Pt(9),
    "六号": Pt(7.5),
    "小六": Pt(6.5),
    "小六号": Pt(6.5),
    "七号": Pt(5.5),
    "八号": Pt(5),
}

# ── 样式名映射（中英双语键名 → Word 内部 style_name）──
STYLE_MAP: dict[str, str] = {
    # ── 中文写法 ──
    "文档标题": "Title",
    "论文标题": "Title",
    "副标题": "Subtitle",
    "作者": "Author",
    "日期": "Date",
    "摘要": "Abstract",
    "摘要标题": "Abstract Title",
    "关键词": "Keywords",
    "一级标题": "Heading 1",
    "二级标题": "Heading 2",
    "三级标题": "Heading 3",
    "四级标题": "Heading 4",
    "五级标题": "Heading 5",
    "六级标题": "Heading 6",
    "正文": "Body Text",
    "首段": "First Paragraph",
    "普通": "Normal",
    "表格题注": "Table Caption",
    "表名": "Table Caption",
    "表题": "Table Caption",
    "图片题注": "Image Caption",
    "图名": "Image Caption",
    "图题": "Image Caption",
    "图": "Captioned Figure",
    "表注": "Table Note",
    "参考文献": "Bibliography",
    "参考文献标题": "References Title",
    "紧凑": "Compact",
    "引用块": "Block Text",
    "代码": "SourceCode",
    "脚注": "Footnote Text",
    "页眉": "Header",
    "页脚": "Footer",
    "目录标题": "TOC Heading",
    "目录一级": "TOC 1",
    "目录二级": "TOC 2",
    "目录三级": "TOC 3",
    "目录四级": "TOC 4",
    "目录五级": "TOC 5",
    # ── 英文原生写法 ──
    "Title": "Title",
    "Subtitle": "Subtitle",
    "Author": "Author",
    "Date": "Date",
    "Abstract": "Abstract",
    "Abstract Title": "Abstract Title",
    "Keywords": "Keywords",
    "Heading 1": "Heading 1",
    "Heading 2": "Heading 2",
    "Heading 3": "Heading 3",
    "Heading 4": "Heading 4",
    "Heading 5": "Heading 5",
    "Heading 6": "Heading 6",
    "Body Text": "Body Text",
    "First Paragraph": "First Paragraph",
    "Normal": "Normal",
    "Table Caption": "Table Caption",
    "Image Caption": "Image Caption",
    "Figure": "Captioned Figure",
    "Captioned Figure": "Captioned Figure",
    "Table Note": "Table Note",
    "Bibliography": "Bibliography",
    "References Title": "References Title",
    "Bibliography Title": "References Title",
    "Compact": "Compact",
    "Block Text": "Block Text",
    "Block Quote": "Block Text",
    "SourceCode": "SourceCode",
    "Code": "SourceCode",
    "Footnote": "Footnote Text",
    "Footnote Text": "Footnote Text",
    "Header": "Header",
    "Footer": "Footer",
    "TOC Heading": "TOC Heading",
    "TOC 1": "TOC 1",
    "TOC 2": "TOC 2",
    "TOC 3": "TOC 3",
    "TOC 4": "TOC 4",
    "TOC 5": "TOC 5",
}

# 三种样式有多个中文写法，反查时取哪个由这张表定死，**不靠字典插入顺序**：
# 顺序一变，模板生成与报错里的名字就跟着变，而且没人看得出为什么变了。
_CANONICAL_CN = {
    "Title": "文档标题",       # 与文档、`init` 样例、README 一致；`论文标题` 是同一个样式的另一写法
    "Table Caption": "表题",
    "Image Caption": "图片题注",
}

STYLE_CN: dict[str, str] = {
    v: k for k, v in STYLE_MAP.items() if re.search(r"[\u4e00-\u9fff]", k)
} | _CANONICAL_CN
# 英文原名：报错时按用户书写语言回显，避免英文稿里出现「正文」这种中文标签
STYLE_EN: dict[str, str] = {v: k for k, v in STYLE_MAP.items() if not re.search(r"[\u4e00-\u9fff]", k)}

# 表格相关的配置行在代码里用中文名标识（无对应 Word 样式名），报错时补一份英文
# 文献区标题：稿子里写这几种之一，writer 就认定正文结束、开始写文献表；validator 也据此
# 判断「有没有写抬头」。两处必须认同一张表——各写一份就会出现「预检说没写抬头，而用户
# 明明写了」这种自相矛盾的提示。
BIBLIOGRAPHY_TITLES: tuple[str, ...] = (
    "参考文献", "参考书目", "參考文獻", "參考書目", "References", "Bibliography",
)

ROW_NAME_EN: dict[str, str] = {
    "表格": "Table",
    "表头": "Table Header",
}

# 常见易错键名提示
WRONG_KEY_HINTS: dict[str, str] = {
    "标题": "文档标题（或 论文标题 / Title）",
    "主标题": "文档标题（或 论文标题 / Title）",
    "大标题": "文档标题（或 论文标题 / Title）",
    "摘要正文": "摘要（或 Abstract）",
    "题注": "表格题注 / 图片题注（或 Table Caption / Image Caption）",
    "图注": "图片题注（或 Image Caption）",
    "图片": "图（或 Figure）",
    "表格附注": "表注（或 Table Note）",
    "第一段": "首段（或 First Paragraph）",
    "紧凑正文": "紧凑（或 Compact）",
    "块引用": "引用块（或 Block Text）",
    "引用": "引用块（或 Block Text）",
    "引用文本": "引用块（或 Block Text）",
    "目录 1": "目录一级（或 TOC 1）",
    "目录 2": "目录二级（或 TOC 2）",
    "目录 3": "目录三级（或 TOC 3）",
    "目录 4": "目录四级（或 TOC 4）",
    "目录 5": "目录五级（或 TOC 5）",
    "英文": "西文字体（或 Font）",
    "全局西文字体": "西文字体（或 Font）",
}

# ── 格式要求文件的语法版本 ──
# 词表是封闭的：改一个词就是破坏性变更。文件头写 `# schema: N` 声明它按哪一版写的，
# 高于本版本时明确拒绝（而不是让用户对着「不认识属性词」猜半天）。
CURRENT_SCHEMA = 1

# ── 纸张尺寸（单位 cm）──
PAGE_SIZES_CM: dict[str, tuple[float, float]] = {
    "a4": (21.0, 29.7),
    "letter": (21.59, 27.94),
}
PAGE_SIZE_MAP: dict[str, str] = {
    "A4": "a4",
    "a4": "a4",
    "Letter": "letter",
    "letter": "letter",
}
TWIPS_PER_CM: float = 566.93

# ── 对齐映射 ──
_ALIGN = {
    "居中": (WD_ALIGN_PARAGRAPH.CENTER, "center"),
    "左对齐": (WD_ALIGN_PARAGRAPH.LEFT, "left"),
    "右对齐": (WD_ALIGN_PARAGRAPH.RIGHT, "right"),
    "两端对齐": (WD_ALIGN_PARAGRAPH.JUSTIFY, "both"),
    "center": (WD_ALIGN_PARAGRAPH.CENTER, "center"),
    "left": (WD_ALIGN_PARAGRAPH.LEFT, "left"),
    "right": (WD_ALIGN_PARAGRAPH.RIGHT, "right"),
    "justify": (WD_ALIGN_PARAGRAPH.JUSTIFY, "both"),
}
ALIGN_MAP = {cn: enum for cn, (enum, _) in _ALIGN.items()}
ALIGN_VAL = {cn: val for cn, (_, val) in _ALIGN.items()}
ALIGN_ENUM_VAL = {enum: val for enum, val in _ALIGN.values()}
ALIGN_CN = {val: cn for cn, (_, val) in _ALIGN.items() if not cn.isascii()}
# 序列化时要按 python-docx 的枚举回写成中文，键换成枚举
ALIGN_ENUM_CN = {enum: cn for cn, (enum, _) in _ALIGN.items() if not cn.isascii()}

# ── 已知字体类别与字体切分（全局单一真相源） ──
CJK_FONTS = {
    # ── 简体中文 / Generic CJK ──
    "宋体", "黑体", "仿宋", "FangSong", "楷体", "微软雅黑",
    "SimSun", "NSimSun", "SimSun-ExtB", "SimHei", "KaiTi", "Microsoft YaHei",
    "FangSong_GB2312", "KaiTi_GB2312", "STSong", "STKaiti", "STHeiti", "STFangsong",
    "PingFang SC", "Hiragino Sans GB", "WenQuanYi Micro Hei",
    "Noto Sans SC", "Noto Sans CJK SC", "Noto Serif SC", "Noto Serif CJK SC",
    "Source Han Sans SC", "Source Han Serif SC", "Source Han Sans", "Source Han Serif",
    # ── 繁体中文 (zh-TW / zh-HK) ──
    "新細明體", "PMingLiU", "PMingLiU-ExtB", "細明體", "MingLiU", "MingLiU-ExtB",
    "標楷體", "DFKai-SB", "BiauKai", "BiauKaiTC", "BiauKaiHK",
    "微軟正黑體", "Microsoft JhengHei", "Microsoft JhengHei UI",
    "蘋方-繁", "PingFang TC", "PingFang HK",
    "宋體-繁", "Songti TC", "黑體-繁", "Heiti TC", "楷體-繁", "Kaiti TC",
    "Noto Serif TC", "Noto Serif CJK TC", "Noto Sans TC", "Noto Sans CJK TC",
    "Source Han Serif TC", "Source Han Sans TC",
    "Source Han Serif HW TC", "Source Han Sans HW TC",
    # ── 日文 (ja) ──
    "MS Mincho", "MS PMincho", "MS Gothic", "MS PGothic", "Yu Mincho", "Yu Gothic",
    "Meiryo", "Noto Sans JP", "Noto Serif JP", "Noto Sans CJK JP", "Noto Serif CJK JP",
}
_CJK_FONTS_LOWER = {f.lower(): f for f in CJK_FONTS}
LATIN_FONTS = {
    "Times New Roman", "Arial", "Calibri", "Verdana", "Helvetica", "Georgia",
    "Cambria", "Garamond", "Palatino", "Consolas", "Courier New",
    "Liberation Serif", "Liberation Sans", "DejaVu Sans",
}
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uf900-\ufaff]")
_CJK_FONT_TOKEN_RE = re.compile(
    r"\b(?:SC|TC|HK|JP|CJK|SimSun|NSimSun|SimHei|KaiTi|FangSong|MingLiU|PMingLiU"
    r"|JhengHei|BiauKai|DFKai|PingFang|Songti|Heiti|Kaiti|Mincho|Gothic|Meiryo"
    r"|STSong|STHeiti|STKaiti|STFangsong|WenQuanYi|Hiragino|Source\s+Han)\b",
    re.I,
)


def is_cjk_font(name: str) -> bool:
    """判定字体名是否属于中日韩（East Asia）字体槽。"""
    if not name:
        return False
    clean = name.strip()
    if clean in CJK_FONTS or clean.lower() in _CJK_FONTS_LOWER:
        return True
    return bool(_CJK_CHAR_RE.search(clean) or _CJK_FONT_TOKEN_RE.search(clean))


def parse_font_name(text: str) -> Optional[list[str]]:
    """从格式声明字体段提取 [cjk_font, latin_font] 或 None（解析/生成/审计同源）。"""
    parts = re.split(r"[/／]", text)
    cjk = None
    latin = None

    for part in parts:
        p = part.strip()
        if not p:
            continue
        known_match = None
        for known in sorted(CJK_FONTS | LATIN_FONTS, key=len, reverse=True):
            if re.search(r"\b" + re.escape(known) + r"\b", p, re.I):
                known_match = known
                break

        if known_match:
            if known_match in CJK_FONTS or is_cjk_font(known_match):
                cjk = known_match
            else:
                latin = known_match
        else:
            candidate = re.split(r"[,，]", p)[0].strip()
            if (
                candidate
                and not re.match(r"^\d", candidate)
                and re.search(r"[^\W\d_]|[\u4e00-\u9fff]", candidate)
            ):
                if is_cjk_font(candidate):
                    cjk = candidate
                else:
                    latin = candidate

    result = []
    if cjk:
        result.append(cjk)
    if latin:
        result.append(latin)
    return result if result else None


def split_fonts(font_names, default_latin=None):
    """把字体名列表拆成 (中日韩字体, 西文字体)。"""
    cjk = None
    latin = None
    for f in (font_names or []):
        if is_cjk_font(f):
            cjk = f
        else:
            latin = f
    if not latin and default_latin:
        latin = default_latin
    return cjk, latin


# ── 页码格式（中英支持）──
PAGE_NUMBER_FMT: dict[str, str] = {
    "阿拉伯": "decimal",
    "罗马": "upperRoman",
    "小写罗马": "lowerRoman",
    "字母": "lowerLetter",
    "大写字母": "upperLetter",
    "decimal": "decimal",
    "arabic": "decimal",
    "upperRoman": "upperRoman",
    "roman": "upperRoman",
    "lowerRoman": "lowerRoman",
    "lowerLetter": "lowerLetter",
    "upperLetter": "upperLetter",
}

# ── 对称页边距与标点压缩（中英双语）──
MIRROR_MARGINS_MAP: dict[str, bool] = {
    "开": True,
    "是": True,
    "关": False,
    "否": False,
    "on": True,
    "true": True,
    "yes": True,
    "off": False,
    "false": False,
    "no": False,
}
PUNCT_COMPRESSION_MAP: dict[str, str] = {
    "压缩": "compressPunctuation",
    "不压缩": "doNotCompress",
    "压缩含日文假名": "compressPunctuationAndJapaneseKana",
    "compress": "compressPunctuation",
    "none": "doNotCompress",
    "kana": "compressPunctuationAndJapaneseKana",
    "compresspunctuation": "compressPunctuation",
    "donotcompress": "doNotCompress",
    "compresspunctuationandjapanesekana": "compressPunctuationAndJapaneseKana",
}
PUNCT_COMPRESSION_CN: dict[str, str] = {
    "compressPunctuation": "压缩",
    "doNotCompress": "不压缩",
    "compressPunctuationAndJapaneseKana": "压缩含日文假名",
}

# ── 表格边框与对齐（中英双语）──
TABLE_ALIGN_MAP = {cn: v for cn, v in ALIGN_VAL.items() if cn not in ("两端对齐", "justify")}
TABLE_STYLE_MAP = {
    "三线表": "three-line",
    "全网格线": "grid",
    "顶底线": "top-bottom",
    "无边框": "none",
    "three-line": "three-line",
    "grid": "grid",
    "top-bottom": "top-bottom",
    "none": "none",
}
TABLE_VALIGN_MAP = {
    "居中": "center",
    "顶端": "top",
    "底端": "bottom",
    "center": "center",
    "top": "top",
    "bottom": "bottom",
}
