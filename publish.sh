#!/bin/bash
# 一键更新 RSS 并发布到 GitHub Pages

set -e

echo "🔄 [1/3] 生成最新 RSS feeds..."
echo ""

python main.py
python filter_openai_research.py

echo ""
echo "📦 [2/3] 发布到 GitHub Pages..."

# 保存生成的文件
cp feeds/deepmind_blog.xml /tmp/deepmind_blog.xml
cp feeds/openai_research_only.xml /tmp/openai_research_only.xml

# 切换到 gh-pages 分支
git checkout gh-pages

# 复制文件并提交
cp /tmp/deepmind_blog.xml .
cp /tmp/openai_research_only.xml .
git add deepmind_blog.xml openai_research_only.xml

if git diff --cached --quiet; then
    echo "📌 RSS 内容无变化，无需更新"
else
    git commit -m "🤖 Update RSS feeds - $(date '+%Y-%m-%d %H:%M')"
    git push origin gh-pages
    echo "✅ 已推送到 GitHub Pages"
fi

# 切回 main 分支
git checkout main

echo ""
echo "🎉 [3/3] 完成！"
echo ""
echo "📡 你的 RSS 订阅链接："
echo "   https://yuanxianh.github.io/rss-feeds/openai_research_only.xml"
echo "   https://yuanxianh.github.io/rss-feeds/deepmind_blog.xml"
