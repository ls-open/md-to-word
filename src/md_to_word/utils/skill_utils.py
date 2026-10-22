#!/usr/bin/env python3
"""skill_utils.py — md-to-word 内部共享基础设施。

整合以下三部分核心能力：
  1. 统一日志配置（stderr 输出，不污染 stdout 报告）
  2. OOXML 主题属性净化（清除 asciiTheme/eastAsiaTheme/themeColor 等，防止覆盖显式样式）
  3. Markdown 文本解析与块级/标题结构校验（frontmatter 拆分、代码块掩码、短代码与块级分隔、CSL/bib 路径解析）
"""

import logging
import re
import sys
from pathlib import Path
from typing import Optional

from lxml import etree

from md_to_word.config import looks_chinese

# ══════════════════════════════════════════════════════════════════════
# 1. 统一日志配置
# ══════════════════════════════════════════════════════════════════════

_LOG_CONFIGURED = False


def configure_logging(level: str = "INFO", *, force: bool = False) -> logging.Logger:
    """初始化根 logger：stderr handler + 统一格式。幂等（只配一次，除非 force）。"""
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED and not force:
        return logging.getLogger("md2word")

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    _LOG_CONFIGURED = True
    return logging.getLogger("md2word")


def get_logger(name: str = "md2word") -> logging.Logger:
    """获取模块级 logger。"""
    return logging.getLogger(name)


# ══════════════════════════════════════════════════════════════════════
# 2. OOXML 主题属性净化
# ══════════════════════════════════════════════════════════════════════

NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# rFonts 上的主题字体属性（`cstheme` 与 `csTheme` 两种拼写都在真实模板里出现过，都清）
FONT_THEME_ATTRS = ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme', 'csTheme')
# color 上的主题颜色属性
COLOR_THEME_ATTRS = ('themeColor', 'themeTint', 'themeShade')
# 全树通杀用（主题属性不只挂在 rFonts/color 上，如 rPrChange 里的旧属性）
THEME_ATTRS = FONT_THEME_ATTRS + COLOR_THEME_ATTRS


def _drop_theme_attrs(el, attrs) -> bool:
    """删除 el 上 attrs 列出的主题属性，返回是否真的删掉了东西。"""
    removed = False
    for attr in attrs:
        key = f'{{{NS_W}}}{attr}'
        if key in el.attrib:
            del el.attrib[key]
            removed = True
    return removed


def clear_font_theme_attrs(el) -> bool:
    """清除 el（rFonts）上的主题字体属性。返回是否真的清掉了。"""
    return _drop_theme_attrs(el, FONT_THEME_ATTRS)


def clear_color_theme_attrs(el) -> bool:
    """清除 el（color）上的主题颜色属性。返回是否真的清掉了。"""
    return _drop_theme_attrs(el, COLOR_THEME_ATTRS)


def strip_theme_attrs_from_xml(xml_bytes: bytes) -> bytes:
    """递归清除 XML 里任意层级的全部主题属性，返回同 XML 声明的字节流。"""
    root = etree.fromstring(xml_bytes)
    for el in root.iter():
        _drop_theme_attrs(el, THEME_ATTRS)
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone='yes')


# ══════════════════════════════════════════════════════════════════════
# 3. Markdown 解析、块级分隔与路径工具
# ══════════════════════════════════════════════════════════════════════

def mask_code_fences(content: str) -> str:
    """围栏代码块（``` / ~~~）内各行掩码为 '.'，保留总行数与行号不变。"""
    out = []
    in_fence = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(".")
            continue
        out.append("." if in_fence else line)
    return "\n".join(out)


def split_frontmatter(text: str) -> tuple[str, str]:
    """拆分 YAML frontmatter，返回 (frontmatter_text, body_text)。
    无 frontmatter 时返回 ("", 原文本)。兼容 UTF-8 BOM、CRLF 行尾与空 frontmatter。
    """
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    m = re.match(r"^---[ \t]*\r?\n(?:(.*?)\r?\n)?---[ \t]*(?:\r?\n|$)", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1) or "", text[m.end():]


