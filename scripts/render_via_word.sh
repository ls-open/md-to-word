#!/usr/bin/env bash
# 脚本本体在包里（`src/md_to_word/resources/render_via_word.sh`）——pip 装的人也要能 `--pdf`，
# 所以它属于包内资源。这里只做转发，保证仓库里的旧用法照旧可用。
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$DIR/../src/md_to_word/resources/render_via_word.sh" "$@"
