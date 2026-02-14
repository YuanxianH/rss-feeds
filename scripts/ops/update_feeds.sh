#!/bin/bash
# 更新所有 RSS feeds

set -u -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "🔄 开始更新 RSS feeds..."
echo ""

failures=0

run_step() {
    local name="$1"
    shift
    echo "📡 更新 ${name}..."
    if "$@"; then
        echo "✅ ${name} 更新成功"
    else
        echo "❌ ${name} 更新失败"
        failures=$((failures + 1))
    fi
    echo ""
}

run_step "Google DeepMind / Meta / Waymo Research" env PYTHONPATH="$ROOT_DIR" python "$ROOT_DIR/main.py"
run_step "OpenAI Research" env PYTHONPATH="$ROOT_DIR" python "$ROOT_DIR/scripts/feed_jobs/filter_openai_research.py"
run_step "Waymo Blog Technology" env PYTHONPATH="$ROOT_DIR" python "$ROOT_DIR/scripts/feed_jobs/fetch_waymo_blog.py"
run_step \
  "MiniMax News" \
  env PYTHONPATH="$ROOT_DIR" python "$ROOT_DIR/scripts/feed_jobs/fetch_minimax_blog.py" \
  --max-items 200 \
  --max-discovery-pages 200 \
  --max-sitemaps 200

echo ""
echo "生成的 RSS 文件："

if ls "$ROOT_DIR/feeds/"*.xml >/dev/null 2>&1; then
    ls -lh "$ROOT_DIR/feeds/"*.xml
else
    echo "（当前没有生成任何 XML 文件）"
fi

if [ "$failures" -gt 0 ]; then
    echo ""
    echo "⚠️ 更新结束：${failures} 个任务失败"
    exit 1
fi

echo ""
echo "✅ 所有 feeds 更新完成！"
