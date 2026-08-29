---
name: add-rss-feed
description: >
  Add a website as an RSS feed to this repository. Use when the user provides a
  URL and asks to subscribe to it or turn it into RSS.
---

# Add RSS Feed

Run commands from the repository root. Feed XML, `feeds/index.html`, and
`feeds/assets/` are generated output; never edit or commit them.

## Choose a job type

| Type | Use case |
|---|---|
| `selector_scrape` | Server-rendered lists with stable CSS selectors |
| `dynamic_site` | Blog links present in HTML, embedded JSON/Next.js data, or sitemaps |
| `minimax_news` | MiniMax News discovery and crawl |
| `minimax_releases` | HuggingFace models and GitHub repositories |
| `waymo_blog_technology` | Waymo blog API |
| `zhipu_research` | Zhipu research articles API |
| `hunyuan_research` | Tencent Hunyuan research list API |
| `openai_research_filter` | Filter an existing RSS feed by category |
| `codex_changelog` | Codex changelog release entries |

Prefer `selector_scrape` for regular HTML. Use `dynamic_site` when article links
exist outside repeated cards or inside embedded data. Add a site-specific job
only when the source requires a dedicated API or data model. Do not add a
headless browser to the hourly workflow.

## Workflow

### 1. Analyze the page

```bash
python .claude/skills/add-rss-feed/scripts/analyze_page.py <URL>
```

Inspect visible anchors, `__NEXT_DATA__`, Next.js flight data, JSON-LD, and
sitemaps. Prefer semantic selectors over generated class names.

### 2. Add config

For server-rendered pages:

```yaml
- type: "selector_scrape"
  name: "Feed Name"
  url: "https://example.com/news"
  output: "feed_name.xml"
  title: "Feed Title"
  description: "Feed description"
  link: "https://example.com/news"
  selectors:
    items: "article"
    title: "h2"
    link: "a"
  catalog:
    section: "blogs"
```

For dynamic indexes:

```yaml
- type: "dynamic_site"
  name: "Feed Name"
  url: "https://example.com/blog"
  path_prefix: "/blog"
  allowed_hosts: ["example.com"]
  sitemap_urls:
    - "https://example.com/sitemap.xml"
  output: "feed_name.xml"
  title: "Feed Title"
  description: "Feed description"
  link: "https://example.com/blog"
  catalog:
    section: "blogs"
  options:
    minimum_items: 1
```

Common timeout, retry, user-agent, encoding, and item limits come from
`defaults.options` in `config.yaml`; only add per-job overrides when needed.

### 3. Add regression coverage

Save a minimal upstream HTML sample under `tests/fixtures/`. Test URL
normalization, discovery, metadata extraction, empty results, and partial
article failures without live network access.

### 4. Verify

```bash
python -m unittest discover -s tests -p "test_*.py"
python main.py -v
```

Validate the generated XML item count, titles, links, and dates. The generated
directory includes the feed automatically from `config.yaml`.

### 5. Publish

Commit source/config/tests only, then push. GitHub Actions restores previous
feeds, updates healthy jobs, retains failed jobs' prior XML, generates the
directory, and publishes `feeds/` to `gh-pages`.

Feed URL: `https://yuanxianh.github.io/rss-feeds/<output_filename>`
