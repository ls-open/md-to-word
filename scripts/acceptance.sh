#!/usr/bin/env bash
# acceptance.sh — 发布前的安装验收：建包 → 干净 venv 安装 → 把所有入口跑一遍。
#
# 为什么单独一遍：测试跑的是源码树，用户拿到的是 wheel。两者之间会漏东西——
# `guide.md` 没进包、控制台脚本指向错的模块、依赖少写一个，测试全绿但装完不能用。
# 每次发版前跑一次，比事后去 PyPI 上发现问题便宜得多。
#
# 用法: bash scripts/acceptance.sh
# 退出码: 0 通过 / 1 有一项没过
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# 建在 /tmp 下：Word for Mac 是沙箱应用，读不到系统临时目录（/var/folders/…），
# 那样 --pdf 会一直按"跳过"返回 3，验收就白测了。
TMP="$(mktemp -d /tmp/md-to-word-accept.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

step() { printf '\n== %s\n' "$1"; }

step "构建 wheel"
python3 -m pip wheel "$ROOT" --no-deps -w "$TMP/dist" -q
WHEEL=$(ls "$TMP"/dist/*.whl)
echo "   $WHEEL"

step "装进干净 venv"
python3 -m venv "$TMP/venv"
"$TMP/venv/bin/pip" install -q "$WHEEL"
BIN="$TMP/venv/bin"

step "命令行入口"
"$BIN/md-to-word" --version
"$BIN/md-to-word" --contract >/dev/null && echo "   --contract ok"
"$BIN/md-to-word" --guide | head -1 | grep -q "Markdown" && echo "   --guide ok"
"$BIN/md-to-word-template" --help >/dev/null && echo "   md-to-word-template ok"

step "包内文档"
SITE=$("$TMP/venv/bin/python" -c "import md_to_word, pathlib; print(pathlib.Path(md_to_word.__file__).parent)")
for f in resources/guide.md resources/manual.md resources/manual_en.md; do
    test -f "$SITE/$f" || { echo "   缺少 $f"; exit 1; }
done
echo "   guide + 两份手册都在"

step "init → 导出"
mkdir "$TMP/work" && cd "$TMP/work"
"$BIN/md-to-word" init
"$BIN/md-to-word" hello.md -o hello.docx --json |
    "$TMP/venv/bin/python" -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["output"], d'
test -f hello.docx

step "PDF 核对（不可用时跳过，退出码 3）"
set +e
"$BIN/md-to-word" hello.md -o proof.docx --pdf >/dev/null 2>&1
PDF_CODE=$?
set -e
case "$PDF_CODE" in
    0) echo "   PDF 已渲染" ;;
    3) echo "   本机不可用，按契约跳过（退出码 3）" ;;
    *) echo "   非预期退出码: $PDF_CODE"; exit 1 ;;
esac

step "从产物反推要求文件"
"$BIN/md-to-word-template" hello.docx -o derived.txt >/dev/null
grep -q "纸张\|Paper" derived.txt && echo "   反推可用"

printf '\n验收通过。\n'
