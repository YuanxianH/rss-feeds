#!/bin/bash
# 推送到 GitHub

set -e

echo "🚀 准备推送到 GitHub..."
echo ""

# 添加远程仓库
echo "📡 添加远程仓库..."
git remote add origin https://github.com/YuanxianH/rss-feeds.git

echo "⬆️  推送代码到 GitHub..."
git push -u origin main

echo ""
echo "✅ 推送成功！"
echo ""
echo "📋 接下来的步骤："
echo "1. 访问: https://github.com/YuanxianH/rss-feeds"
echo "2. 点击 Settings → Pages"
echo "3. Source 选择: Deploy from a branch"
echo "4. Branch 选择: gh-pages / (root)"
echo "5. 点击 Save"
echo ""
echo "⏰ 等待 1-2 分钟，GitHub Actions 会自动运行"
echo "📡 然后你就可以订阅这些链接了："
echo ""
echo "   https://yuanxianh.github.io/rss-feeds/openai_research_only.xml"
echo "   https://yuanxianh.github.io/rss-feeds/deepmind_blog.xml"
