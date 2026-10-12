#!/usr/bin/env python3
"""
check_md.py — 导出前校验：检查 MD 文件里可能导致"静默失败"或样式错位的写法

功能：
  1. YAML 前置区：bibliography / csl 路径是否存在
  2. 文件名空格检查：![]() 路径含空格会导致 Quarto 静默失败
  3. 图片文件存在性：![](path) 路径不存在时 Quarto 静默失败
  4. Obsidian wikilink 检查：![[path]] 和 [[link]] Quarto 不识别，会漏成文本
  5. LaTeX 分页符检查：\\newpage / \\pagebreak / \\clearpage 在 docx 中不生效
  5b. 块级标记与正文的空行分隔：公式 / 分页短代码 / 围栏块 / 表格 / 图片行紧贴正文时
  5c. 不认识的短代码：Quarto 只警告并丢弃，标记会凭空消失
  6. custom-style 缺失检查：MD 里用到的 `custom-style="X"` 是否都在模板中存在
     （不存在则 Quarto 会静默建空壳样式，格式不生效且无警告）

用法（发现问题返回非零退出码，阻断导出；没有"只警告"的模式）：
    python3 check_md.py submission_manuscript.md                     # 只查稿件本身
    python3 check_md.py submission_manuscript.md -t template.docx     # 另查 custom-style 在不在模板里
    python3 check_md.py submission_manuscript.md -r 格式要求.txt       # 另查稿件结构要的样式声明没有

依赖：
  pip install python-docx # 仅 -t 时需要
"""

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skill_utils import (  # noqa: E402
    block_marker_issues,
    citation_key_issues,
    citations_without_bibliography,
    configure_logging,
    crossref_prefix_issues,
    get_logger,
    has_declared_image_width,
    heading_and_div_issues,
    image_width_issues,
    malformed_table_issues,
    mask_code_fences,
    parse_bib_keys,
    resolve_manuscript_path,
    section_pagebreak_issues,
    split_frontmatter,
    undefined_crossref_issues,
    unknown_shortcode_issues,
)

try:
    import yaml
except ImportError:  # pragma: no cover - 环境缺 pyyaml 时给出明确错误
    yaml = None
    raise RuntimeError("缺少 PyYAML 依赖，请先安装: pip install pyyaml")

sys.path.pop(0)
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

logger = get_logger(__name__)


def _is_in_code_block(line, prev_in_block):
    """Track fenced code block state (支持 ``` 和 ~~~)"""
    stripped = line.strip()
    if stripped.startswith('```') or stripped.startswith('~~~'):
        return not prev_in_block
    return prev_in_block


def extract_custom_styles(md_text):
    """提取 MD 里所有 custom-style="X" 的样式名（去重，保留出现行号）"""
    found = {} # style_name -> [line_numbers]
    in_code_block = False
    for i, line in enumerate(md_text.split('\n'), 1):
        in_code_block = _is_in_code_block(line, in_code_block)
        if in_code_block:
            continue
        for m in re.finditer(r"""custom-style=(["'])([^"']+)\1""", line):
            name = m.group(2)
            found.setdefault(name, []).append(i)
    return found


def parse_yaml(md_text):
    """解析 YAML 前置区为 dict。

    走 PyYAML `safe_load` + `skill_utils.split_frontmatter`（BOM/CRLF/EOF 兼容）。
    **别退回手写正则**：`^(\\w[\\w-]*):\\s*(.*)$` 这类写法会把嵌套映射、块标量、
    带特殊字符的值静默吞掉；YAML 一坏，Quarto 就当正文渲染，docx 表现为标题缺失
    加损坏行泄漏到正文。

    无 frontmatter 时返回 `{}`；frontmatter 存在但 YAML 非法抛 `yaml.YAMLError`
    由调用方捕获并计入 problems，使 export.sh 的 check_md 预检能阻断后续 Quarto 编译，
    避免静默损坏 docx。

    触发 `yaml.YAMLError` 的三种情形：
      1. PyYAML 解析器报错（缺引号、缩进错、重复文档分隔符等）
      2. frontmatter 文本解析为非 dict（如裸字符串 `title "no colon"`，或裸列表）
         —— Pandoc 期望键值对，非 dict 视为损坏
      3. frontmatter 文本为空（仅有 `---` 边界，无内容）—— 不算错误，返回 `{}`
    """
    fm_text, _ = split_frontmatter(md_text)
    if not fm_text:
        return {}
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        raise  # 天然抛错，直接上抛
    # 防御性：frontmatter 非空但解析结果不是 dict（如裸字符串/列表），
    # Pandoc 期望键值映射，这种"半合法" YAML 同样会导致 Quarto 静默损坏。
    if not isinstance(data, dict):
        snippet = repr(fm_text[:60]) + ("..." if len(fm_text) > 60 else "")
        raise yaml.YAMLError(
            f"frontmatter 解析为 {type(data).__name__}，期望键值映射（dict）。"
            f"内容：{snippet}"
        )
    return data


