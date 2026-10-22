#!/usr/bin/env bash
# export.sh — 技能入口壳（Markdown → Word）
#
# 本文件只做三件事：找到 python3、把技能自带的 src/ 放进模块搜索路径、把参数原样交给
# `python -m md_to_word`。**导出逻辑一行都不在这里**——实现全部在 src/md_to_word/，
# 与 pip 安装后的 `md-to-word` 命令是同一份代码。
#
# 保留这个壳的原因：Claude Code 技能与 nature-skills 那类集成，入口约定是
# `bash <技能目录>/scripts/export.sh`，不会先 pip install。
#
# 用法:
#   bash export.sh 稿件.md -o 输出.docx
#   bash export.sh 稿件.md --preset en-nature -o 输出.docx
#   bash export.sh --help            # 全部选项
#
# 退出码: 0=全部完成 / 1=稿件或门禁问题 / 2=环境问题（缺 Quarto 或依赖）/ 3=docx 已生成但 --pdf 未渲染
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SKILL_ROOT="$(dirname "$SCRIPT_DIR")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "错误: 未找到 python3（本技能的实现是 Python 3，见 requirements.txt）" >&2
    exit 1
fi

# 技能目录自带 src/ 时必须优先用它：克隆即用，不要求 pip install。
# 放在 PYTHONPATH 前面，避免用户环境里另一份旧版 md-to-word 顶替本技能的实现。
if [[ -d "$SKILL_ROOT/src/md_to_word" ]]; then
    export PYTHONPATH="$SKILL_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
fi

exec python3 -m md_to_word "$@"
