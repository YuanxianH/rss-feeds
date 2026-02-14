# 用户指南

适用对象：只关心“怎么生成和订阅 RSS”的使用者。  
开发维护说明见 `docs/MAINTAINER_GUIDE.md`。

## 你可以做什么

- 从多个站点抓取内容并生成 RSS
- 一键更新全部 feeds
- 通过 GitHub Pages 对外发布订阅链接

## 安装

```bash
cd /Users/yxhuang/repo/rss_creator
pip install -r requirements.txt
```

## 快速开始

### 1) 仅按配置生成抓取型 feeds

```bash
python main.py
```

### 2) 全量更新（推荐）

```bash
./update_feeds.sh
```

说明：

- 会执行 `main.py` 和额外任务（OpenAI/Waymo/MiniMax）
- 任一任务失败时，脚本最终返回非零退出码

### 3) 本地预览

```bash
cd feeds
python -m http.server 8000
```

示例订阅地址：

- `http://localhost:8000/openai_research_only.xml`

## 默认生成文件

- `feeds/deepmind_blog.xml`
- `feeds/waymo_research.xml`
- `feeds/meta_ai_research.xml`
- `feeds/openai_research_only.xml`
- `feeds/waymo_blog_tech.xml`
- `feeds/minimax_blog.xml`

## 常用命令

```bash
# 运行测试
python -m unittest discover -s tests -p "test_*.py"

# 首次推送（origin 未配置）
./deploy.sh --remote-url https://github.com/YOUR_USERNAME/rss-feeds.git

# 后续推送（触发 Actions 自动更新与发布）
./deploy.sh

# 直接手动发布 feeds 到 gh-pages
./publish.sh
```

## 配置 `config.yaml`

核心字段：

- `feeds[].url`: 目标网页
- `feeds[].selectors`: CSS 选择器
- `feeds[].options.max_items`: 最大条目数
- `feeds[].options.timeout`: 超时秒数
- `feeds[].options.retries`: 重试次数
- `feeds[].options.backoff_factor`: 重试退避系数

最小示例：

```yaml
feeds:
  - name: "Example"
    url: "https://example.com/news"
    output: "example.xml"
    selectors:
      items: "article.post"
      title: "h2.title"
      link: "a.permalink"
```

## 部署到 GitHub Pages

详细步骤见 `docs/DEPLOY.md`。