# ── 块级标记：独占一行、并与正文隔开空行 ──────────────────────────────
_MATH_ONLY_RE = re.compile(r"^\s*\$\$(\s*\{#eq-[^}]+\})?\s*$")
_MATH_INLINE_RE = re.compile(r"^\s*\$\$\s*\S.*\$\$(\s*\{#eq-[^}]+\})?\s*$")
_PAGEBREAK_RE = re.compile(r"^\s*\{\{<\s*pagebreak\s*>\}\}\s*$")
TOC_MARKER_RE = re.compile(r"^\s*\{\{<\s*toc(?:\s+(?P<depth>\d+))?\s*>\}\}\s*$")
_SECTION_RE = re.compile(r"^\s*\{\{<\s*section\b[^>]*>\}\}\s*$")

_SHORTCODE_MARKERS = {
    "pagebreak": (_PAGEBREAK_RE, "分页"),
    "toc": (TOC_MARKER_RE, "目录"),
    "section": (_SECTION_RE, "分节"),
}
_CROSSREF_LABEL_RE = re.compile(r"\{#(?P<kind>eq|fig|tbl)-")
# crossref 标签种类 → YAML 里对应的前缀字段
CROSSREF_PREFIX_FIELDS = {"eq": "eq-prefix", "fig": "fig-prefix", "tbl": "tbl-prefix"}
_CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
_SHORTCODE_RE = re.compile(r"\{\{<\s*([A-Za-z][\w-]*)")
_DIV_OPEN_RE = re.compile(r"^\s*:::\s*\{.*\}\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|")
_IMAGE_ONLY_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)(\s*\{[^}]*\})?\s*$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")


def _is_prose_line(line: str) -> bool:
    """该行是不是正文（非空、非 ---、非标题、非任何块级标记行，也不含 `%%` 段落样式行）。"""
    s = line.strip()
    if not s or s == "---" or _HEADING_RE.match(line):
        return False
    if s[0] in "|>!" or s.startswith(":::") or s.startswith("%%"):
        return False
    return not (_MATH_ONLY_RE.match(line) or _MATH_INLINE_RE.match(line)
                or any(rex.match(line) for rex, _ in _SHORTCODE_MARKERS.values()))


def _shortcode_marker(line: str):
    """该行出现的短代码名；不是「独占一行」表里的标记则返回 None。"""
    m = _SHORTCODE_RE.search(line)
    return m.group(1) if m and m.group(1) in _SHORTCODE_MARKERS else None


def unknown_shortcode_issues(text: str) -> list:
    """不认识的短代码 → [(行号, 名字)]；空列表 = 没有。"""
    if not text:
        return []
    issues = []
    for i, line in enumerate(mask_code_fences(text).split("\n")):
        for m in _SHORTCODE_RE.finditer(line):
            if m.group(1) not in _SHORTCODE_MARKERS:
                issues.append((i + 1, m.group(1)))
    return issues


