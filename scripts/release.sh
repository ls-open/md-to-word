#!/usr/bin/env bash
# release.sh — 一次发版的机械动作：升版本号 → 重出五份样例 → 重建样张页 → 跑门禁 → 提交并打 tag。
#
# 只做仓库内的事。推远端要 `--push`，传 PyPI 要 `--publish`；两个都不带时，跑完就先停在那儿，
# 你可以先看 diff 再决定。
#
# 用法:
#   bash scripts/release.sh 3.6.1 --dry-run          # 只报告将做什么，不落任何改动
#   bash scripts/release.sh 3.6.1                    # 改造 + 提交 + 打 tag（不推、不发）
#   bash scripts/release.sh 3.6.1 --push --publish   # 再加推送与上传
#   bash scripts/release.sh 3.6.1 --full             # 提交前额外跑 acceptance.sh（建 wheel、干净 venv 装一遍）
#
# 为什么必须重出样例：`docProps` 里记着版本号，升版之后仓库里提交的 `.docx` 与现场导出的
# 对不上，`test_committed_docx_matches_a_fresh_export` 会当场红——它红得对。
#
# 退出码: 0=完成 / 1=前置检查或门禁没过 / 2=用法错误
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"

VERSION="${1:-}"
[ -n "$VERSION" ] || { echo "用法: bash scripts/release.sh <x.y.z> [--dry-run] [--push] [--publish] [--full]" >&2; exit 2; }
shift

DRY_RUN=0 PUSH=0 PUBLISH=0 FULL=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --push)    PUSH=1 ;;
        --publish) PUBLISH=1 ;;
        --full)    FULL=1 ;;
        *) echo "未知参数: $arg" >&2; exit 2 ;;
    esac
done

# 五份样例：目录 | 产物名 | 稿件 | 格式文件（`-` 表示同目录没有 format.txt，按语言选预设）
DEMOS=(
    "00_quickstart      hello        hello.md        format.txt"
    "01_chinese_thesis  thesis_sample thesis_sample.md format.txt"
    "02_modern_report   report_sample report_sample.md format.txt"
    "03_english_paper   paper        paper.md        -"
    "04_zh_tw_paper     paper_zh_tw  paper_zh_tw.md  format.txt"
)

die() { echo "✗ $*" >&2; exit 1; }
step() { echo; echo "── $* ──"; }

# ── 1. 前置检查 ────────────────────────────────────────────────────────────────
step "前置检查"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "版本号要写成 x.y.z，收到: $VERSION"
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || die "当前不在 main 分支"
git diff --quiet && git diff --cached --quiet || die "工作区不干净，先提交或 stash"

CUR="$(grep -oE '__version__ = "[^"]+"' src/md_to_word/__init__.py | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
[ -n "$CUR" ] || die "读不到当前版本号"
python3 - "$CUR" "$VERSION" <<'PY' || die "新版本号必须大于当前版本号"
import sys
cur, new = (tuple(int(x) for x in v.split(".")) for v in sys.argv[1:3])
raise SystemExit(0 if new > cur else 1)
PY
echo "   $CUR → $VERSION"
if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
    die "tag v$VERSION 已存在"
fi

if [ "$DRY_RUN" = 1 ]; then
    step "dry-run：将要做的事"
    echo "  1. 改 src/md_to_word/__init__.py 与 .codebuddy-plugin/plugin.json 的版本号"
    echo "  2. 重出 ${#DEMOS[@]} 份样例的 .docx/.pdf 与首页图（需要本机 Word）"
    echo "  3. python3 web/build.py 重建样张页与 docs/assets"
    if [ "$FULL" = 1 ]; then
        echo "  4. 跑 pytest 与 scripts/acceptance.sh"
    else
        echo "  4. 跑 pytest"
    fi
    echo "  5. git commit「release: $VERSION」并打 tag v$VERSION"
    if [ "$PUSH" = 1 ]; then echo "  6. git push origin main --tags"; fi
    if [ "$PUBLISH" = 1 ]; then echo "  7. uv build && uv publish（传 PyPI）"; fi
    echo
    echo "   没有落任何改动。"
    exit 0
fi

# ── 2. 升版本号 ────────────────────────────────────────────────────────────────
# 只有两处是手写的：__version__ 是权威，plugin.json 是插件市场直接读的静态第二份。
# 样张页与 docProps 里的版本由 web/build.py 与导出器从 __version__ 算，不在这里改。
step "升版本号"
python3 - "$VERSION" <<'PY'
import re, sys
from pathlib import Path

new = sys.argv[1]
for path, pattern in (
    (Path("src/md_to_word/__init__.py"), r'__version__ = "[^"]+"'),
    (Path(".codebuddy-plugin/plugin.json"), r'"version":\s*"[^"]+"'),
):
    text = path.read_text(encoding="utf-8")
    text2, n = re.subn(
        pattern,
        lambda m: re.sub(r'"[^"]+"$', f'"{new}"', m.group(0)),
        text,
    )
    assert n == 1, f"{path}: 找到 {n} 处版本号，应为一处"
    path.write_text(text2, encoding="utf-8")
    print(f"   {path}: {n} 处")
PY

# ── 3. 重出样例 ────────────────────────────────────────────────────────────────
step "重出样例（docx / pdf / 首页图）"
for row in "${DEMOS[@]}"; do
    read -r dir stem md fmt <<<"$row"
    (
        cd "demo/$dir"
        rm -f page-*.png
        set +e
        if [ "$fmt" = "-" ]; then
            bash ../../scripts/export.sh "$md" -o "$stem.docx" --pdf
        else
            bash ../../scripts/export.sh "$md" -r "$fmt" -o "$stem.docx" --pdf
        fi
        rc=$?
        set -e
        [ "$rc" = 0 ] || die "demo/$dir 导出失败（退出码 $rc，3 = docx 出了但 PDF 没渲染，可能是本机没装 Word）"
        pdftoppm -png -r 110 "$stem.pdf" page
        echo "   demo/$dir → $stem.docx / .pdf / $(ls page-*.png | wc -l | tr -d ' ') 页图"
    )
done

# ── 4. 重建样张页 ──────────────────────────────────────────────────────────────
step "重建样张页"
python3 web/build.py

# ── 5. 门禁 ────────────────────────────────────────────────────────────────────
step "门禁"
python3 -m pytest -q
if [ "$FULL" = 1 ]; then
    step "安装验收（acceptance.sh）"
    bash scripts/acceptance.sh
fi

# ── 6. 提交并打 tag ────────────────────────────────────────────────────────────
step "提交并打 tag"
git add -A
git commit -q -m "release: $VERSION"
git tag -a "v$VERSION" -m "v$VERSION"
echo "   $(git log -1 --format='%h %s')"
echo "   变动 $(git show --stat --format='' HEAD | tail -1)"

# ── 7. 推送 / 上传（都要显式要求） ─────────────────────────────────────────────
if [ "$PUSH" = 1 ]; then
    step "推送到 origin"
    git push origin main --tags
fi

if [ "$PUBLISH" = 1 ]; then
    step "构建并上传 PyPI"
    command -v uv >/dev/null || die "没装 uv；也可以用 python3 -m build && twine upload dist/*"
    rm -rf dist
    uv build
    uv publish   # 需要 UV_PUBLISH_TOKEN（或 keyring 里已有 PyPI 凭据）
fi

step "完成"
echo "   v$VERSION 已在本地提交并打 tag。"
[ "$PUSH" = 1 ] || echo "   还没推远端：git push origin main --tags"
[ "$PUBLISH" = 1 ] || echo "   还没发 PyPI：uv build && uv publish"