def get_template_styles(template_path):
    """从模板 docx 读取所有样式名（`w:name`）与 styleId 集合。

    直接读 `word/styles.xml`（zipfile + lxml），**不依赖 python-docx**：只枚举样式名
    用不着那个库，而依赖它的代价是——缺库时这里返回 (None, None)，custom-style 那道
    检查会被**静默跳过**（只剩一行 INFO）。读模板是纯 XML 的活，没有任何理由降级。
    """
    names, ids = set(), set()
    try:
        with zipfile.ZipFile(template_path) as z:
            root = etree.fromstring(z.read('word/styles.xml'))
    except (KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as e:
        logger.warning(f' 读不出模板样式（{e}）：{template_path}')
        return None, None
    for style in root.findall(f'{W}style'):
        sid = style.get(f'{W}styleId')
        if sid:
            ids.add(sid)
        name = style.find(f'{W}name')
        if name is not None and name.get(f'{W}val'):
            names.add(name.get(f'{W}val'))
    return names, ids


def check_path_spaces(md_text):
    """检查 ![]() 和 []() 中路径是否含空格"""
    issues = [] # [(line_number, path)]
    in_code_block = False
    for i, line in enumerate(md_text.split('\n'), 1):
        in_code_block = _is_in_code_block(line, in_code_block)
        if in_code_block:
            continue
        # 匹配 ![alt](path) 或 [text](path)
        for m in re.finditer(r'!?\[[^\]]*\]\(([^)]+)\)', line):
            raw_path = m.group(1).strip()
            # 跳过 URL
            if raw_path.startswith(('http://', 'https://', 'mailto:', 'data:')):
                continue
            # 去除 Quarto 渲染器属性 {width=...} 与可选标题 "title"
            path_clean = re.sub(r'\{.*\}$', '', raw_path).strip()
            path_clean = re.sub(r'\s+["\'].*["\']$', '', path_clean).strip()
            if ' ' in path_clean:
                issues.append((i, path_clean))
    return issues


def check_image_paths_exist(md_text, md_dir, extra_dirs=None):
    """检查 ![](path) 中的图片文件是否存在。

    Quarto 遇到不存在的图片路径会静默失败（不报错但图缺失）。
    跳过 http(s):// 开头的 URL 和 data: URI。

    解析基准：先按 MD 所在目录（md_dir），再按 extra_dirs 逐一尝试——
    与 export.sh 传给 Quarto 的 resource-path（INPUT_DIR:PROJECT_ROOT:FIGURES_DIR）
    保持一致，避免两层校验基准不同（如投稿副本引用相对项目根的 results/figures/）。
    """
    issues = [] # [(line_number, path)]
    search_dirs = [md_dir] + list(extra_dirs or [])
    in_code_block = False
    for i, line in enumerate(md_text.split('\n'), 1):
        in_code_block = _is_in_code_block(line, in_code_block)
        if in_code_block:
            continue
        # 匹配 ![alt](path)，不匹配普通链接 [text](url)
        for m in re.finditer(r'!\[[^\]]*\]\(([^)]+)\)', line):
            path = m.group(1).strip()
            # 跳过 URL 和 data URI
            if path.startswith(('http://', 'https://', 'data:')):
                continue
            # 去除 Quarto 渲染器属性语法 {width=...} 与可选标题 "title"
            path_clean = re.sub(r'\{.*\}$', '', path).strip()
            path_clean = re.sub(r'\s+["\'].*["\']$', '', path_clean).strip()
            if not path_clean:
                continue
            if os.path.isabs(path_clean):
                exists = os.path.exists(path_clean)
            else:
                exists = any(os.path.exists(os.path.join(d, path_clean)) for d in search_dirs)
            if not exists:
                issues.append((i, path_clean))
    return issues


def check_obsidian_wikilink(md_text):
    """检查 Obsidian wikilink 语法：![[path]] 和 [[link]]。

    Quarto 不识别 wikilink，会将其作为纯文本输出，导致图片缺失或链接失效。
    """
    issues = [] # [(line_number, syntax_type, content)]
    in_code_block = False
    for i, line in enumerate(md_text.split('\n'), 1):
        in_code_block = _is_in_code_block(line, in_code_block)
        if in_code_block:
            continue
        # 图片 wikilink: ![[xxx]]
        for m in re.finditer(r'!\[\[([^\]]+)\]\]', line):
            issues.append((i, '图片 wikilink', m.group(1)))
        # 链接 wikilink: [[xxx]]（排除已被 ![[ 匹配的）
        for m in re.finditer(r'(?<!!)\[\[([^\]]+)\]\]', line):
            issues.append((i, '链接 wikilink', m.group(1)))
    return issues


def check_latex_pagebreak(md_text):
    """检查 LaTeX 分页符：\\newpage / \\pagebreak / \\clearpage。

    这些命令在 docx 输出中不生效（Quarto 不转换），分页一律用 `{{< pagebreak >}}`。
    """
    issues = [] # [(line_number, command)]
    patterns = [r'\\newpage\b', r'\\pagebreak\b', r'\\clearpage\b']
    in_code_block = False
    for i, line in enumerate(md_text.split('\n'), 1):
        in_code_block = _is_in_code_block(line, in_code_block)
        if in_code_block:
            continue
        for pat in patterns:
            for m in re.finditer(pat, line):
                issues.append((i, m.group(0)))
    return issues


def check_latex_tag(md_text):
    """检查公式编号误用 LaTeX 的 \\tag{}（不是 Pandoc 语法，会让整条公式退化成字面文本）。

    公式编号只有 `{#eq-xxx}` 一种写法，写错就拦下，不做自动转换。
    """
    issues = []  # [(line_number, text)]
    in_code_block = False
    for i, line in enumerate(md_text.split('\n'), 1):
        in_code_block = _is_in_code_block(line, in_code_block)
        if in_code_block:
            continue
        if re.search(r'\\tag\s*\{', line):
            issues.append((i, line.strip()[:80]))
    return issues


def check_manuscript_required_styles(md_text, req_path, fm_data=None):
    """按稿件实际用到的结构（二~六级标题、摘要、关键词、图表、参考文献、目录、引用块）
    校验 requirements.txt 是否已声明对应样式或配置行。
    返回 [(line_number, feature_desc, missing_style_cn, style_en)]。
    """
    skill_dir = os.path.dirname(os.path.abspath(__file__))
    if skill_dir not in sys.path:
        sys.path.insert(0, skill_dir)
    from generate_template import missing_styles_for_body, parse_requirements

    req_text = Path(req_path).read_text(encoding='utf-8')
    spec = parse_requirements(req_text)
    declared = {r['style_name'] for r in spec.styles}
    if spec.table:
        declared.add('__ROW_table__')
    if spec.table_header:
        declared.add('__ROW_table_header__')

    _, body = split_frontmatter(md_text)
    start_line = md_text.count('\n') - body.count('\n') + 1
    issues = missing_styles_for_body(mask_code_fences(body), declared, start_line=start_line)

    if isinstance(fm_data, dict):
        if fm_data.get('bibliography') and 'Bibliography' not in declared:
            if not any(en == 'Bibliography' for _, _, _, en in issues):
                issues.append((1, 'YAML bibliography 文献库', '参考文献', 'Bibliography'))
        if fm_data.get('abstract') and 'Abstract' not in declared:
            if not any(en == 'Abstract' for _, _, _, en in issues):
                issues.append((1, 'YAML abstract 摘要', '摘要', 'Abstract'))

    return issues


def content_width_cm(req_path):
    """版心宽度（cm）= 纸张宽 - 左页边距 - 右页边距 - 装订线。

    装订线要减：它是折进左边距写的（见 design.md §1.5）。取不到要求文件时返回 None。
    """
    skill_dir = os.path.dirname(os.path.abspath(__file__))
    if skill_dir not in sys.path:
        sys.path.insert(0, skill_dir)
    from generate_template import PAGE_SIZES_CM, parse_requirements

    spec = parse_requirements(Path(req_path).read_text(encoding='utf-8'))
    if not spec.margins:
        return None
    w_cm = PAGE_SIZES_CM.get(spec.page_size, PAGE_SIZES_CM['a4'])[0]
    return w_cm - spec.margins['left'] - spec.margins['right'] - (spec.gutter_cm or 0)


def main():
    parser = argparse.ArgumentParser(
        description='导出前校验 MD：检查 custom-style 缺失、YAML 路径、文件名空格、图片存在性、wikilink、LaTeX 分页符等静默失败项',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('md', help='Markdown 文件路径')
    parser.add_argument('-t', '--template', help='模板 docx 路径（用于校验 custom-style 是否存在）')
    parser.add_argument('-r', '--requirements', help='格式要求 txt 路径（用于校验稿件用到的深层结构样式是否已声明）')
    parser.add_argument('--resource-dirs', default='',
                        help='额外资源基准目录，冒号分隔（与 Quarto resource-path 同格式）；'
                             '图片/路径存在性检查按 MD 目录 → 各基准目录顺序解析')
    args = parser.parse_args()
    configure_logging()

    if not os.path.exists(args.md):
        logger.error(f'错误: 文件不存在: {args.md}')
        sys.exit(2)

    with open(args.md, 'r', encoding='utf-8') as f:
        md_text = f.read()

    problems = 0
    # 因缺输入（没给 -r/-t）而**整条没跑**的检查。与 problems 分开记：它们不是问题，
    # 但也不是通过——不列出来，结论行那句「未发现静默失败风险」就是假话。
    skipped: list[str] = []
    md_path = Path(args.md).resolve()
    md_dir = str(md_path.parent)
    extra_dirs = [d for d in args.resource_dirs.split(':') if d]

    logger.info(f'校验: {args.md}')
    logger.info('─' * 50)

    # ── 1. YAML 路径检查 ──
    # 损坏 YAML 必须计入 problems（→ exit 1 → export.sh 阻断）：Quarto 会把损坏行
    # 当正文渲染，docx 静默损坏——标题缺失、损坏行泄漏到正文。
    fm_data = None
    try:
        fm_data = parse_yaml(md_text)
    except yaml.YAMLError as e:
        print(f' ❌ YAML 前置区解析失败: {e}')
        print(' 建议: 检查 frontmatter 语法（键值对格式、缩进、引号闭合、块标量 | 等）。')
        print('       损坏的 YAML 不会被 Quarto 解析，会导致 export 静默损坏 docx（标题缺失、'
              '损坏行泄漏到正文）。')
        problems += 1

    # 路径解析口径：绝对路径、相对稿件所在目录，或（针对 csl）回退匹配技能内置 resources/csl/ 目录。
    skill_csl_dir = Path(__file__).resolve().parent.parent / 'resources' / 'csl'
    if fm_data:
        for key in ('bibliography', 'csl'):
            val = fm_data.get(key)
            if not val:
                continue
            csl_fallback = skill_csl_dir if key == 'csl' else None
            path, how = resolve_manuscript_path(str(val), md_path, skill_csl_dir=csl_fallback)
            if how:
                continue
            print(f' ⚠ {key} 路径不存在: {val}')
            if key == 'csl':
                print('  提示: 可填写绝对路径、相对稿件所在目录的路径，或直接写本技能 resources/csl/ 下的内置文件名（如 apa.csl）。')
            else:
                print('  提示: 请填写绝对路径，或相对稿件所在目录的路径。')
            problems += 1

    # ── 1b. 正文引用的 key 是否都在 .bib 里 ──
    # 与上面同一个 `bibliography:` 路径，只是再往前走一步：把条目读出来对账。
    # 不做这一步的后果实测过——正文里留下 `[nosuchkey2020?]`（citeproc 的占位），
    # 参考文献列表里也不会有它，而三道门禁全绿（pandoc 只在自己的输出里打一行 WARNING）。
    _, body_text = split_frontmatter(md_text)
    if fm_data and fm_data.get('bibliography'):
        bib_path, how = resolve_manuscript_path(str(fm_data['bibliography']), md_path)
        if how:
            try:
                known_keys = parse_bib_keys(Path(bib_path).read_text(encoding='utf-8', errors='replace'))
            except OSError as e:
                print(f' ⚠ 读不出文献库 {bib_path}（{e}），跳过引文 key 校验')
                problems += 1
            else:
                cite_issues = citation_key_issues(body_text, known_keys)
                if cite_issues:
                    print('\n[引文 key] 正文引用的条目在 .bib 里找不到'
                          '（导出后会渲染成「key?」，且不会进参考文献列表）:')
                    for line_no, why in cite_issues:
                        print(f' ⚠ 行 {line_no}: {why}')
                    print(' 建议: 核对 key 拼写，或把该条目补进 .bib。')
                    problems += 1
    elif isinstance(fm_data, dict):
        # 没声明 bibliography：pandoc 完全不处理引文，`[@key]` 会**原样印进正文**。
        # 实测：产物里就是 `[@somekey2020]` 这七个字符，citeproc 不报警、导出报成功。
        bare_cites = citations_without_bibliography(body_text)
        if bare_cites:
            shown = '、'.join(f'行 {n}' for n in bare_cites[:5])
            more = f' 等 {len(bare_cites)} 处' if len(bare_cites) > 5 else ''
            print('\n[引文] 正文有引文语法，但 YAML 没声明 `bibliography:`'
                  f'（{shown}{more}）:')
            print(' 后果: pandoc 不会处理它们，`[@key]` 会**原样印进 docx 正文**，'
                  '不是渲染成占位符。')
            print(' 建议: 在 YAML 里加 `bibliography: refs.bib`；'
                  '若本意就是展示这串字面量，请用反引号包成行内代码。')
            problems += 1

    # ── 1c. 正文引用的 crossref 标签是否都有定义 ──
    # 与引文 key 同一类失败：实测未定义的 `@eq-x` 渲染成 `?@eq-x`，残骸直接印在正文里，
    # 而 Quarto 只在自己的输出里打一行 `WARNING Unable to resolve crossref`。
    if isinstance(fm_data, dict):
        xref_issues = undefined_crossref_issues(body_text)
        if xref_issues:
            print('\n[交叉引用] 正文引用的标签在稿子里没有定义（会渲染成「?@标签」）:')
            for line_no, why in xref_issues:
                print(f' ⚠ 行 {line_no}: {why}')
            print(' 建议: 补上 `{#标签}` 定义，或核对标签名的拼写。')
            problems += 1

    # ── 2. 文件名空格检查 ──
    space_issues = check_path_spaces(md_text)
    if space_issues:
        print('\n[文件名空格] 发现以下路径包含空格（违反 URL 规范，Quarto 静默失败）:')
        for line_no, path in space_issues:
            print(f' ⚠ 行 {line_no}: {path}')
            problems += 1
        print(' 建议: 将空格替换为下划线或连字符')

    # ── 3. 图片文件存在性检查（MD 目录 → extra 基准目录）──
    missing_imgs = check_image_paths_exist(md_text, md_dir, extra_dirs)
    if missing_imgs:
        print('\n[图片缺失] 发现以下图片路径不存在（Quarto 静默失败，图不会出现在 docx 中）:')
        for line_no, path in missing_imgs:
            print(f' ⚠ 行 {line_no}: {path}')
            problems += 1
        print(' 建议: 检查路径拼写、相对路径基准，或补充图片文件')

    # ── 4. Obsidian wikilink 检查 ──
    wikilink_issues = check_obsidian_wikilink(md_text)
    if wikilink_issues:
        print('\n[Obsidian wikilink] 发现 wikilink 语法（Quarto 不识别，会漏成纯文本）:')
        for line_no, syntax_type, content in wikilink_issues:
            print(f' ⚠ 行 {line_no}: {syntax_type} [[{content}]]')
            problems += 1
        print(' 建议: 图片用 ![](path)，链接用 [text](url)')

    # ── 5. LaTeX 分页符检查 ──
    pagebreak_issues = check_latex_pagebreak(md_text)
    if pagebreak_issues:
        print('\n[LaTeX 分页符] 发现 \\newpage/\\pagebreak/\\clearpage（docx 中不生效）:')
        for line_no, cmd in pagebreak_issues:
            print(f' ⚠ 行 {line_no}: {cmd}')
            problems += 1
        print(' 建议: 替换为 Quarto 标准分页符 {{< pagebreak >}}')

    # ── 5b. 块级标记与正文的空行分隔（判定见 skill_utils.block_marker_issues）──
    block_issues = block_marker_issues(md_text)
    if block_issues:
        print('\n[块级标记] 与正文没隔开（导出时会被并进相邻段落）:')
        for line_no, why in block_issues:
            print(f' ⚠ 行 {line_no}: {why}')
            problems += 1

    # ── 5c. 不认识的短代码（Quarto 只警告并丢弃，标记会凭空消失）──
    unknown_sc = unknown_shortcode_issues(md_text)
    if unknown_sc:
        print('\n[短代码] 发现不支持的短代码（Quarto 会把整段标记丢弃，直接少掉内容）:')
        for line_no, name in unknown_sc:
            print(f' ⚠ 行 {line_no}: {{{{< {name} >}}}}')
            problems += 1
        print(' 本技能只认这三种：{{< pagebreak >}} / {{< toc >}} / {{< section … >}}')

    # ── 5d. 标题层级与包裹块内禁用 # 检查 ──
    hd_issues = heading_and_div_issues(md_text)
    if hd_issues:
        print('\n[标题层级与包裹规范] 发现会导致样式错位或层级混乱的标题写法:')
        for line_no, why in hd_issues:
            print(f' ⚠ 行 {line_no}: {why}')
            problems += 1

    # ── 5e. 分节标记后紧跟分页符（多顶出一页）──
    sp_issues = section_pagebreak_issues(md_text)
    if sp_issues:
        print('\n[分节与分页] 分节标记之后又写了分页短代码（会多出一页空白）:')
        for line_no, why in sp_issues:
            print(f' ⚠ 行 {line_no}: {why}')
            problems += 1
        print(' 分节标记底层已自带「下一页」分节符，删掉它后面的 {{< pagebreak >}} 即可。')
        print(' （写在分节标记**之前**不产生多余页，不必改）')

    # ── 5f. 中文稿件没设交叉引用前缀（会渲染成 Equation 1）──
    cr_issues = crossref_prefix_issues(md_text, fm_data)
    if cr_issues:
        print('\n[交叉引用] 中文稿件用了交叉引用标签，但 YAML 没设中文字前缀（会渲染成中英混排）:')
        for line_no, why in cr_issues:
            print(f' ⚠ 行 {line_no}: {why}')
            problems += 1
        print(' 在 YAML 里补上，例如：')
        print('   crossref:')
        print('     eq-prefix: "式"')
        print('     fig-prefix: "图"')
        print('     tbl-prefix: "表"')
        print(' （想用英文前缀就显式写 "Equation"/"Figure"/"Table"）')

    # ── 5g. 表格列数不一致（pandoc 会静默丢列连内容一起丢）──
    tbl_issues = malformed_table_issues(md_text)
    if tbl_issues:
        print('\n[表格] 各行列数不一致（pandoc 不报错，直接把多出来的单元格丢掉）:')
        for line_no, why in tbl_issues:
            print(f' ⚠ 行 {line_no}: {why}')
            problems += 1

    # ── 5h. 图片声明宽度超过版心（导出时会被静默钳成版心宽，不报错）──
    wants_width_check = has_declared_image_width(md_text)
    if args.requirements and os.path.exists(args.requirements):
        width_cm = content_width_cm(args.requirements)
        if width_cm:
            img_issues = image_width_issues(md_text, width_cm)
            if img_issues:
                print(f'\n[图片宽度] 声明宽度超过版心 {width_cm:.2f}cm'
                      f'（导出时会被静默改小到版心宽，不报错）:')
                for line_no, why in img_issues:
                    print(f' ⚠ 行 {line_no}: {why}')
                    problems += 1
        elif wants_width_check:
            skipped.append('图片宽度是否超过版心（要求文件没写页边距，算不出版心）')
    elif wants_width_check:
        skipped.append('图片宽度是否超过版心（没给格式要求文件，算不出版心）')

    # ── 6. 公式编号写法检查（\tag{} 不是 Pandoc 语法）──
    tag_issues = check_latex_tag(md_text)
    if tag_issues:
        print('\n[公式编号] 发现 \\tag{}：Pandoc 不认这个语法，整条公式会退化成字面文本')
        for line_no, snippet in tag_issues:
            print(f' ⚠ 行 {line_no}: {snippet}')
            problems += 1
        print(' 公式编号只有一种写法：把 \\tag{X} 删掉，在 $$ 之后写标签')
        print('   改前: $$Y_i = a + bX_i \\tag{1}$$')
        print('   改后: $$Y_i = a + bX_i$$ {#eq-model1}')
        print(' 编号由 Quarto crossref 生成（顺序 (1)，配 crossref: chapters: true 则按章 (5.1)）')
    # ── 7. custom-style 缺失检查 ──
    styles_used = extract_custom_styles(md_text)
    if styles_used:
        print(f'\n[custom-style] MD 中用到 {len(styles_used)} 个自定义样式:')
        if args.template:
            if not os.path.exists(args.template):
                print(f' ⚠ 模板不存在: {args.template}，跳过样式校验')
                problems += 1
            else:
                names, ids = get_template_styles(args.template)
                if names is None:
                    # 模板明确给了却读不出 → 拦。与上面「模板不存在」同为模板不可用，
                    # 两者都该是硬失败。
                    print(f' ⚠ 模板存在但读不出样式表: {args.template}')
                    print(f'   以下 {len(styles_used)} 个 custom-style 无法校验'
                          f'（Quarto 遇到模板里没有的样式会静默建空壳，格式不生效）:')
                    for name, lines in sorted(styles_used.items()):
                        print(f' - {name} (行 {lines[0]}…)')
                    print(' 建议: 换一份本技能生成的模板，或修好这份 .docx（须含 word/styles.xml）。')
                    problems += 1
                else:
                    for name, lines in sorted(styles_used.items()):
                        matched = (name in names) or (name in ids)
                        where = '样式名' if name in names else ('styleId' if name in ids else '')
                        if matched:
                            print(f' ✓ {name} (行 {lines[0]}…) — 模板中存在({where})')
                        else:
                            print(f' ✗ {name} (行 {lines[0]}…) — 模板中不存在！'
                                  f'Quarto 会静默建空壳样式，格式不生效。'
                                  f'请在模板中创建该样式，或核对拼写。')
                            problems += 1
        else:
            for name, lines in sorted(styles_used.items()):
                print(f' - {name} (行 {lines[0]}…) — 未指定模板，跳过校验')
            print(' (提示: 加 -t 模板.docx 可校验样式是否存在，避免静默失败)')
            skipped.append(f'custom-style 是否存在（没指定 -t 模板，{len(styles_used)} 个）')

    # ── 7b. 稿件结构触发的条件必填样式检查 ──
    if args.requirements and os.path.exists(args.requirements):
        ms_style_issues = check_manuscript_required_styles(md_text, args.requirements, fm_data=fm_data)
        if ms_style_issues:
            print('\n[结构样式缺失] 稿件用到了以下结构，但格式要求文件未声明对应样式（将静默回退默认样式）:')
            for line_no, feat_desc, cn_name, en_name in ms_style_issues:
                label = f'「{cn_name}：...」配置行' if en_name.startswith('__ROW_') else f'「{cn_name}」（{en_name}）定义'
                print(f' ✗ 行 {line_no} 用到了 {feat_desc}，要求文件缺少 {label}')
                problems += 1
    else:
        skipped.append('稿件用到的结构是否已声明样式（没给格式要求文件，无法比对）')

    # ── 汇总 ──
    # 有跳过项时不打「未发现静默失败风险」：那句只有在全部都跑过时才成立，
    # 否则就是一边说「跳过校验」、一边宣称没风险。
    logger.info('\n' + '─' * 50)
    if problems != 0:
        print(f'❌ 发现 {problems} 个问题，已终止（请按上方提示修复后重新导出）。')
        sys.exit(1)
    if skipped:
        print('✅ 已跑的检查全部通过。')
        print(f'⚠ 但另有 {len(skipped)} 项**未校验**（未校验 ≠ 通过）:')
        for s in skipped:
            print(f' - {s}')
    else:
        print('✅ 校验通过，未发现静默失败风险。')


if __name__ == '__main__':
    main()