def block_marker_issues(text: str) -> list:
    """块级标记写法问题 → [(行号, 说明)]；空列表 = 全部规范。"""
    if not text:
        return []
    lines = mask_code_fences(text).split("\n")
    issues: list[tuple[int, str]] = []

    def after_glued(i: int) -> bool:
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        return _is_prose_line(nxt) or bool(_HEADING_RE.match(nxt))

    def before_glued(i: int) -> bool:
        return i > 0 and _is_prose_line(lines[i - 1])

    in_math = False
    for i, line in enumerate(lines):
        no = i + 1
        if _MATH_ONLY_RE.match(line):
            in_math = not in_math
            if not in_math and after_glued(i):
                issues.append((no, "公式收尾行后无空行"))
            continue
        if in_math:
            continue
        if "$$" in line:
            if not _MATH_INLINE_RE.match(line):
                issues.append((no, "公式与文字同行（未独立成行）"))
            elif after_glued(i):
                issues.append((no, "公式后无空行"))
        elif (marker := _shortcode_marker(line)) is not None:
            whole_line_re, label = _SHORTCODE_MARKERS[marker]
            if not whole_line_re.match(line):
                issues.append((no, f"{label}短代码未独占一行"))
            elif after_glued(i):
                issues.append((no, f"{label}短代码后无空行"))
        elif _DIV_OPEN_RE.match(line):
            if before_glued(i):
                issues.append((no, "围栏块首行前无空行"))
        elif _IMAGE_ONLY_RE.match(line):
            if before_glued(i):
                issues.append((no, "图片行前无空行"))
            if after_glued(i):
                issues.append((no, "图片行后无空行"))
        elif _TABLE_ROW_RE.match(line) and not (i and _TABLE_ROW_RE.match(lines[i - 1])):
            if before_glued(i):
                issues.append((no, "表格首行前无空行"))
    return issues


_IMG_WIDTH_CM_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)\s*\{[^}]*\bwidth\s*=\s*([\d.]+)cm')


def image_width_issues(text: str, content_cm: float) -> list[tuple[int, str]]:
    """图片声明宽度超过版心 → [(行号, 说明)]。`content_cm` 是版心宽度（cm）。

    **写超了不会报错，会被静默改小**：实测 A4 + 2.54cm 边距下写 `{width=25cm}`，
    产物里是 15.90cm（pandoc 按 `pgSz - pgMar` 钳的，与本技能算版心同一条公式）。
    作者以为排的是 25cm，拿到的是别的数——所以写超了就是写错，拦下让他改。
    """
    if not text:
        return []
    issues = []
    for i, line in enumerate(mask_code_fences(text).split("\n")):
        if line.lstrip().startswith("|"):        # 表格行里的 `|` 不是图片语法
            continue
        for m in _IMG_WIDTH_CM_RE.finditer(line):
            w = float(m.group(1))
            if w > content_cm + 0.01:
                issues.append((
                    i + 1,
                    f"图片声明宽 {w:g}cm，超过版心 {content_cm:.2f}cm——"
                    f"导出时会被**静默钳成版心宽**（不报错、也没有警告），"
                    f"实际拿到的不是 {w:g}cm。改成 {content_cm:.2f}cm 以内，或调小页边距",
                ))
    return issues


def has_declared_image_width(text: str) -> bool:
    """稿件里有没有写过 `{width=Ncm}`——决定上面那条门禁有没有活要干。

    没给格式要求文件时算不出版心，门禁只能跳过；但该被跳过的是**有宽度可查**的稿件，
    一张宽度都没声明的稿子不必为它多出一行「未校验」。
    """
    if not text:
        return False
    return any(_IMG_WIDTH_CM_RE.search(line)
               for line in mask_code_fences(text).split("\n")
               if not line.lstrip().startswith("|"))


def malformed_table_issues(text: str) -> list[tuple[int, str]]:
    """Markdown 表格各行列数不一致 → [(行号, 说明)]。

    **这不是排版问题，是丢内容**：列数对不上时 pandoc 不报错，直接把多出来的单元格
    连同里面的字一起丢掉（实测：表头 3 列、分隔行 2 格、数据行 3 格 → 产物只剩前两列，
    第三列的字一个不剩，全程零告警）。所以必须在导出前拦下。
    """
    if not text:
        return []
    lines = mask_code_fences(text).split("\n")
    issues: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        if not _TABLE_ROW_RE.match(lines[i]):
            i += 1
            continue
        # 一块连续的表格行
        block = []
        while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
            block.append((i + 1, lines[i]))
            i += 1
        if len(block) < 2:
            continue
        counts = [(no, len(line.strip().strip('|').split('|'))) for no, line in block]
        expect = counts[0][1]
        bad = [(no, n) for no, n in counts[1:] if n != expect]
        if bad:
            first_bad, n = bad[0]
            issues.append((
                first_bad,
                f"表格第 1 行有 {expect} 列，第 {first_bad} 行是 {n} 列——"
                f"列数对不上时多出来的单元格会被静默丢掉（连字一起丢）",
            ))
    return issues


