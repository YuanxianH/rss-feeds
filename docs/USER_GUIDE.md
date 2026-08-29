# 用户指南

适用对象：只关心“怎么生成和订阅 RSS”的使用者。  
开发维护说明见 `docs/MAINTAINER_GUIDE.md`。

## 你可以做什么

- 从多个站点抓取内容并生成 RSS
- 一键更新全部 feeds
- 通过 GitHub Pages 对外发布订阅链接

## 安装

```bash
cd /path/to/rss-feeds
pip install -r requirements.txt
```

## 快速开始

### 1) 按配置生成全部 RSS 任务

```bash
python main.py
```

### 2) 全量更新（推荐）

```bash
python main.py -v
```

说明：

- 会执行 `main.py`，统一处理 `config.yaml` 的 `jobs[]`
- 任一任务失败时，脚本最终返回非零退出码
- 自动发布使用 `--allow-partial`，会更新成功的 Feed 并保留失败 Feed 的旧版本

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
- `feeds/minimax_official_blog.xml`
- `feeds/kimi_blog.xml`
- `feeds/zhipu_research.xml`
- `feeds/hunyuan_research.xml`

`feeds/index.html` 和 `feeds/assets/site.css` 也会自动生成，用于本地预览；
这些文件不需要手工编辑。

## 常用命令

```bash
# 运行测试
python -m unittest discover -s tests -p "test_*.py"

# 首次推送（origin 未配置）
./scripts/ops/deploy.sh --remote-url https://github.com/YOUR_USERNAME/rss-feeds.git

# 后续推送（触发 Actions 自动更新与发布）
./scripts/ops/deploy.sh

# 直接手动发布 feeds 到 gh-pages
./scripts/ops/publish.sh
```

## 配置 `config.yaml`

核心字段：

- `jobs[].type`: 任务类型（如 `selector_scrape` / `dynamic_site` / `openai_research_filter` / `waymo_blog_technology` / `minimax_news` / `zhipu_research` / `hunyuan_research`）
- `jobs[].name`: 任务名称（用于日志和结果统计）
- `jobs[].output`: 输出文件名（写入 `feeds/`）
- `jobs[].options.*`: 任务参数（如 `max_items` / `timeout` / `retries`）
- `defaults.options.*`: 所有任务共用的默认参数；单个任务可以覆盖

最小示例：

```yaml
jobs:
  - type: "selector_scrape"
    name: "Example"
    url: "https://example.com/news"
    output: "example.xml"
    selectors:
      items: "article.post"
      title: "h2.title"
      link: "a.permalink"
```

动态页面若在 HTML、Next.js 内嵌数据或 sitemap 中包含文章链接，可配置：

```yaml
jobs:
  - type: "dynamic_site"
    name: "Example Blog"
    url: "https://example.com/blog"
    path_prefix: "/blog"
    allowed_hosts: ["example.com"]
    output: "example_blog.xml"
```

## 部署到 GitHub Pages

详细步骤见 `docs/DEPLOY.md`。
