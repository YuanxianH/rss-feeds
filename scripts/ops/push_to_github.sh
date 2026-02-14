#!/bin/bash
# 兼容旧入口：转发到 deploy.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "ℹ️ push_to_github.sh 已合并到 deploy.sh，正在转发..."
exec "$ROOT_DIR/scripts/ops/deploy.sh" "$@"
