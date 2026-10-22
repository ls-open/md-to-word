#!/bin/bash
# render_via_word.sh — 用本机 Microsoft Word 把 docx 渲染成 PDF（macOS）
#
# 用法：bash render_via_word.sh <输入.docx> <输出.pdf> [更新后.docx]
#
# 第三项可选：把**域更新之后**的 docx 也留一份。默认不落 —— 原稿一个字都不改是这条
# 通道的承诺（渲染走容器里的中转副本）。但排查「目录/页眉这类域到底被 Word 怎么算的」
# 时，只有更新后的文档内部才看得见（段落挂的样式名、Word 新造了哪些样式）。
# 需要就传第三项，别另写 AppleScript：容器、更新域的时机、关窗重试都在这份脚本里。
#
# ── 为什么绕道 Word 自己的容器 ──
# Word for Mac 是**沙箱应用**。AppleScript 交给它一个容器外的路径时，macOS 会弹
# 「授予文件访问权限」；而且这个弹窗**每次都要重新授权**——实测其选择器只能授权
# **单个文件，不能授权目录**，所以「授权一次以后都不问」做不到，逐次视觉核对没法进行。
#
# 把文件先拷进 Word 自己的容器（~/Library/Containers/com.microsoft.Word/Data/）再渲染，
# Word 对自己的容器有完全访问权，**不弹窗**。实测有效。
#
# 查证过的替代方案（都不如这条）：
#   · GUI 脚本用 System Events 点弹窗按钮——社区公认的通用办法，但要动用户的无障碍权限；
#   · 换 LibreOffice 渲染——不经过沙箱，但不展开 Word 的域（目录/STYLEREF/PAGE 会空白），
#     而我们核对的核心恰恰就是这些域；
#   · `open -a`（走 LaunchServices）绕开 AppleScript 的 open——实测无效，照样弹。
#
# AppleScript 本身只能在 macOS 上用，本脚本是 macOS 专用。

set -euo pipefail

IN="${1:-}"
OUT="${2:-}"
KEEP="${3:-}"
if [[ -z "$IN" || -z "$OUT" ]]; then
    echo "用法: bash render_via_word.sh <输入.docx> <输出.pdf> [更新后.docx]" >&2
    exit 1
fi
[[ -f "$IN" ]] || { echo "错误: 输入文件不存在: $IN" >&2; exit 1; }

CONTAINER="$HOME/Library/Containers/com.microsoft.Word/Data"
if [[ ! -d "$CONTAINER" ]]; then
    # 装了 Word 但从未启动过 → 容器目录还没生成。这种情况要给出可操作的话，
    # 不能笼统说"没装 Word"，否则用户对着装好的 Word 无从下手。
    if [[ -d "/Applications/Microsoft Word.app" ]]; then
        echo "错误: 找到 Word，但它的容器目录还不存在：$CONTAINER" >&2
        echo "      容器在 Word 首次启动后才会生成——请先手动打开一次 Word 再重试。" >&2
    else
        echo "错误: 本机未安装 Microsoft Word（找不到 /Applications/Microsoft Word.app）" >&2
    fi
    exit 1
fi

IN_ABS="$(cd "$(dirname "$IN")" && pwd -P)/$(basename "$IN")"
mkdir -p "$(dirname "$OUT")"
OUT_ABS="$(cd "$(dirname "$OUT")" && pwd -P)/$(basename "$OUT")"
KEEP_ABS=""
if [[ -n "$KEEP" ]]; then
    mkdir -p "$(dirname "$KEEP")"
    KEEP_ABS="$(cd "$(dirname "$KEEP")" && pwd -P)/$(basename "$KEEP")"
fi

# 中转名带 PID：两次渲染同时跑时，固定名会互相覆盖中转文件、互删对方产物。
# 带 PID 后各自的文件互不相干；万一某次清理没跑成（SIGKILL、断电），残留也只是
# 一次性垃圾（前缀固定，可整批清理），不会串到下一次运行。
CIN="$CONTAINER/_md2word_render_in.$$.docx"
COUT="$CONTAINER/_md2word_render_out.$$.pdf"
IN_NAME="$(basename "$CIN")"
cleanup() { rm -f "$CIN" "$COUT"; }
# 除了正常退出，被 Ctrl-C / kill 打断时也要清（只有 SIGKILL 拦不住，那种情况见上）
trap cleanup EXIT INT TERM HUP QUIT

