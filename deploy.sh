#!/bin/bash
# 快速部署到 GitHub Pages

set -e

echo "🚀 RSS Creator - GitHub Pages 部署脚本"
echo "=========================================="
echo ""

# 检查是否已经是 Git 仓库
if [ ! -d .git ]; then
    echo "📦 初始化 Git 仓库..."
    git init
    echo "✅ Git 仓库已初始化"
    echo ""
fi

# 检查是否有远程仓库
if ! git remote get-url origin &> /dev/null; then
    echo "⚠️  尚未配置远程仓库"
    echo ""
    echo "请按照以下步骤操作："
    echo "1. 访问 https://github.com/new"
    echo "2. 创建新仓库（名称如：rss-feeds）"
    echo "3. 设置为 Public（公开）"
    echo "4. 复制仓库 URL"
    echo ""
    read -p "请输入你的 GitHub 仓库 URL: " REPO_URL

    git remote add origin "$REPO_URL"
    echo "✅ 远程仓库已配置: $REPO_URL"
    echo ""
fi

# 添加所有文件
echo "📝 添加文件到 Git..."
git add .

# 创建提交
echo "💾 创建提交..."
COMMIT_MSG="🤖 Update RSS feeds - $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$COMMIT_MSG" || echo "没有新的更改需要提交"

# 推送到 GitHub
echo "⬆️  推送到 GitHub..."
git branch -M main
git push -u origin main

echo ""
echo "✅ 部署成功！"
echo ""
echo "📋 后续步骤："
echo "1. 访问你的 GitHub 仓库"
echo "2. 点击 Settings → Pages"
echo "3. Source 选择: Deploy from a branch"
echo "4. Branch 选择: gh-pages / (root)"
echo "5. 点击 Save"
echo ""
echo "⏰ 等待 1-2 分钟后，访问："
echo "   https://YOUR_USERNAME.github.io/REPO_NAME/openai_research_only.xml"
echo "   https://YOUR_USERNAME.github.io/REPO_NAME/deepmind_blog.xml"
echo ""
echo "📚 详细说明请查看 DEPLOY.md"
