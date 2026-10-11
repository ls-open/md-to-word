#!/bin/bash
set -euo pipefail
# export.sh — Markdown → Word (docx) 现代学术导出流水线
#
# 引擎：Quarto 现代渲染 + Word 365 样式 + 公式靠右排版引擎
#
# 用法:
#   bash export.sh input.md -t template.docx -o out.docx
#   bash export.sh input.md -t template.docx --strip-comments # 去注释后导出
#
# 退出码: 0=全部完成 / 1=闸门未通过或技能安装不完整
#         3=docx 已生成，但 --pdf 没能渲染（附一行 MD2WORD_SKIP，见文末）
#
# CSL 在稿件 YAML 的 `csl:` 里写（支持直接写本技能 csl/ 下的内置文件名如 apa.csl、
# 相对稿件所在目录的路径，或绝对路径）。
#
# 导出前会自动跑 check_md.py (strict) 预检，发现结构性问题（图片缺失、wikilink、
# 路径空格、标题跳级等）即阻断导出，避免编译静默失败。
# 可用 --no-check 跳过预检（不推荐）。

# 渲染器探测依赖用户 $PATH 中已含 quarto（line 69 的 command -v quarto），
# 不再硬编码常见安装路径，跨平台（conda/pipx/官方安装包）通用。

INPUT=""
TEMPLATE=""
TEMPLATE_GIVEN=false   # 显式传了 -t：这时以它为准，不再按格式要求实时生成模板
OUTPUT=""
STRIP_COMMENTS=false
CHECK_MD=true   # 导出前硬闸门：默认开启 check_md 严格预检
POSTFLIGHT=true # 产物完整性闸门：默认开（见文末）。逃逸 --no-postflight
AUDIT=true      # 导出后抽查：产物 ↔ 格式要求文件逐条对账。逃逸 --no-audit
REQUIREMENTS=""  # 格式要求文件；不给则从模板同目录自动找唯一的 .txt
MAKE_PDF=false  # 可选：导出后再渲染一份 PDF 供核对（macOS + 本机 Word；见文末）。非日常必跑
EQ_NUMBER_STYLE=asis  # 公式编号外观：asis=Quarto 原生 (1)/(1.1)；cjk=中文学位论文 （5-1）

while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--template) TEMPLATE="$2"; TEMPLATE_GIVEN=true; shift 2 ;;
        -o|--output)   OUTPUT="$2";   shift 2 ;;
        --strip-comments) STRIP_COMMENTS=true; shift ;;
        --no-check)      CHECK_MD=false; shift ;;
        --no-postflight) POSTFLIGHT=false; shift ;;
        --no-audit)      AUDIT=false; shift ;;
        -r|--requirements) REQUIREMENTS="$2"; shift 2 ;;
        --pdf)           MAKE_PDF=true; shift ;;
        --eq-number-style) EQ_NUMBER_STYLE="$2"; shift 2 ;;
        -h|--help)
            echo "用法: bash export.sh input.md [-r 格式要求.txt] [-t template.docx] [-o out.docx] [--strip-comments] [--pdf] [--eq-number-style asis|cjk] [--no-check] [--no-postflight] [--no-audit]"
            echo "  -r, --requirements     格式要求文件（默认：稿件或模板同目录下唯一的 .txt）；用于导出后对账，未传 -t 时据它实时生成临时模板"
            echo "  -t, --template         可选：指定现成 Word 样式模板；传了就以它为准（不再实时生成，--reference-doc 用这一份）"
            echo "  --pdf                  导出后用本机 Word 再渲染一份 PDF（macOS 专用，用于核对效果）"
            echo "  --eq-number-style      公式编号外观：asis=Quarto 原生 (1)/(1.1)（默认）；"
            echo "                         cjk=中文学位论文写法 （5-1）"
            echo ""
            echo "退出码: 0=全部完成 / 1=闸门未通过或技能安装不完整"
            echo "        3=docx 已生成，但 --pdf 没能渲染（同时打一行 MD2WORD_SKIP kind=pdf-render）"
            exit 0 ;;
        *)
            # 位置参数：只认第一个（稿件）。**不认识的选项与多余的位置参数都报错**——
            # 静默 shift 会让 `--templte x.docx` 这种手误悄悄失效（同目录有 .txt 时
            # 就静默用了生成的模板），而人以为模板给对了。
            if [[ "$1" == -* ]]; then
                echo "错误: 不认识的选项 $1"
                echo "  用法: bash export.sh input.md [-r 格式要求.txt] [-t template.docx] -o out.docx"
                echo "  全部选项见: bash export.sh --help"
                exit 1
            fi
            if [[ -z "$INPUT" ]]; then
                INPUT="$1"
            else
                echo "错误: 多了一个位置参数 $1（只接受一个输入稿件）"
                exit 1
            fi
            shift ;;
    esac
