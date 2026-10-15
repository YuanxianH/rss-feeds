import unittest
from pathlib import Path

import yaml

from src.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "worldlabs_blog_index.html"


def _worldlabs_job() -> dict:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    for job in config.get("jobs") or []:
        if job.get("output") == "worldlabs_blog.xml":
            return job
    raise AssertionError("World Labs Blog job missing from config.yaml")


class WorldLabsBlogFeedTests(unittest.TestCase):
    def test_fixture_extracts_posts_and_metadata(self):
        job = _worldlabs_job()
        self.assertEqual(job.get("name"), "World Labs Blog")
        self.assertEqual(job.get("title"), "World Labs Blog")
        self.assertEqual(job.get("output"), "worldlabs_blog.xml")
        parser = HTMLParser(
            FIXTURE.read_text(encoding="utf-8"),
            base_url="https://www.worldlabs.ai",
        )
        items = parser.parse_items(job["selectors"], max_items=50)

        self.assertEqual(
            [(item["title"], item["link"]) for item in items],
            [
                (
                    "World Labs is Joining AMD",
                    "https://www.worldlabs.ai/blog/amd-announcement",
                ),
                (
                    "To Seek a Newer World",
                    "https://drfeifei.substack.com/worldlabs-joining-amd",
                ),
                (
                    "Atlas: A World Model for Spatial Intelligence",
                    "https://www.worldlabs.ai/blog/atlas",
                ),
            ],
        )
        by_title = {item["title"]: item for item in items}
        self.assertEqual(
            by_title["World Labs is Joining AMD"]["pubDate"],
            "Mon, 28 Sep 2026 00:00:00 +0000",
        )
        self.assertEqual(
            by_title["To Seek a Newer World"]["pubDate"],
            "Mon, 28 Sep 2026 00:00:00 +0000",
        )
        self.assertEqual(
            by_title["Atlas: A World Model for Spatial Intelligence"]["pubDate"],
            "Tue, 01 Sep 2026 00:00:00 +0000",
        )
        self.assertEqual(by_title["World Labs is Joining AMD"]["author"], "World Labs team")
        self.assertEqual(by_title["To Seek a Newer World"]["author"], "Dr. Fei-Fei Li")
        self.assertEqual(
            by_title["Atlas: A World Model for Spatial Intelligence"]["author"],
            "World Labs team",
        )
        self.assertEqual(
            by_title["World Labs is Joining AMD"]["description"],
            "Accelerating the future of AI research and compute",
        )
        self.assertEqual(
            by_title["To Seek a Newer World"]["description"],
            "Our journey from World Labs to AMD",
        )
        self.assertEqual(
            by_title["Atlas: A World Model for Spatial Intelligence"]["description"],
            "Introducing Atlas, our new omni world model for spatial intelligence.",
        )


if __name__ == "__main__":
    unittest.main()
