#!/bin/bash
# 安全部署脚本：执行检查并推送当前分支，触发 GitHub Actions 发布。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

REMOTE_NAME="origin"
REMOTE_URL=""
TARGET_BRANCH=""
RUN_TESTS=1
AUTO_COMMIT=0
ALLOW_DIRTY=0
COMMIT_MESSAGE=""

usage() {
    cat <<'EOF'
用法:
  ./deploy.sh [选项]

选项:
  --remote-url <url>    当 origin 不存在时设置远程 URL
  --branch <name>       指定要推送的分支（默认: 当前分支）
  --no-tests            跳过单元测试
  --auto-commit         自动提交当前变更（git add --all）
  --commit-message <m>  自动提交时使用的提交信息
  --allow-dirty         允许工作区未提交变更也继续推送
  -h, --help            显示帮助
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

while [[ $# -gt 0 ]]; do
    case "$1" in
        --remote-url)
            REMOTE_URL="${2:-}"
            shift 2
            ;;
        --branch)
            TARGET_BRANCH="${2:-}"
            shift 2
            ;;
        --no-tests)
            RUN_TESTS=0
            shift
            ;;
        --auto-commit)
            AUTO_COMMIT=1
            shift
            ;;
        --commit-message)
            COMMIT_MESSAGE="${2:-}"
            shift 2
            ;;
        --allow-dirty)
            ALLOW_DIRTY=1
            shift
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

if [[ -z "$TARGET_BRANCH" ]]; then
    TARGET_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
fi

if [[ -z "$TARGET_BRANCH" || "$TARGET_BRANCH" == "HEAD" ]]; then
    die "无法识别当前分支，请使用 --branch 显式指定"
fi

if git remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    CURRENT_REMOTE_URL="$(git remote get-url "$REMOTE_NAME")"
else
    CURRENT_REMOTE_URL=""
fi

if [[ -z "$CURRENT_REMOTE_URL" ]]; then
    [[ -n "$REMOTE_URL" ]] || die "未配置 origin。请使用 --remote-url 设置远程仓库"
    git remote add "$REMOTE_NAME" "$REMOTE_URL"
    CURRENT_REMOTE_URL="$REMOTE_URL"
    log "✅ 已添加远程仓库: $REMOTE_NAME -> $CURRENT_REMOTE_URL"
elif [[ -n "$REMOTE_URL" && "$REMOTE_URL" != "$CURRENT_REMOTE_URL" ]]; then
    die "origin 已存在且与 --remote-url 不一致。当前: $CURRENT_REMOTE_URL"
fi

if [[ "$RUN_TESTS" -eq 1 ]]; then
    log "🧪 运行单元测试..."
    python -m unittest discover -s tests -p 'test_*.py'
fi

if [[ "$AUTO_COMMIT" -eq 1 ]]; then
    if [[ -z "$COMMIT_MESSAGE" ]]; then
        COMMIT_MESSAGE="chore: deploy $(date '+%Y-%m-%d %H:%M:%S')"
    fi

    log "📝 自动提交当前变更..."
    git add --all
    if git diff --cached --quiet; then
        log "ℹ️ 没有可提交的变更"
    else
        git commit -m "$COMMIT_MESSAGE"
    fi
fi

if [[ "$ALLOW_DIRTY" -ne 1 ]]; then
    git diff --quiet || die "工作区存在未提交变更，请先提交或使用 --allow-dirty"
    git diff --cached --quiet || die "暂存区存在未提交变更，请先提交或使用 --allow-dirty"
fi

UPSTREAM="$(git rev-parse --abbrev-ref "${TARGET_BRANCH}@{upstream}" 2>/dev/null || true)"
if [[ -z "$UPSTREAM" ]]; then
    log "⬆️ 首次推送并设置上游: $REMOTE_NAME/$TARGET_BRANCH"
    git push -u "$REMOTE_NAME" "$TARGET_BRANCH"
else
    log "⬆️ 推送分支: $TARGET_BRANCH -> $REMOTE_NAME/$TARGET_BRANCH"
    git push "$REMOTE_NAME" "$TARGET_BRANCH"
fi

log ""
log "✅ 推送完成，已触发 CI/CD。"
log "请在 GitHub Actions 查看执行状态。"
