#!/usr/bin/env bash
# export.sh — 技能入口壳：找到已安装的 md-to-word，把参数原样交给它。
#
# **技能不含实现**。实现是一个 pip 包（`pipx install md-to-word`），本文件只做转发。
# 这样升级是 `pipx upgrade md-to-word` 一条命令，不必重装技能；技能文件只在文档
# 需要变化时才动。仓库里自带的 `src/` 只在开发检出、且没有安装过包时兜底使用。
#
# 用法:
#   bash export.sh 稿件.md -o 输出.docx
#   bash export.sh 稿件.md --preset en-nature -o 输出.docx
#   bash export.sh --help            # 全部选项
#   bash export.sh --version         # 确认引擎版本（低版本先 pipx upgrade）
#
# 退出码: 0=全部完成 / 1=稿件、门禁或依赖问题 / 3=docx 已生成但 --pdf 未渲染
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SKILL_ROOT="$(dirname "$SCRIPT_DIR")"

# 1. 已安装的实现优先：这是分发形态下的正常路径，升级也走这条
if command -v md-to-word >/dev/null 2>&1; then
    exec md-to-word "$@"
fi

# 2. 开发检出兜底：有源码、且依赖齐全时，直接用仓库里的这份
if [[ -d "$SKILL_ROOT/src/md_to_word" ]] \
    && command -v python3 >/dev/null 2>&1 \
    && python3 -c "import docx, lxml, yaml, latex2mathml, citeproc" >/dev/null 2>&1; then
    export PYTHONPATH="$SKILL_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
    exec python3 -m md_to_word "$@"
fi

# 3. 都没有：给出可照抄的安装命令，不要让用户对着 command not found 猜
cat >&2 <<'EOF'
未找到 md-to-word。这个技能只是入口，实现要单独安装：

  pipx install md-to-word                     # 已发布到 PyPI 后（推荐，隔离环境）
  pip install "git+https://github.com/ls-open/md-to-word@main"   # 在此之前

更新用同一条：pipx upgrade md-to-word（或 pip install --upgrade …）
如果你是从源码检出的仓库里直接运行，先在仓库根目录执行 pip install -r requirements.txt。
EOF
exit 1
