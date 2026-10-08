#!/bin/bash
# render_via_word.sh — 用本机 Microsoft Word 把 docx 渲染成 PDF（macOS）
#
# 用法：bash render_via_word.sh <输入.docx> <输出.pdf>
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
if [[ -z "$IN" || -z "$OUT" ]]; then
    echo "用法: bash render_via_word.sh <输入.docx> <输出.pdf>" >&2
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

# 「打开 → 重排版 → 另存 PDF → 关闭」。save as 是另存，**不改动原 docx**。
# with timeout：osascript 平时会一直等 Word 应答；Word 一旦弹出任何模态框
# （首次运行、登录、恢复文档、宏安全提示），这里就**永久挂死**，无人值守时
# 整条流水线卡住。给 Apple 事件加超时，超时即报错退出，由调用方处置。
osascript - "$CIN" "$COUT" "$IN_NAME" <<'APPLESCRIPT'
on run argv
    set inPath to item 1 of argv
    set outPath to item 2 of argv
    set inName to item 3 of argv
    with timeout of 180 seconds
        tell application "Microsoft Word"
            set d to open file name inPath with read only
            repaginate d
            save as d file name outPath file format format PDF
            -- save as 成 PDF 之后，原来的文档引用会失效，close d 会报 -1708；
            -- 按名字找回并关闭，找不到就算了（不能 close every document——那会关掉
            -- 用户自己开着的其它文档）。
            try
                close d saving no
            on error
                try
                    repeat with doc in documents
                        if (name of doc as text) contains inName then
                            close doc saving no
                            exit repeat
                        end if
                    end repeat
                end try
            end try
        end tell
    end timeout
    return "OK"
end run
APPLESCRIPT

[[ -f "$COUT" ]] || { echo "错误: Word 未产出 PDF（渲染失败或超时，见上方 osascript 报错）" >&2; exit 1; }
cp "$COUT" "$OUT_ABS"
echo "✓ 已渲染: $OUT_ABS"