cp "$IN_ABS" "$CIN"
rm -f "$COUT"

# 「打开 → 重排版 → 更新域 → 另存 PDF → 关闭」。save as 是另存，**不改动原 docx**。
# with timeout：osascript 平时会一直等 Word 应答；Word 一旦弹出任何模态框
# （首次运行、登录、恢复文档、宏安全提示），这里就**永久挂死**，无人值守时
# 整条流水线卡住。给 Apple 事件加超时，超时即报错退出，由调用方处置。
osascript - "$CIN" "$COUT" "$IN_NAME" "${KEEP_ABS:+"1"}" <<'APPLESCRIPT'
on run argv
    set inPath to item 1 of argv
    set outPath to item 2 of argv
    set inName to item 3 of argv
    set wantKeep to (count of argv) > 3 and (item 4 of argv is not "")
    with timeout of 180 seconds
        tell application "Microsoft Word"
            -- **必须读写打开**。实测 Word 在 `with read only` 下不执行域更新：
            -- update 调用照样返回成功，结果却纹丝不动（目录页码全停在 1）。
            -- 这里打开的是容器里的中转副本（CIN），退出时由 trap 清掉，
            -- 传出去的 PDF 走 save as 另存，用户拿到的 .docx 一个字都不会变。
            set d to open file name inPath
            repaginate d
            -- 更新域：目录页码与页眉的 STYLEREF 都要 Word 现算。
            -- **光 repaginate 不够**——它只重算分页，不动域里已存的结果，目录页码会停在
            -- 插入域那一刻的值（实测：四章全写「1」）。这份 PDF 存在的意义就是核对目录/
            -- 页眉这类动态域，域没更新等于没核对。
            -- 用 `update field (every field of d)` 而不是 `update toc`：我们的目录域生在
            -- 目录写在 <w:sdt> 内容控件里，Word 不把它归入 table of contents 集合
            -- （实测 TOC 个数=0），只有按 field 逐个更新才够得着。
            update field (every field of d)
            repaginate d
            save as d file name outPath file format format PDF

            -- 要保留「更新后」的 docx 时，就地存回那份**容器里的中转副本**（不是用户的
            -- 原稿），退出后由脚本拷到调用方指定的位置。用 `save d` 而不是再写一条
            -- save as：另存要指定 file format 常量（`format document` 在 Word for Mac
            -- 上不认，实测 -1728），就地存没这个问题。
            if wantKeep then
                save d
            end if

            -- 关闭这次打开的文档窗口。
            -- **必须重试**：save as 刚返回时 Word 还在收尾，此刻访问 documents 会随机
            -- 抛 -1708（实测：不 delay 直接 repeat 就报「every document 不理解 count」）。
            -- 原先是 try 一包了事，抛错被静默吞掉，文档窗口就留在屏幕上——连续渲染几次
            -- 用户屏幕上会攒出一排打开的 Word 窗口。
            -- 关不掉就复核一次：名字还在说明没关成，隔一秒再来；最多三轮。
            repeat 3 times
                delay 1
                try
                    close d saving no
                end try
                set remaining to 0
                try
                    repeat with doc in documents
                        if (name of doc as text) contains inName then
                            set remaining to remaining + 1
                        end if
                    end repeat
                on error
                    -- 读不到文档列表时不敢断定已关掉，再来一轮
                    set remaining to 1
                end try
                if remaining is 0 then exit repeat
            end repeat
        end tell
    end timeout
    return "OK"
end run
APPLESCRIPT

[[ -f "$COUT" ]] || { echo "错误: Word 未产出 PDF（渲染失败或超时，见上方 osascript 报错）" >&2; exit 1; }
cp "$COUT" "$OUT_ABS"
echo "✓ 已渲染: $OUT_ABS"

if [[ -n "$KEEP_ABS" ]]; then
    # 与输入**逐字节相同** = Word 没执行 save（没存成却把中转副本交出去，等于拿输入冒充
    # 结果——排查域的时候这种"看着成功其实没更新"最误事）。命中就明确失败。
    if cmp -s "$CIN" "$IN_ABS"; then
        echo "错误: 中转副本与输入逐字节相同，Word 没有执行保存（更新后的 docx 未取到）" >&2
        exit 1
    fi
    cp "$CIN" "$KEEP_ABS"
    echo "✓ 已保留更新后的 docx: $KEEP_ABS"
fi
