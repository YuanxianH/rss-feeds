# 🚀 部署到 GitHub Pages

将你的 RSS feeds 部署到云端，实现 24/7 在线访问和自动更新。

## 📋 前置要求

- GitHub 账号
- Git 已安装

## 🎯 部署步骤

### 1. 初始化 Git 仓库（如果还没有）

```bash
cd /Users/yxhuang/repo/rss_creator

# 初始化 Git
git init

# 添加所有文件
git add .

# 创建首次提交
git commit -m "Initial commit: RSS Creator"
```

### 2. 在 GitHub 创建仓库

1. 访问 https://github.com/new
2. 仓库名称：`rss-feeds`（或任意名称）
3. 设置为 **Public**（必须，GitHub Pages 免费版需要公开仓库）
4. **不要**勾选 "Add a README file"
5. 点击 "Create repository"

### 3. 推送到 GitHub

```bash
# 添加远程仓库（替换 YOUR_USERNAME）
git remote add origin https://github.com/YOUR_USERNAME/rss-feeds.git

# 推送代码
git branch -M main
git push -u origin main
```

### 4. 启用 GitHub Pages

1. 在 GitHub 仓库页面，点击 **Settings**
2. 左侧菜单找到 **Pages**
3. **Source** 选择：`Deploy from a branch`
4. **Branch** 选择：`gh-pages` / `/ (root)`
5. 点击 **Save**

### 5. 等待自动部署

- GitHub Actions 会自动运行（约 1-2 分钟）
- 访问 **Actions** 标签页查看进度
- 部署成功后，你的 RSS feeds 将在线可用！

## 📡 订阅链接

部署成功后，你的 RSS feeds 将托管在：

```
https://YOUR_USERNAME.github.io/rss-feeds/openai_research_only.xml
https://YOUR_USERNAME.github.io/rss-feeds/deepmind_blog.xml
```

**替换 `YOUR_USERNAME` 和 `rss-feeds` 为你的实际 GitHub 用户名和仓库名。**

## ⏰ 自动更新

RSS feeds 将自动更新：
- **每天 2 次**：北京时间 8:00 和 20:00
- **手动触发**：在 Actions 标签页点击 "Run workflow"

## 🔧 修改更新频率

编辑 `.github/workflows/update-rss.yml`：

```yaml
schedule:
  # 每 6 小时更新一次
  - cron: '0 */6 * * *'

  # 或者每小时更新
  - cron: '0 * * * *'
```

## 🌐 自定义域名（可选）

如果你有自己的域名：

1. 在 `feeds/` 目录创建 `CNAME` 文件
2. 写入你的域名（如 `rss.yourdomain.com`）
3. 在域名服务商添加 CNAME 记录指向 `YOUR_USERNAME.github.io`

## 🆘 常见问题

### Q: Actions 运行失败？
A: 检查 Settings → Actions → General，确保 "Workflow permissions" 设置为 "Read and write permissions"

### Q: 页面 404？
A: 等待 5-10 分钟，GitHub Pages 部署需要时间

### Q: 想使用私有仓库？
A: 升级到 GitHub Pro（付费），或使用其他托管方案（见下文）

---

## 🔄 其他托管方案

### 方案 2: Vercel（免费，支持私有仓库）

1. 访问 https://vercel.com
2. 用 GitHub 账号登录
3. Import 你的仓库
4. 部署完成

### 方案 3: Netlify（免费）

1. 访问 https://netlify.com
2. 用 GitHub 账号登录
3. "New site from Git"
4. 选择你的仓库
5. Build settings:
   - Build command: `pip install -r requirements.txt && python main.py && python filter_openai_research.py`
   - Publish directory: `feeds`

### 方案 4: Cloudflare Pages（免费）

1. 访问 https://pages.cloudflare.com
2. 连接 GitHub
3. 选择仓库
4. 配置构建

---

## 📝 总结

- ✅ **推荐**: GitHub Pages（免费、简单）
- ✅ **备选**: Vercel/Netlify（功能更强大）
- ✅ **高级**: 自己的服务器/NAS

选择最适合你的方案！🎉
