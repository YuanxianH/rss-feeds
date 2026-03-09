#!/bin/bash
# 手动发布脚本：使用临时 worktree 推送 feeds 到 gh-pages。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

REMOTE_NAME="origin"
PUBLISH_BRANCH="gh-pages"
SOURCE_DIR="feeds"
SKIP_GENERATE=0
ALLOW_DIRTY=0
COMMIT_MESSAGE=""
WORKTREE_DIR=""

usage() {
    cat <<'EOF'
用法:
  ./scripts/ops/publish.sh [选项]

选项:
  --remote <name>         远程名（默认: origin）
  --branch <name>         发布分支（默认: gh-pages）
  --source-dir <path>     待发布目录（默认: feeds）
  --skip-generate         跳过本地生成，直接发布现有文件
  --allow-dirty           允许工作区未提交变更
  --commit-message <msg>  自定义提交信息
  -h, --help              显示帮助
EOF
}

log() {
    echo "$*"
}

die() {
    echo "❌ $*" >&2
    exit 1
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "缺少命令: $1"
}

cleanup() {
    if [[ -n "$WORKTREE_DIR" ]]; then
        git worktree remove --force "$WORKTREE_DIR" >/dev/null 2>&1 || true
        rm -rf "$WORKTREE_DIR"
    fi
}

trap cleanup EXIT

while [[ $# -gt 0 ]]; do
    case "$1" in
        --remote)
            REMOTE_NAME="${2:-}"
            shift 2
            ;;
        --branch)
            PUBLISH_BRANCH="${2:-}"
            shift 2
            ;;
        --source-dir)
            SOURCE_DIR="${2:-}"
            shift 2
            ;;
        --skip-generate)
            SKIP_GENERATE=1
            shift
            ;;
        --allow-dirty)
            ALLOW_DIRTY=1
            shift
            ;;
        --commit-message)
            COMMIT_MESSAGE="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "未知参数: $1"
            ;;
    esac
done

require_cmd git
require_cmd python

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "当前目录不是 Git 仓库"
git remote get-url "$REMOTE_NAME" >/dev/null 2>&1 || die "远程不存在: $REMOTE_NAME"

if [[ "$ALLOW_DIRTY" -ne 1 ]]; then
    git diff --quiet || die "工作区存在未提交变更，请先提交或使用 --allow-dirty"
    git diff --cached --quiet || die "暂存区存在未提交变更，请先提交或使用 --allow-dirty"
fi

if [[ "$SKIP_GENERATE" -ne 1 ]]; then
    log "🔄 生成最新 RSS..."
    env PYTHONPATH="$ROOT_DIR" python "$ROOT_DIR/main.py"
fi

SOURCE_PATH="$ROOT_DIR/$SOURCE_DIR"
[[ -d "$SOURCE_PATH" ]] || die "目录不存在: $SOURCE_PATH"
if ! ls "$SOURCE_PATH"/*.xml >/dev/null 2>&1; then
    die "未找到可发布的 XML 文件，请先生成 feeds"
fi

log "📦 准备发布到 $REMOTE_NAME/$PUBLISH_BRANCH ..."
WORKTREE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/rss-pages.XXXXXX")"

if git ls-remote --exit-code --heads "$REMOTE_NAME" "$PUBLISH_BRANCH" >/dev/null 2>&1; then
    git fetch "$REMOTE_NAME" "$PUBLISH_BRANCH":"refs/remotes/$REMOTE_NAME/$PUBLISH_BRANCH"
    git worktree add -B "$PUBLISH_BRANCH" "$WORKTREE_DIR" "refs/remotes/$REMOTE_NAME/$PUBLISH_BRANCH"
else
    git worktree add --detach "$WORKTREE_DIR"
    git -C "$WORKTREE_DIR" checkout --orphan "$PUBLISH_BRANCH"
fi

find "$WORKTREE_DIR" -mindepth 1 -maxdepth 1 ! -name ".git" -exec rm -rf {} +
find "$SOURCE_PATH" -mindepth 1 -maxdepth 1 -type f ! -name ".gitkeep" -exec cp {} "$WORKTREE_DIR"/ \;
touch "$WORKTREE_DIR/.nojekyll"

git -C "$WORKTREE_DIR" add --all

if git -C "$WORKTREE_DIR" diff --cached --quiet; then
    log "ℹ️ 发布内容无变化，跳过提交"
    exit 0
fi

if [[ -z "$COMMIT_MESSAGE" ]]; then
    COMMIT_MESSAGE="chore: publish feeds $(date '+%Y-%m-%d %H:%M:%S')"
fi

git -C "$WORKTREE_DIR" commit -m "$COMMIT_MESSAGE"
git -C "$WORKTREE_DIR" push "$REMOTE_NAME" "$PUBLISH_BRANCH"

log "✅ 手动发布完成"
