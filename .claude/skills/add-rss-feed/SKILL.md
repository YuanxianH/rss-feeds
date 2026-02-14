---
name: add-rss-feed
description: >
  Add a new website as an RSS feed to the rss_creator project at /Users/yxhuang/repo/rss_creator.
  Use when the user provides a URL and wants to turn it into an RSS feed, or says things like
  "帮我把这个网页变成 RSS", "add RSS feed for this site", "订阅这个页面", "把这个网页加到 RSS".
  Handles: analyzing page HTML, configuring CSS selectors, testing feed generation, committing, and deploying to GitHub Pages.
---

# Add RSS Feed

## Workflow

### Step 1: Analyze the page

Run the analysis script to check if the page is server-rendered and find repeating elements:

```bash
python /Users/yxhuang/.claude/skills/add-rss-feed/scripts/analyze_page.py <URL>
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
  - name: "Feed Name"
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
      user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
      encoding: "utf-8"
```

### Step 4: Test locally

```bash
cd /Users/yxhuang/repo/rss_creator && python main.py -v
```

Verify: feed generates with expected item count, read the XML in `feeds/` to confirm content.

### Step 5: Commit and push

Commit `config.yaml`, then `git push`. GitHub Actions auto-deploys to GitHub Pages.

New feed URL: `https://yuanxianh.github.io/rss-feeds/<output_filename>`
