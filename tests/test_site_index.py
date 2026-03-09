import tempfile
import unittest
from pathlib import Path

from src.site_index import generate_site_index


def _write_feed(path: Path, title: str, description: str, last_build: str) -> None:
    path.write_text(
        f"""<?xml version='1.0' encoding='UTF-8'?>
<rss version="2.0">
  <channel>
    <title>{title}</title>
    <link>https://example.com/{path.stem}</link>
    <description>{description}</description>
    <lastBuildDate>{last_build}</lastBuildDate>
  </channel>
</rss>
""",
        encoding="utf-8",
    )


class SiteIndexTests(unittest.TestCase):
    def test_generate_site_index_groups_feeds_and_uses_relative_rss_links(self):
        config = {
            "site": {
                "title": "AI RSS Network",
                "url": "https://yuanxianh.github.io/rss-feeds/",
                "tagline": "A deployed RSS network for AI labs.",
                "description": "Curated AI feeds.",
            },
            "jobs": [
                {
                    "name": "OpenAI Research",
                    "title": "OpenAI Research",
                    "description": "Filtered research posts from OpenAI.",
                    "output": "openai_research_only.xml",
                    "catalog": {"section": "research"},
                },
                {
                    "name": "Google DeepMind Blog",
                    "title": "Google DeepMind Blog",
                    "description": "Latest posts from Google DeepMind.",
                    "output": "deepmind_blog.xml",
                    "link": "https://deepmind.google/blog/",
                    "catalog": {"section": "blogs"},
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            feeds_dir = Path(temp_dir)
            _write_feed(
                feeds_dir / "openai_research_only.xml",
                "OpenAI Research",
                "Filtered research posts from OpenAI.",
                "Sun, 15 Feb 2026 06:27:21 +0000",
            )
            _write_feed(
                feeds_dir / "deepmind_blog.xml",
                "Google DeepMind Blog",
                "Latest posts from Google DeepMind.",
                "Sun, 15 Feb 2026 06:26:48 +0000",
            )

            output_path = generate_site_index(config, str(feeds_dir))
            html = output_path.read_text(encoding="utf-8")

        research_block = html.split('id="section-research"', 1)[1].split('id="section-blogs"', 1)[0]
        blogs_block = html.split('id="section-blogs"', 1)[1].split('id="section-releases"', 1)[0]

        self.assertIn("OpenAI Research", research_block)
        self.assertNotIn("Google DeepMind Blog", research_block)
        self.assertIn("Google DeepMind Blog", blogs_block)
        self.assertIn('href="openai_research_only.xml"', html)
        self.assertIn('href="deepmind_blog.xml"', html)
        self.assertIn('href="https://example.com/openai_research_only"', html)
        self.assertIn("15 Feb 2026, 06:27 UTC", html)

    def test_generate_site_index_handles_missing_feed_xml(self):
        config = {
            "jobs": [
                {
                    "name": "MiniMax Releases",
                    "title": "MiniMax Releases",
                    "description": "MiniMax model releases.",
                    "output": "minimax_releases.xml",
                    "link": "https://huggingface.co/MiniMaxAI",
                    "catalog": {"section": "releases"},
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = generate_site_index(config, temp_dir)
            html = output_path.read_text(encoding="utf-8")

        self.assertIn("MiniMax Releases", html)
        self.assertIn("Feed file unavailable", html)
        self.assertIn("Awaiting first build", html)


if __name__ == "__main__":
    unittest.main()
