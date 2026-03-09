import tempfile
import unittest
from pathlib import Path

from src.site_index import generate_site_index


def _write_feed(
    path: Path,
    title: str,
    description: str,
    last_build: str | None = None,
) -> None:
    last_build_xml = (
        f"    <lastBuildDate>{last_build}</lastBuildDate>\n" if last_build else ""
    )
    path.write_text(
        f"""<?xml version='1.0' encoding='UTF-8'?>
<rss version="2.0">
  <channel>
    <title>{title}</title>
    <link>https://example.com/{path.stem}</link>
    <description>{description}</description>
{last_build_xml}  </channel>
</rss>
""",
        encoding="utf-8",
    )


class SiteIndexTests(unittest.TestCase):
    def test_generate_site_index_renders_sidebar_navigation_with_live_counts_and_sorting(self):
        config = {
            "site": {
                "title": "AI RSS Network",
                "url": "https://yuanxianh.github.io/rss-feeds/",
                "tagline": "A deployed RSS network for AI labs.",
                "description": "Curated AI feeds.",
            },
            "jobs": [
                {
                    "name": "Older Research",
                    "title": "Older Research",
                    "description": "Older research stream.",
                    "output": "older_research.xml",
                    "catalog": {"section": "research"},
                },
                {
                    "name": "Newest Research",
                    "title": "Newest Research",
                    "description": "Newest research stream.",
                    "output": "newest_research.xml",
                    "catalog": {"section": "research"},
                },
                {
                    "name": "Unavailable Research",
                    "title": "Unavailable Research",
                    "description": "Unavailable research stream.",
                    "output": "missing_research.xml",
                    "link": "https://example.com/missing",
                    "catalog": {"section": "research"},
                },
                {
                    "name": "DeepMind Blog",
                    "title": "DeepMind Blog",
                    "description": "Latest posts from DeepMind.",
                    "output": "deepmind_blog.xml",
                    "link": "https://deepmind.google/blog/",
                    "catalog": {"section": "blogs"},
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            feeds_dir = Path(temp_dir)
            _write_feed(
                feeds_dir / "older_research.xml",
                "Older Research",
                "Older research stream.",
                "Fri, 14 Feb 2026 06:27:21 +0000",
            )
            _write_feed(
                feeds_dir / "newest_research.xml",
                "Newest Research",
                "Newest research stream.",
                "Sun, 15 Feb 2026 06:27:21 +0000",
            )
            _write_feed(
                feeds_dir / "deepmind_blog.xml",
                "DeepMind Blog",
                "Latest posts from DeepMind.",
                "Sat, 15 Feb 2026 05:00:00 +0000",
            )

            output_path = generate_site_index(config, str(feeds_dir))
            html = output_path.read_text(encoding="utf-8")

        research_block = html.split('id="section-research"', 1)[1].split('id="section-blogs"', 1)[0]
        sidebar_block = html.split('<nav class="sidebar-body">', 1)[1].split("</nav>", 1)[0]

        self.assertIn('class="sidebar"', html)
        self.assertIn('class="sidebar-overlay"', html)
        self.assertNotIn('class="jump-menu"', html)
        self.assertIn('data-sidebar-toggle', html)
        self.assertIn('aria-controls="feed-sidebar"', html)
        self.assertIn("sidebar-open-mobile", html)
        self.assertIn("desktop-expanded", html)
        self.assertIn("mobile-open", html)
        self.assertIn("mobile-closed", html)
        self.assertIn("3 live feeds", html)
        self.assertIn("4 configured", html)
        self.assertIn('class="directory-toggle directory-toggle--sidebar"', html)
        self.assertIn('class="directory-toggle directory-toggle--hero"', html)
        self.assertIn('data-toggle-label', html)
        self.assertIn("Hide directory", html)
        self.assertIn("Show directory", html)
        self.assertIn("Open directory", html)
        self.assertIn("Close directory", html)
        self.assertNotIn('href="#section-research"', html)
        self.assertNotIn('href="#section-blogs"', html)
        self.assertNotIn('href="#section-releases"', html)
        self.assertIn('href="#feed-research-newest-research"', html)
        self.assertEqual(sidebar_block.count("<h2>Research</h2>"), 1)
        self.assertEqual(sidebar_block.count("<h2>Blogs</h2>"), 1)
        self.assertEqual(sidebar_block.count("<h2>Releases</h2>"), 1)
        self.assertIn("2 live", research_block)
        self.assertNotIn('<span class="meta-key">Source</span>', research_block)
        self.assertIn("Unavailable", research_block)
        self.assertIn("RSS unavailable", research_block)
        self.assertIn('href="newest_research.xml"', html)
        self.assertIn('href="https://example.com/newest_research"', html)
        self.assertIn('id="feed-research-newest-research"', html)
        self.assertLess(research_block.index("Newest Research"), research_block.index("Older Research"))
        self.assertLess(research_block.index("Older Research"), research_block.index("Unavailable Research"))
        self.assertIn("15 Feb 2026, 06:27 UTC", html)

    def test_generate_site_index_places_missing_timestamp_after_dated_live_feeds(self):
        config = {
            "jobs": [
                {
                    "name": "Dated Blog",
                    "title": "Dated Blog",
                    "description": "Has a build timestamp.",
                    "output": "dated_blog.xml",
                    "catalog": {"section": "blogs"},
                },
                {
                    "name": "Undated Blog",
                    "title": "Undated Blog",
                    "description": "Missing build timestamp.",
                    "output": "undated_blog.xml",
                    "catalog": {"section": "blogs"},
                },
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            feeds_dir = Path(temp_dir)
            _write_feed(
                feeds_dir / "dated_blog.xml",
                "Dated Blog",
                "Has a build timestamp.",
                "Sun, 15 Feb 2026 06:27:21 +0000",
            )
            _write_feed(
                feeds_dir / "undated_blog.xml",
                "Undated Blog",
                "Missing build timestamp.",
            )

            output_path = generate_site_index(config, str(feeds_dir))
            html = output_path.read_text(encoding="utf-8")

        blogs_block = html.split('id="section-blogs"', 1)[1].split('id="section-releases"', 1)[0]

        self.assertIn("2 live", blogs_block)
        self.assertIn("Unknown", blogs_block)
        self.assertLess(blogs_block.index("Dated Blog"), blogs_block.index("Undated Blog"))

    def test_generate_site_index_keeps_source_action_without_rendering_source_meta(self):
        config = {
            "jobs": [
                {
                    "name": "Linked Feed",
                    "title": "Linked Feed",
                    "description": "Has a source action.",
                    "output": "linked_feed.xml",
                    "catalog": {"section": "blogs"},
                },
                {
                    "name": "No Source Feed",
                    "title": "No Source Feed",
                    "description": "Missing upstream URL.",
                    "output": "missing_no_source.xml",
                    "catalog": {"section": "releases"},
                },
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            feeds_dir = Path(temp_dir)
            _write_feed(
                feeds_dir / "linked_feed.xml",
                "Linked Feed",
                "Has a source action.",
                "Sun, 15 Feb 2026 06:27:21 +0000",
            )

            output_path = generate_site_index(config, str(feeds_dir))
            html = output_path.read_text(encoding="utf-8")

        self.assertNotIn('<span class="meta-key">Source</span>', html)
        self.assertIn('href="https://example.com/linked_feed"', html)
        self.assertIn(">Source</a>", html)
        self.assertIn("Source unavailable", html)


if __name__ == "__main__":
    unittest.main()
