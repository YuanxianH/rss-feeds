#!/bin/bash
# 根目录兼容入口，转发到 scripts/ops/deploy.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT_DIR/scripts/ops/deploy.sh" "$@"
