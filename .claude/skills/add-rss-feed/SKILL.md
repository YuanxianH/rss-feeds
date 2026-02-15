---
name: add-rss-feed
description: >
  Add a new website as an RSS feed to the rss_creator project at /Users/yxhuang/repo/rss_creator.
  Use when the user provides a URL and wants to turn it into an RSS feed, or says things like
  "帮我把这个网页变成 RSS", "add RSS feed for this site", "订阅这个页面", "把这个网页加到 RSS".
  Handles: analyzing page HTML, configuring CSS selectors, testing feed generation, committing, and deploying to GitHub Pages.
---

# Add RSS Feed

## Job Types

The repo supports multiple job types:

| Type | Use Case |
|------|----------|
| `selector_scrape` | Most websites with server-rendered HTML |
| `kimi_blog` | VitePress based blogs |
| `minimax_news` | Complex sites requiring sitemap discovery |
| `waymo_blog_technology` | Waymo blog API |
| `openai_research_filter` | Filter existing RSS for specific categories |

For most new feeds, use `selector_scrape`.

## Workflow

### Step 1: Analyze the page

Run the analysis script to check if the page is server-rendered and find repeating elements:

```bash
python /Users/yxhuang/repo/rss_creator/.claude/skills/add-rss-feed/scripts/analyze_page.py <URL>
```

If 0 repeated content elements found, the page is likely JS-rendered — inform the user it may not work with simple HTTP scraping.

Also fetch the page with `WebFetch` or Python to inspect the first item's full HTML with `prettify()`.

### Step 2: Identify CSS selectors

From the HTML, determine selectors for:

| Field | Required | Notes |
|-------|----------|-------|
| `items` | Yes | Container for each entry (e.g., `article`, `div.post`) |
| `title` | Yes | Title text element (e.g., `h3 a`, `h2.title`) |
| `link` | Yes | Element with `href` (e.g., `h3 a`, `a.permalink`) |
| `description` | No | Summary text |
| `date` | No | Parser reads `datetime` attr first, then text content |
| `author` | No | Author name |

**Tips:**
- Prefer semantic tags (`article`, `h3 a`) over CSS module hashed classes (`_foo_abc123`) which break between builds
- Verify with `soup.select(selector)` that match count equals expected item count

### Step 3: Add config to config.yaml

Read `/Users/yxhuang/repo/rss_creator/config.yaml` and append:

```yaml
  - type: "selector_scrape"
    name: "Feed Name"
    url: "https://example.com/page"
    output: "feed_name.xml"
    title: "Feed Title"
    description: "Feed description"
    link: "https://example.com/page"
    selectors:
      items: "article"
      title: "h3 a"
      link: "h3 a"
    options:
      max_items: 50
      timeout: 15
      retries: 2
      backoff_factor: 0.5
      user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
      encoding: "utf-8"
```

### Step 4: Test locally

```bash
cd /Users/yxhuang/repo/rss_creator && python main.py -v
```

Verify: feed generates with expected item count, read the XML in `feeds/` to confirm content.

### Step 5: Update index.html

Add the new feed to `feeds/index.html` so it appears in the feed list:

```html
<li class="feed-item">
    <a href="feed_name.xml">Feed Title</a>
    <div class="description">Feed description</div>
</li>
```

### Step 6: Commit and push

1. Commit changes:
   ```bash
   git add config.yaml feeds/index.html
   git commit -m "feat: add <feed_name> RSS feed"
   ```

2. Push to trigger GitHub Actions:
   ```bash
   git push
   ```

GitHub Actions will automatically run and deploy the updated feeds to GitHub Pages.

**New feed URL:** `https://yuanxianh.github.io/rss_creator/<output_filename>`

You can manually trigger a deployment from the GitHub Actions tab if needed.