def section_pagebreak_issues(text: str) -> list[tuple[int, str]]:
    """`{{< section … >}}` 后面紧跟 `{{< pagebreak >}}` → [(行号, 说明)]。

    分节标记底层已自带「下一页」分节符，后面再加一个分页符会多顶出一页
    （实测：论文样例 5 页 → 6 页）。**只查这一个方向**——反过来（分页符写在
    分节标记之前）实测不产生多余页，5 页仍是 5 页，所以不报。
    """
    if not text:
        return []
    lines = mask_code_fences(text).split("\n")
    issues: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if not _SECTION_RE.match(line):
            continue
        for j in range(i + 1, len(lines)):
            if not lines[j].strip():
                continue
            if _PAGEBREAK_RE.match(lines[j]):
                issues.append((j + 1, f"分节标记（行 {i + 1}）之后紧跟分页短代码，会多顶出一页"))
            break
    return issues


# ── 引文 key（`[@key]` / `@key`）──
# 字符集实测而来：首字符是字母数字或 `_`，其后允许 `: . - _ + / % &`（k1:2 / k-2 / k_3 /
# k.4 / k+5 / k%7 / k/7 / k&7 都被 citeproc 认作引文并能在 .bib 里命中）。
# `@` 前是词字符则不算引文——正文里的 `user@example.com` 原样输出（实测）。
# `-@key`（抑制作者）的 `@` 前是 `-`，故 `-` 不能进排除集，否则那种写法会被整条漏掉。
_CITE_KEY_RE = re.compile(r'(?<![\w@])@(\w[\w:.\-+/%&]*)')
# .bib 条目头：`@article{key,` / `@book{key,`
_BIB_ENTRY_RE = re.compile(r'@\w+\s*\{\s*([^,\s}]+)\s*,')
# 行内代码 `` `...` `` —— mask_code_fences 只管围栏块，行内代码得在这里单独遮掉
_INLINE_CODE_RE = re.compile(r'`[^`]*`')
# 稿子里定义过的标签：`{#eq-dynamics}`、`{#tbl-main}`
_DEFINED_LABEL_RE = re.compile(r'\{#([\w:.\-]+)\}')
# Quarto 内置的 crossref 标签前缀——`@eq-x` 这类是**交叉引用**，不是文献 key，
# 当文献 key 去 .bib 里找必然找不到（demo/01 的 `@eq-dynamics` 就是这么被误报的）。
_CROSSREF_PREFIX_RE = re.compile(r'^(?:eq|fig|tbl|sec|lst)-')


def parse_bib_keys(bib_text: str) -> set:
    """从 .bib 文本里取出全部条目 key。"""
    return set(_BIB_ENTRY_RE.findall(bib_text or ''))


def cited_keys(text: str, line_offset: int = 0):
    """逐行产出 `(行号, key)`——正文里所有 `[@key]` / `@key` 的候选 key。

    已遮掉围栏块与行内代码，已剥掉句末句点。末尾句点必须剥：`@smith2023.` 在句末时
    citeproc 解析出的 key 是 `smith2023`（实测无 WARNING），而字符集含 `.`，
    不剥就会抽出 `smith2023.` 去报一个不存在的 key——**误报比漏报贵**，它拦的是合法导出。

    `line_offset` 是给「只拿到去掉 frontmatter 的正文」的调用方补行号用的：
    不补，报出来的行号会比稿件实际行号少掉 frontmatter 的行数，用户照着找必然错位。
    """
    for i, raw in enumerate(mask_code_fences(text or '').split("\n"), 1):
        for m in _CITE_KEY_RE.finditer(_INLINE_CODE_RE.sub(' ', raw)):
            key = m.group(1).rstrip('.')
            if key:
                yield i + line_offset, key


