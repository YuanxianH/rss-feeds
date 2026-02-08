# RSS Creator

一个简单但强大的 RSS 生成器，可以为任何网站生成 RSS feed。

## 功能特性

- 🌐 抓取任意网站内容
- 📝 智能解析 HTML 提取标题、链接、描述
- 📡 生成符合标准的 RSS 2.0 格式
- ⚙️ 灵活的 YAML 配置
- 🔄 支持定时自动更新
- 📂 多站点支持
- ☁️ 支持云端部署（GitHub Pages/Vercel/Netlify）
- 🤖 GitHub Actions 自动化更新

## 📊 当前支持的站点

- ✅ **Google DeepMind Blog** - AI 研究和突破
- ✅ **OpenAI Research** - 纯研究内容（已过滤新闻/政策）

## 安装

```bash
pip install -r requirements.txt
```

## 快速开始

1. 编辑 `config.yaml` 配置你想要订阅的网站
2. 运行生成器：

```bash
python main.py
```

3. 生成的 RSS 文件保存在 `feeds/` 目录
4. 使用你喜欢的 RSS 阅读器订阅这些文件

## 配置示例

```yaml
feeds:
  - name: "示例网站"
    url: "https://example.com/news"
    selectors:
      items: "article.post"
      title: "h2.title"
      link: "a.permalink"
      description: "p.summary"
      date: "time.published"
```

## 🌐 部署方式对比

### 方案 1: 本地使用（简单快速）

```bash
# 启动本地服务器
cd feeds
python -m http.server 8000
```

**订阅链接**：`http://localhost:8000/openai_research_only.xml`

⚠️ **限制**：
- 必须保持程序运行
- 只能在本机访问
- 关闭程序后 RSS 阅读器无法访问

---

### 方案 2: 云端部署（推荐⭐）

```bash
# 一键部署到 GitHub Pages
./deploy.sh
```

**订阅链接**：`https://YOUR_USERNAME.github.io/rss-feeds/openai_research_only.xml`

✅ **优势**：
- 24/7 在线，永不掉线
- 多设备访问（手机、电脑、平板）
- 自动更新（每天 2 次）
- 完全免费

📚 **详细部署教程**：查看 [DEPLOY.md](DEPLOY.md)

---

## 🔄 更新 RSS

### 本地更新
```bash
./update_feeds.sh
```

### 云端自动更新
部署到 GitHub Pages 后，无需手动操作，GitHub Actions 会自动更新：
- 每天北京时间 8:00 和 20:00
- 也可在 GitHub Actions 页面手动触发
