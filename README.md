# AI RSS Network

An English-first, deployed RSS network for AI labs, research groups, engineering blogs, and release streams.

Primary entrypoint: [yuanxianh.github.io/rss-feeds](https://yuanxianh.github.io/rss-feeds/)

## What This Is

This repository publishes a subscriber-facing RSS collection for AI research and product monitoring. Instead of browsing each source separately, you can start from one deployed homepage and subscribe to the feeds you want.

The network currently covers:

- Research publications and filtered research feeds
- Engineering and company blogs
- Release-oriented feeds for models and repositories

## Available Feeds

### Research

- [Waymo Research](https://yuanxianh.github.io/rss-feeds/waymo_research.xml)
- [Meta AI Research Publications](https://yuanxianh.github.io/rss-feeds/meta_ai_research.xml)
- [OpenAI Research](https://yuanxianh.github.io/rss-feeds/openai_research_only.xml)

### Blogs

- [Google DeepMind Blog](https://yuanxianh.github.io/rss-feeds/deepmind_blog.xml)
- [Waymo Blog - Technology](https://yuanxianh.github.io/rss-feeds/waymo_blog_tech.xml)
- [MiniMax News](https://yuanxianh.github.io/rss-feeds/minimax_blog.xml)
- [Kimi Research Articles & Technical Blogs](https://yuanxianh.github.io/rss-feeds/kimi_blog.xml)

### Releases

- MiniMax Releases, configured in the network and shown on the landing page when its XML feed is available

## Quick Paths

### Browse Online

- Landing page: [https://yuanxianh.github.io/rss-feeds/](https://yuanxianh.github.io/rss-feeds/)

### Subscribe Directly

- Copy any live XML URL above into your RSS reader.

### Run Locally

```bash
pip install -r requirements.txt
python main.py
cd feeds
python -m http.server 8000
```

Then open `http://localhost:8000/` for the generated landing page or subscribe to any local XML feed.

### Deploy

```bash
./scripts/ops/deploy.sh
```

That pushes the repository, triggers GitHub Actions, regenerates the feeds, and publishes `feeds/` to GitHub Pages.

## Docs

- User guide (Chinese): [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- Deployment guide (Chinese): [docs/DEPLOY.md](docs/DEPLOY.md)
- Maintainer guide (Chinese): [docs/MAINTAINER_GUIDE.md](docs/MAINTAINER_GUIDE.md)

## Repository Shape

```text
rss_creator/
├── docs/
├── scripts/
│   └── ops/
├── src/
│   ├── jobs/
│   └── site_index.py
├── tests/
├── config.yaml
├── main.py
└── feeds/
```