def defined_labels(text: str) -> set:
    """稿子里定义过的标签（`{#eq-dynamics}` 的 `eq-dynamics`）。"""
    return set(_DEFINED_LABEL_RE.findall(text or ''))


def citation_key_issues(text: str, known_keys: set, line_offset: int = 0) -> list[tuple[int, str]]:
    """正文引用了 `.bib` 里没有的 key → [(行号, 说明)]，每个 key 只报一次。

    属于「能确定」的一类：文献库是纯文本，正文引了哪些 key 也是纯文本，两边取差集即可，
    不需要渲染。不查的后果实测过——正文里留下 `[nosuchkey2020?]`（citeproc 的占位），
    参考文献列表里也不会有它，而三道门禁全绿（pandoc 只在自己的输出里打一行 WARNING）。

    `known_keys` 为空时返回空：那种情况下每个被引 key 都会报，是噪声；**「文献库读到了
    却一条条目都没有」由调用方单独报**（`check_md.py` 的 1b），不在这里静默吞掉。

    只覆盖**能静态看出**的写法；citeproc 还有边角写法，故 `export.sh` 另有一层以它自己的
    WARNING 为准的兜底——两层互补，不是重复。
    """
    if not known_keys:
        return []
    labels = defined_labels(text)
    issues: list[tuple[int, str]] = []
    reported: set = set()
    for line_no, key in cited_keys(text, line_offset):
        # `@eq-x` 这类是 Quarto 交叉引用，归 undefined_crossref_issues 管，
        # 拿到 .bib 里找必然落空（demo/01 的 `@eq-dynamics` 就是这么被误报的）。
        if key in known_keys or key in labels or _CROSSREF_PREFIX_RE.match(key):
            continue
        if key in reported:
            continue
        reported.add(key)
        issues.append((line_no, f'引用了 {key}，但文献库里没有这个条目'))
    return issues


def undefined_crossref_issues(text: str, line_offset: int = 0) -> list[tuple[int, str]]:
    """正文引用了 `@eq-x` / `@fig-x` / `@tbl-x`，但稿子里没有 `{#eq-x}` 定义。

    与引文 key 是同一类失败：实测渲染成 **`?@eq-x`**——残骸直接印在正文里，
    而 Quarto 只在自己的输出里打一行 `WARNING Unable to resolve crossref`。
    """
    labels = defined_labels(text)
    issues: list[tuple[int, str]] = []
    reported: set = set()
    for line_no, key in cited_keys(text, line_offset):
        if not _CROSSREF_PREFIX_RE.match(key) or key in labels or key in reported:
            continue
        reported.add(key)
        issues.append((line_no, f'引用了 {key}，但稿子里没有 {{#{key}}} 这个标签定义'))
    return issues


def citations_without_bibliography(text: str, line_offset: int = 0) -> list[int]:
    """正文里出现**文献引用**语法的行号，保序去重。

    实测：YAML 没有 `bibliography:` 时 pandoc **完全不处理引文**——`[@somekey2020]`
    不是渲染成 `(somekey2020?)` 那种占位符，而是**这七个字符原样印进 docx 正文**，
    且 citeproc 一声不吭、导出照样报成功。所以这属于「能确定」的一类。

    **交叉引用不算文献引用**：`@eq-model1`（或引用稿子里定义过的 `{#标签}`）由 Quarto
    的 crossref 解析，没有 `bibliography:` 也照常渲染。把它算进来，会让「有公式编号、
    没有参考文献」的常规报告被误拦——实测该场景 `--no-check` 强导后产物里是「式1」，
    没有任何残留。交叉引用自身的失效由 `undefined_crossref_issues` 负责。
    """
    labels = defined_labels(text)
    seen: set = set()
    out: list[int] = []
    for line_no, key in cited_keys(text, line_offset):
        if key in labels or _CROSSREF_PREFIX_RE.match(key):
            continue
        if line_no not in seen:
            seen.add(line_no)
            out.append(line_no)
    return out


