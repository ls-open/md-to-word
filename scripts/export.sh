#!/usr/bin/env bash
# export.sh — 仓库里的导出入口：用本目录的 `src/` 跑，不依赖是否装过包。
#
# 这个仓库既是 pip 包的源码，也是一个技能目录（`SKILL.md` 是入口）。所以这里**优先用
# 仓库自己的源码**——克隆下来跑的永远是仓库里这一份，不会被机器上装过的旧版本悄悄顶掉。
# 源码缺失时才退回已安装的 `md-to-word`（例如只拷了 scripts/ 的情况）。
#
# 用法:
#   bash export.sh 稿件.md -o 输出.docx
#   bash export.sh 稿件.md -r 要求.txt -o 输出.docx
#   bash export.sh 稿件.md --preset en-nature -o 输出.docx
#   bash export.sh --contract        # 契约速查 + 手册与预设的路径
#   bash export.sh --help            # 全部选项
#
# 退出码: 0=全部完成 / 1=稿件、门禁或依赖问题 / 3=docx 已生成但 --pdf 未渲染
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(dirname "$SCRIPT_DIR")"
VENDORED="$ROOT/src/md_to_word"

# 1. 仓库自带的实现优先
if [[ -d "$VENDORED" ]] && command -v python3 >/dev/null 2>&1; then
    if python3 -c "import docx, lxml, yaml, latex2mathml, citeproc" >/dev/null 2>&1; then
        export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
        exec python3 -m md_to_word "$@"
    fi
    cat >&2 <<'MSG'
缺少 Python 依赖，先在仓库根目录执行一次：

  pip install -r requirements.txt

（只装依赖，引擎就在本目录的 src/ 里。）
MSG
    exit 1
fi

# 2. 没有源码时退回已安装的包
if command -v md-to-word >/dev/null 2>&1; then
    exec md-to-word "$@"
fi

cat >&2 <<'MSG'
找不到实现：本目录缺 src/md_to_word，也没有已安装的 md-to-word。

  pip install md-to-word-docx      # 改用 pip 分发的版本

或重新获取完整仓库（自带 src/）。
MSG
exit 1
