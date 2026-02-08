#!/bin/bash
# 更新所有 RSS feeds

echo "🔄 开始更新 RSS feeds..."
echo ""

# 更新 DeepMind Blog
echo "📡 更新 Google DeepMind Blog..."
python main.py

# 更新 OpenAI Research
echo ""
echo "📡 更新 OpenAI Research..."
python filter_openai_research.py

echo ""
echo "✅ 所有 feeds 更新完成！"
echo ""
echo "生成的 RSS 文件："
ls -lh feeds/*.xml