def crossref_prefix_issues(text: str, fm_data) -> list[tuple[int, str]]:
    """中文稿件用了交叉引用标签、YAML 却没设中文字前缀 → [(行号, 说明)]。

    不设前缀时 Quarto 渲染成 `Equation 1` / `Figure 1`，与正文中文混排。
    判定条件都是硬事实，不做任何猜测：**正文含中日韩字符** + **出现 `{#eq-/fig-/tbl-}` 标签**
    + **该标签在 YAML `crossref:` 下没有对应前缀**。三样都成立才报。

    想要英文前缀就在 YAML 里显式写明（`eq-prefix: "Equation"`），一样能过。
    """
    if not text:
        return []
    body_lines = mask_code_fences(text).split("\n")
    crossref = {}
    if isinstance(fm_data, dict):
        raw = fm_data.get("crossref")
        if isinstance(raw, dict):
            crossref = raw

    issues: list[tuple[int, str]] = []
    reported: set[str] = set()
    for i, line in enumerate(body_lines):
        for m in _CROSSREF_LABEL_RE.finditer(line):
            kind = m.group("kind")
            if kind in reported or CROSSREF_PREFIX_FIELDS[kind] in crossref:
                continue
            if not looks_chinese(text):
                continue  # 非中文稿件用英文默认前缀，不算问题
            reported.add(kind)
            issues.append((
                i + 1,
                f"中文稿件用了 {kind} 交叉引用（{m.group(0)}…），"
                f"但 YAML 的 crossref 下没写 {CROSSREF_PREFIX_FIELDS[kind]}",
            ))
    return issues


def heading_and_div_issues(text: str) -> list[tuple[int, str]]:
    """检查标题层级与 custom-style 包裹块内禁用 # 的规范问题 → [(行号, 说明)]。

    检查项：
      1. `::: {custom-style="..."}` 包裹块内严禁写 `#` 标题（Quarto 会渲染为 Heading 覆盖自定义样式）
      2. 正文第一个 `#` 标题必须是 1 级（不能从 `##` 开始）
      3. `#` 标题层级必须连续（不能从 `#` 直接跳到 `###`）
      4. 带数字编号的章节标题（如 `1.`、`2.1`、`2.1.1`），其编号深度必须等于 `#` 的数量
         （防止把论文大标题写成 `# 标题` 导致全文编号章节被挤到 `## 1.` / `### 1.1`）
    """
    if not text:
        return []
    _, body = split_frontmatter(text)
    start_offset = text.count("\n") - body.count("\n")
    lines = mask_code_fences(body).split("\n")

    issues: list[tuple[int, str]] = []
    in_custom_div = False
    custom_div_style = ""
    prev_level = 0

    for idx, line in enumerate(lines):
        line_no = start_offset + idx + 1
        stripped = line.strip()

        # 跟踪 ::: {custom-style="..."} 包裹状态
        m_div = re.match(r'^:::\s*\{[^}]*custom-style=(["\'])([^"\']+)\1[^}]*\}\s*$', stripped)
        if m_div:
            in_custom_div = True
            custom_div_style = m_div.group(2)
            continue
        if stripped == ":::":
            in_custom_div = False
            custom_div_style = ""
            continue

        m_head = re.match(r'^(#{1,6})\s+(.+?)\s*$', stripped)
        if not m_head:
            continue

        hashes, title = m_head.group(1), m_head.group(2)
        level = len(hashes)

        # 1. 包裹块内严禁写 #
        if in_custom_div:
            issues.append((
                line_no,
                f'`::: {{custom-style="{custom_div_style}"}}` 包裹内严禁使用 `{hashes}` 标题'
                f'（Quarto 会将其识别为 Heading {level} 并覆盖自定义样式，请去掉 `{hashes} ` 保留纯文本）'
            ))
            continue

        # 2. 第一个标题必须是 1 级
        if prev_level == 0 and level != 1:
            issues.append((
                line_no,
                f'首个章节标题是 {level} 级（`{hashes} {title[:30]}`），必须从 1 级（`#`）开始'
            ))
        # 3. 标题不得跳级
        elif prev_level > 0 and level > prev_level + 1:
            issues.append((
                line_no,
                f'标题层级跳级：从 {prev_level} 级直接跳到 {level} 级（`{hashes} {title[:30]}`），'
                f'应为 `{"#" * (prev_level + 1)}`'
            ))

        # 4. 章节数字编号深度必须等于 # 数量（如 # 1. / ## 2.1 / ### 2.1.1）
        num_match = re.match(r'^(\d+(?:\.\d+)*)\.?\s+\S', title)
        if num_match:
            number_str = num_match.group(1)
            number_depth = number_str.count('.') + 1
            if number_depth != level:
                issues.append((
                    line_no,
                    f'章节编号深度与 `#` 数量不匹配：`{hashes} {title[:30]}` 有 {level} 个 `#`，'
                    f'但编号 `{number_str}` 深度为 {number_depth}（常见原因：把论文主标题写成了 `# 标题`，'
                    f'主标题应写在 YAML `title:` 中，正文一级章节用 `# 1. ...`）'
                ))

        prev_level = level

    return issues