done

if [[ -z "$INPUT" || ! -f "$INPUT" ]]; then
    echo "错误: 输入文件不存在或未指定: $INPUT"
    exit 1
fi

# 早校验：取值写错时不该等到渲染完（渲染很慢）才在公式后处理那一步报错
if [[ "$EQ_NUMBER_STYLE" != "asis" && "$EQ_NUMBER_STYLE" != "cjk" ]]; then
    echo "错误: --eq-number-style 只接受 asis 或 cjk，收到: $EQ_NUMBER_STYLE"
    exit 1
fi

# 按章编号 + 编号外观仍是默认 → 多半是漏带了 --eq-number-style cjk。
# **这一项没有任何闸门能发现**：漏了就是静默产出 (5.1)（点号、半角括号），
# check_md / post_flight / audit 三道闸门全部照绿——正是本工具最怕的那种失败。
# 只提醒、不阻断：英文稿开了 chapters 而用 (5.1) 是合法的。
if [[ "$EQ_NUMBER_STYLE" == "asis" ]] && grep -qE 'chapters:[[:space:]]*true' "$INPUT" \
        && grep -q '{#eq-' "$INPUT"; then
    echo "提示: 稿件 YAML 开了 crossref.chapters（按章编号），但公式编号外观是默认的 (5.1)。" >&2
    echo "      中文学位论文通常写作 （5-1）——需要的话加 --eq-number-style cjk。" >&2
fi

if [[ -n "$REQUIREMENTS" && ! -f "$REQUIREMENTS" ]]; then
    echo "❌ -r 指定的格式要求文件不存在: $REQUIREMENTS" >&2
    exit 1
fi

# abspath <file>: 文件路径解析为绝对路径并展开符号链接（macOS /tmp → /private/tmp）
abspath() {
    local p="$1"
    if [[ -z "$p" ]]; then
        echo ""
        return
    fi
    local dir
    dir="$(cd "$(dirname "$p")" && pwd -P)"
    echo "${dir}/$(basename "$p")"
}

# temp_path <目录> <名字> <后缀>：三个临时文件（清洗稿 / 展开稿 / 临时模板）的命名唯一来源。
# 名字一律带 $$，**不要改用 mktemp**：mktemp 只替换**结尾**的 X，而我们都要留后缀
# （`.docx` / `.md`），X 落在中间时 mktemp 原样返回字面量、还返回 0 —— 于是每次导出都写
# 同一个文件，同目录并发（主稿 + 独立表格）就互相覆盖，而流程全绿。$$ 与渲染中转文件
# （render_via_word.sh 的 `_md2word_render_in.$$.docx`）同一约定。
temp_path() {
    echo "${1}/.${2}_$$.${3}"
}

