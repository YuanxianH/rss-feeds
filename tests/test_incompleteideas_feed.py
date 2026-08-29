import unittest
from pathlib import Path

import yaml

from src.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "incompleteideas_index.html"


def _incompleteideas_job() -> dict:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    for job in config.get("jobs") or []:
        if job.get("name") == "Incomplete Ideas":
            return job
    raise AssertionError("Incomplete Ideas job missing from config.yaml")


class IncompleteIdeasFeedTests(unittest.TestCase):
    def test_fixture_extracts_navigable_homepage_links(self):
        job = _incompleteideas_job()
        parser = HTMLParser(
            FIXTURE.read_text(encoding="utf-8"),
            base_url="http://www.incompleteideas.net",
        )
        items = parser.parse_items(
            job["selectors"],
            max_items=int((job.get("options") or {}).get("max_items", 200)),
        )

        self.assertEqual(
            [(item["title"], item["link"]) for item in items],
            [
                ("Oak Lab", "https://oaklab.example"),
                ("http://richsutton.com", "http://richsutton.com"),
                ("X: @RichardSSutton", "https://x.com/RichardSSutton"),
                (
                    "The Alberta Plan for AI Research",
                    "http://www.incompleteideas.net/IncIdeas/AlbertaPlan.html",
                ),
                (
                    "The Bitter Lesson",
                    "http://www.incompleteideas.net/IncIdeas/BitterLesson.html",
                ),
            ],
        )
        self.assertTrue(all("mailto:" not in item["link"] for item in items))
        self.assertTrue(all("javascript:" not in item["link"] for item in items))


if __name__ == "__main__":
    unittest.main()