def resolve_manuscript_path(
    value: str,
    md_path: Path,
    skill_csl_dir: Optional[Path] = None,
) -> tuple[Path, str]:
    """解析稿件 YAML 里的路径值（csl / bibliography），返回 (解析到的路径, 命中的写法)。

    支持三种写法：
      - `'absolute'`      — 绝对路径；
      - `'doc-relative'`  — 相对**稿件所在目录**的路径；
      - `'skill-builtin'` — 仅当传入 `skill_csl_dir` 时，若本地不存在，自动在技能内置 `csl/` 目录按文件名匹配；
      - `''`              — 都没命中（返回最可能的目标路径，供报错展示）。
    """
    p = Path(value).expanduser()
    if p.is_absolute():
        return (p, "absolute") if p.exists() else (p, "")
    cand = md_path.parent / p
    if cand.exists():
        return (cand, "doc-relative")
    if skill_csl_dir is not None and skill_csl_dir.is_dir() and p.parent == Path("."):
        # 仅当填写纯文件名（如 `apa.csl`）时，在技能内置 resources/csl/ 目录下匹配
        builtin_cand = skill_csl_dir / p.name
        if builtin_cand.exists():
            return (builtin_cand.resolve(), "skill-builtin")
    return (cand, "")


# 句末标点算「这段写完了」；`；`/`：` 后面显然还有话，不算。
_TERMINAL_PUNCT = "。！？…!?）)」』”'"


def soft_wrap_issues(text: str) -> list:
    """相邻两行都是正文、且上一行没有句末标点 → [(行号, 上一行片段)]。

    本引擎按「一行一段」读取（Markdown 里一段本来就能写成一行，不需要延续规则）。
    但为 Pandoc 写的稿子常把一段折成多行，Pandoc 会把它们并成一段，我们则拆成几段——
    每段都吃一次首行缩进，版面上是看得出来的错，所以提醒一句，不阻断。
    """
    if not text:
        return []
    _, body = split_frontmatter(text)
    offset = text.count("\n") - body.count("\n")  # 前置区也占行号，报错要对得上原稿
    lines = mask_code_fences(body).split("\n")
    issues: list[tuple[int, str]] = []
    for i in range(len(lines) - 1):
        here, nxt = lines[i], lines[i + 1]
        if not (_is_prose_line(here) and _is_prose_line(nxt)):
            continue
        if here.rstrip().endswith(tuple(_TERMINAL_PUNCT)):
            continue
        snippet = here.strip()
        issues.append((i + 2 + offset, snippet[:24] + ("…" if len(snippet) > 24 else "")))
    return issues