# 解析格式要求文件 REQ：显式 -r 优先；否则在模板同目录（或未传 -t 时在稿件同目录）找唯一的 .txt
REQ="$REQUIREMENTS"
if [[ -z "$REQ" ]]; then
    _search_dir=""
    if [[ -n "$TEMPLATE" ]]; then
        _search_dir="$(cd "$(dirname "$TEMPLATE")" 2>/dev/null && pwd -P || echo "")"
    else
        _search_dir="$(cd "$(dirname "$INPUT")" 2>/dev/null && pwd -P || echo "")"
    fi
    if [[ -n "$_search_dir" ]]; then
        _txts=("$_search_dir"/*.txt)          # 无匹配时保持字面量，靠 -f 过滤
        if [[ ${#_txts[@]} -eq 1 && -f "${_txts[0]}" ]]; then
            REQ="${_txts[0]}"
        fi
    fi
fi

# 显式 -t：文件必须存在。**这条不因有没有格式要求文件而放宽**——路径写错就该当场停下，
# 否则 `-t typo.docx` 会穿过前置检查（实时生成那一步因 -t 已给而跳过），预检还会先说
# "✅ 校验通过"，直到 pandoc 抛一句 `--reference-doc ... does not exist` 才算失败。
if [[ "$TEMPLATE_GIVEN" == true && ( -z "$TEMPLATE" || ! -f "$TEMPLATE" ) ]]; then
    echo "错误: -t 指定的模板不存在: ${TEMPLATE:-（空值）}"
    echo "  用法: bash export.sh input.md [-t template.docx] [-r 格式要求.txt] -o out.docx"
    exit 1
fi

# 既无格式要求文件、又无现成模板文件时报错阻断（不退回渲染器内置默认模板）
if [[ -z "$REQ" && -z "$TEMPLATE" ]]; then
    echo "错误: 模板不存在或未指定: 未传 -t，且同目录未找到唯一的格式要求 .txt"
    echo "  用法: bash export.sh input.md [-r 格式要求.txt] [-t template.docx] -o out.docx"
    echo "  日常导出只需同目录放唯一的格式要求 .txt（或传 -r），每次导出会自动实时生成临时模板。"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 输出路径默认值
if [[ -z "$OUTPUT" ]]; then
    OUTPUT="${INPUT%.*}.docx"
fi

# 检测渲染引擎：Quarto（本技能唯一支持引擎）
if ! command -v quarto &>/dev/null; then
    echo "错误: 未找到 Quarto 编译器，请先安装（brew install quarto）"
    exit 1
fi

# 检测 Python 依赖：缺了要给可操作的提示，而不是把 ModuleNotFoundError 回溯甩给用户
if ! command -v python3 &>/dev/null; then
    echo "错误: 未找到 python3（本技能的脚本都是 Python 3 写的）"
    exit 1
fi
MISSING_DEPS="$(python3 -c "import importlib.util as u; print('、'.join(m for m in ('docx', 'lxml', 'yaml') if u.find_spec(m) is None))")"
if [[ -n "$MISSING_DEPS" ]]; then
    echo "错误: 缺少 Python 依赖（$MISSING_DEPS）。先安装再导出："
    echo "      pip install -r \"$(cd "$SCRIPT_DIR/.." && pwd)/requirements.txt\""
    exit 1
fi

# ── 临时文件统一注册与清理陷阱（覆盖正常退出与异常中断）──
CLEANUP_FILES=()
cleanup_export_artifacts() {
    if [[ ${#CLEANUP_FILES[@]} -gt 0 ]]; then
        rm -f "${CLEANUP_FILES[@]}"
    fi
}
trap cleanup_export_artifacts EXIT INT TERM HUP QUIT

# ── 每次导出实时从格式要求文件生成临时模板（彻底消灭模板过期与二进制模板中间件入库）──
# 显式传了 -t 就以它为准：那是有意指定的模板（比如目标方自己发的 .docx），
# 不该被自动找到的要求文件顶掉；要求文件仍照常用于对账。
if [[ -n "$REQ" && "$TEMPLATE_GIVEN" == false ]]; then
    echo "🛠️  根据格式要求实时生成临时模板: $(basename "$REQ")..."
    GEN_TPL="$(temp_path "${TMPDIR:-/tmp}" export_tpl docx)"
    CLEANUP_FILES+=("$GEN_TPL")
    if ! python3 "$SCRIPT_DIR/generate_template.py" "$REQ" -o "$GEN_TPL"; then
        echo "❌ 模板实时生成未通过：请根据上方提示修复格式要求文件 ($REQ)。" >&2
        exit 1
    fi
    TEMPLATE="$GEN_TPL"
fi

# ── 源稿预处理（--strip-comments）──
CLEAN_INPUT=""
ORIG_INPUT_DIR=""
if $STRIP_COMMENTS; then
    # 副本**必须落在原稿同目录**：YAML 的 bibliography/csl、正文里的图片路径都是相对
    # 稿件目录写的，放 /tmp 会让它们全部解析失败（Quarto 与 check_md 都会静默丢图）。
    ORIG_INPUT_DIR="$(dirname "$INPUT")"
    CLEAN_INPUT="$(temp_path "$ORIG_INPUT_DIR" export_clean md)"
    CLEANUP_FILES+=("$CLEAN_INPUT")
    python3 - "$INPUT" > "$CLEAN_INPUT" <<'PREPROCESS_PY'
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()
sys.stdout.write(re.sub(r'<!--.*?-->', '', src, flags=re.DOTALL))
PREPROCESS_PY
    INPUT="$CLEAN_INPUT"
fi


INPUT_DIR="$(dirname "$INPUT")"
GIT_SOURCE_DIR="${ORIG_INPUT_DIR:-$INPUT_DIR}"
PROJECT_ROOT="$(cd "$GIT_SOURCE_DIR" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "")"

RESOURCE_PATH="$INPUT_DIR"
if [[ -n "$PROJECT_ROOT" && -d "$PROJECT_ROOT" ]]; then
    RESOURCE_PATH="$INPUT_DIR:$PROJECT_ROOT"
fi

# 导出前预检：check_md.py (strict)
if $CHECK_MD; then
    echo "🔍 导出前预检 (check_md strict)..."
    CHECK_MD_ARGS=(-t "$TEMPLATE")
    [[ -n "$REQ" ]] && CHECK_MD_ARGS+=(-r "$REQ")
    [[ -n "$RESOURCE_PATH" ]] && CHECK_MD_ARGS+=(--resource-dirs "$RESOURCE_PATH")
    if ! python3 "$SCRIPT_DIR/check_md.py" "$INPUT" "${CHECK_MD_ARGS[@]}"; then
        echo "❌ 预检未通过：请修复上述问题后重新导出。"
        echo "   （如确需跳过，可加 --no-check，但不推荐——静默失败风险由你承担）"
        exit 1
    fi
fi

# ── 源稿预处理：展开结构标记（目录 / 分节）──
# 放在预检**之后**：check_md 要校验作者写的标记本身（未独占一行、拼错的短代码都由它拦），
# 而 Quarto 只该看到展开成 OOXML 的结果。
if grep -q '{{<' "$INPUT"; then
    EXPANDED="$(temp_path "$(dirname "$INPUT")" export_markers md)"
    CLEANUP_FILES+=("$EXPANDED")
    if ! python3 "$SCRIPT_DIR/expand_markers.py" "$INPUT" -o "$EXPANDED" -t "$TEMPLATE"; then
        rm -f "$EXPANDED"
        exit 1
    fi
    INPUT="$EXPANDED"
fi

# 编译命令构建与执行
echo "🚀 采用 Quarto 引擎编译..."
# Quarto 子 shell 会 cd 到 TARGET_DIR，相对路径全部失效，必须提前转为绝对路径
INPUT="$(abspath "$INPUT")"
TEMPLATE="$(abspath "$TEMPLATE")"

mkdir -p "$(dirname "$OUTPUT")"
TARGET_DIR="$(cd "$(dirname "$OUTPUT")" && pwd -P)"
OUTPUT_ABS="$TARGET_DIR/$(basename "$OUTPUT")"

RENDER_CMD=(quarto render "$INPUT" --to docx -o "$(basename "$OUTPUT")" --reference-doc "$TEMPLATE")
# 若稿件 YAML 的 csl: 写的是技能内置 csl/ 下的文件名（如 apa.csl），且稿件同目录不存在该文件，
# 自动将内置 CSL 的绝对路径通过 -M csl=... 传给 Quarto，实现零拷贝即插即用。
BUILTIN_CSL="$(python3 - "$INPUT" "$SCRIPT_DIR" <<'RESOLVE_CSL_PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from skill_utils import split_frontmatter, resolve_manuscript_path
import yaml
md_path = Path(sys.argv[1]).resolve()
skill_csl_dir = Path(sys.argv[2]).resolve().parent / "resources" / "csl"
fm_text, _ = split_frontmatter(md_path.read_text(encoding="utf-8"))
if fm_text:
    try:
        data = yaml.safe_load(fm_text)
        if isinstance(data, dict) and data.get("csl"):
            p, how = resolve_manuscript_path(str(data["csl"]), md_path, skill_csl_dir=skill_csl_dir)
            if how == "skill-builtin":
                print(str(p), end="")
    except Exception:
        pass
RESOLVE_CSL_PY
)"
if [[ -n "$BUILTIN_CSL" ]]; then
    RENDER_CMD+=(-M "csl=$BUILTIN_CSL")
fi

# 正文引用直接跳到文末对应条目（docx 里落成内部书签链接 w:hyperlink w:anchor="ref-<key>"）。
# 默认打开：稿件用了 .bib 就有用，没用就是空转，不值得为它去解析一遍 YAML。
# **稿件 YAML 里写 link-citations: false 可以关掉**——实测 YAML 覆盖 -M，命令行只是默认值。
RENDER_CMD+=(-M "link-citations=true")

# --resource-path：让图片在多种路径写法下都能解析。
# 不含该参数时 Quarto 会把绝对路径（/Users/...）误解析成 ./Users/... 相对路径，
# 导致图片被静默丢弃（只有 warning 不报错）。追加根 "/" 以支持绝对路径。
if [[ -n "$RESOURCE_PATH" ]]; then
    RENDER_CMD+=(--resource-path "$RESOURCE_PATH:/")
fi

# 渲染失败时 set -e 会中止，但用户只看到 Quarto 自己的原始输出（JS 栈 / GHC 回溯），
# 看不出"产物没生成、后面的闸门一个都没跑"。补一行结论，把状态说清楚。
if ! (cd "$TARGET_DIR" && "${RENDER_CMD[@]}"); then
    echo "" >&2
    echo "❌ 渲染失败：Quarto 未产出 docx（上方是它的原始输出）。" >&2
    echo "   后续闸门（公式后处理 / 产物完整性 / 导出后抽查）都没跑。" >&2
    echo "   磁盘上同名文件若还在，那是上一次的旧产物，不是这次的结果。" >&2
    exit 1
fi

# 后处理：学术公式居中 + 编号靠右排版优化与样式深度净化
# 这一步不是可选修饰：它清理主题属性并重构公式排版。缺脚本 = 技能
# 装坏了；静默跳过会导出一个"看着正常"的不合格 docx，链路上不报任何错。
if [[ ! -f "$SCRIPT_DIR/fix_docx_equations.py" ]]; then
    echo "❌ 缺少 $SCRIPT_DIR/fix_docx_equations.py（技能安装不完整），导出中止。" >&2
    exit 1
fi
if [[ ! -f "$OUTPUT_ABS" ]]; then
    echo "❌ Quarto 未产出 $OUTPUT_ABS（未报错但没有产物），导出中止。" >&2
    exit 1
fi
echo "📐 自动优化公式排版（居中公式 + 靠右对齐编号）与主题深度净化..."
# 表格的列宽由后处理按稿件里分隔行的短横线（写得不均匀时）或各列文字量来定，
# 总宽一律撑满版心。所以要把它连稿件一起交给它。
python3 "$SCRIPT_DIR/fix_docx_equations.py" "$OUTPUT_ABS" \
    --eq-number-style "$EQ_NUMBER_STYLE" --manuscript "$INPUT"

# Post-flight 完整性检查：导出链上唯一的数据丢失守护。
# 稿件里的每个三位以上小数都必须出现在 docx 里，缺一个即阻断（确定性比对，无阈值）。
# 独立脚本 post_flight_check.py 避免 bash 嵌套引号破坏；逃逸 --no-postflight。
if $POSTFLIGHT; then
    # 缺脚本 = 守卫不存在。静默跳过等于把"唯一的数据丢失守护"悄悄关掉。
    if [[ ! -f "$SCRIPT_DIR/post_flight_check.py" ]]; then
        echo "❌ 缺少 $SCRIPT_DIR/post_flight_check.py（技能安装不完整），导出中止。" >&2
        echo "   确需放过：加 --no-postflight（不推荐——静默丢数据由你承担）。" >&2
        exit 1
    fi
    if ! python3 "$SCRIPT_DIR/post_flight_check.py" "$INPUT" "$OUTPUT_ABS"; then
        echo "❌ 产物完整性检查未通过：docx 疑似丢内容（见上方缺失清单）。" >&2
        echo "   确需放过：加 --no-postflight（不推荐——静默丢数据由你承担）。" >&2
        exit 1
    fi
fi

# 导出后抽查：产物 ↔ 格式要求文件逐条对账（字体/字号/加粗/倾斜/纸张/页边距/
# 页码/奇偶页/首页留白）。这些都是 XML 里的确定值，能脚本核对；域展开后的视觉
# 效果不在此列，要看得渲染 PDF。逃逸 --no-audit。
if $AUDIT; then
    if [[ ! -f "$SCRIPT_DIR/audit_export.py" ]]; then
        echo "❌ 缺少 $SCRIPT_DIR/audit_export.py（技能安装不完整），导出中止。" >&2
        exit 1
    fi
    if [[ -z "$REQ" ]]; then
        # 跳过 ≠ 通过：没查就明说没查，不冒充"抽查没问题"。
        echo "⚠️ 导出后抽查跳过：未找到格式要求文件（用 -r 指定；同目录只放一个 .txt 可自动识别）。"
    elif ! python3 "$SCRIPT_DIR/audit_export.py" "$OUTPUT_ABS" -r "$REQ"; then
        echo "❌ 导出后抽查未通过：产物与格式要求文件对不上（见上方清单）。" >&2
        echo "   确需放过：加 --no-audit；或用 -r 指定正确的要求文件。" >&2
        exit 1
    fi
fi

# ── 可选：导出后渲染 PDF（--pdf）──
# 只有 Word 会把**域**真正展开——目录、页眉章名（STYLEREF）、页码（PAGE）。
# 要核对这几项就必须走它，别的渲染器看到的不是读者看到的东西。
# 通道细节（为什么要绕道 Word 自己的容器）见 render_via_word.sh 头部注释。
#
# 机器可判别：请求了渲染却没渲染，**不是成功**。故打一行 MD2WORD_SKIP 并以
# 退出码 3 结束——只读退出码的调用方（脚本 / CI / Agent）才不会把"0"读成
# "PDF 已生成"。跳过本身是正常的（非 macOS、没装 Word），所以不是 1。
RENDER_SKIP=""
if $MAKE_PDF; then
    RENDER_SH="$SCRIPT_DIR/render_via_word.sh"
    PDF_ABS="${OUTPUT_ABS%.*}.pdf"
    if [[ "$(uname)" != "Darwin" ]]; then
        RENDER_SKIP="not-darwin"
        echo "⚠️ --pdf 跳过：该通道用 AppleScript 驱动本机 Microsoft Word，仅 macOS 可用。"
    elif [[ ! -f "$RENDER_SH" ]]; then
        RENDER_SKIP="no-render-script"
        echo "⚠️ --pdf 跳过：找不到 $RENDER_SH"
    elif [[ ! -d "$HOME/Library/Containers/com.microsoft.Word/Data" ]]; then
        RENDER_SKIP="no-word"
        echo "⚠️ --pdf 跳过：本机未安装 Microsoft Word。"
    else
        echo "🖨️  用本机 Word 渲染 PDF（域会被展开）..."
        if ! bash "$RENDER_SH" "$OUTPUT_ABS" "$PDF_ABS"; then
            echo "❌ PDF 渲染失败。docx 已正常生成: $OUTPUT_ABS" >&2
            exit 1
        fi
    fi
fi

# 成功消息放在最后：中途 exit 1 时不该已经宣布过"生成成功"。
echo "✅ Word 文档导出成功: $OUTPUT_ABS"

if [[ -n "$RENDER_SKIP" ]]; then
    echo "MD2WORD_SKIP kind=pdf-render reason=$RENDER_SKIP"
    echo "   docx 已正常生成，未受影响；PDF 未产出（--pdf 请求未完成）。" >&2
    exit 3
fi
