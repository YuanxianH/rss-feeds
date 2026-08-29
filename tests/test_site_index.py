import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
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
    def test_generates_simple_static_directory_and_stylesheet(self):
        now = datetime.now(timezone.utc)
        config = {
            "site": {
                "title": "AI RSS Network",
                "url": "https://example.com/feeds/",
                "tagline": "A small feed directory.",
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
                format_datetime(now - timedelta(hours=2)),
            )
            _write_feed(
                feeds_dir / "newest_research.xml",
                "Newest Research",
                "Newest research stream.",
                format_datetime(now - timedelta(hours=1)),
            )
            _write_feed(
                feeds_dir / "deepmind_blog.xml",
                "DeepMind Blog",
                "Latest posts from DeepMind.",
                format_datetime(now),
            )

            output_path = generate_site_index(config, str(feeds_dir))
            html = output_path.read_text(encoding="utf-8")
            stylesheet = feeds_dir / "assets" / "site.css"
            stylesheet_exists = stylesheet.exists()

        research = html.split('id="section-research"', 1)[1].split(
            'id="section-blogs"', 1
        )[0]
        self.assertTrue(stylesheet_exists)
        self.assertIn('href="assets/site.css"', html)
        self.assertIn('class="skip-link" href="#main-content"', html)
        self.assertIn('aria-label="Feed categories"', html)
        self.assertIn('href="#section-research">Research<span>3</span>', html)
        self.assertNotIn("<script", html)
        self.assertNotIn("sidebar", html)
        self.assertNotIn("hero", html)
        self.assertIn("Live", research)
        self.assertIn("Unavailable", research)
        self.assertIn("RSS unavailable", research)
        self.assertIn('href="newest_research.xml"', html)
        self.assertIn('rel="noopener"', html)
        self.assertIn("<time datetime=", html)
        self.assertLess(
            research.index("Newest Research"),
            research.index("Older Research"),
        )
        self.assertLess(
            research.index("Older Research"),
            research.index("Unavailable Research"),
        )

    def test_marks_old_restored_feed_as_stale(self):
        config = {
            "jobs": [
                {
                    "name": "Current Blog",
                    "output": "current.xml",
                    "catalog": {"section": "blogs"},
                },
                {
                    "name": "Restored Blog",
                    "output": "restored.xml",
                    "catalog": {"section": "blogs"},
                },
            ]
        }
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            feeds_dir = Path(temp_dir)
            _write_feed(
                feeds_dir / "current.xml",
                "Current Blog",
                "Current.",
                format_datetime(now),
            )
            _write_feed(
                feeds_dir / "restored.xml",
                "Restored Blog",
                "Old but retained.",
                format_datetime(now - timedelta(days=4)),
            )

            html = generate_site_index(config, str(feeds_dir)).read_text(
                encoding="utf-8"
            )

        restored = html.split('id="feed-blogs-restored"', 1)[1].split(
            "</article>", 1
        )[0]
        self.assertIn("is-stale", html)
        self.assertIn("Stale", restored)
        self.assertIn('href="restored.xml"', restored)
        self.assertLess(html.index("Current Blog"), html.index("Restored Blog"))

    def test_escapes_configured_content_and_keeps_missing_source_disabled(self):
        config = {
            "site": {
                "title": "Feeds <script>",
                "description": 'Quotes " and <tags>',
            },
            "jobs": [
                {
                    "name": "Unsafe <Feed>",
                    "description": "<b>not markup</b>",
                    "output": "missing.xml",
                    "catalog": {"section": "releases"},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            html = generate_site_index(config, temp_dir).read_text(encoding="utf-8")

        self.assertIn("Feeds &lt;script&gt;", html)
        self.assertIn("&lt;b&gt;not markup&lt;/b&gt;", html)
        self.assertNotIn("<b>not markup</b>", html)
        self.assertIn("Source unavailable", html)


if __name__ == "__main__":
    unittest.main()
