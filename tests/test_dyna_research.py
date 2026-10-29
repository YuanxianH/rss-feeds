import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import yaml

from src.jobs.base import JobContext
from src.jobs.selector_scrape import SelectorScrapeJob
from src.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "dyna_research_index.html"
DYNA_RESEARCH_URL = "https://www.dyna.co/research"


def _dyna_job() -> dict:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    for job in config.get("jobs") or []:
        if job.get("output") == "dyna_research.xml":
            return job
    raise AssertionError("DYNA Research job missing from config.yaml")


class DynaResearchFeedTests(unittest.TestCase):
    def test_config_targets_research_index(self):
        job = _dyna_job()
        self.assertEqual(job["type"], "selector_scrape")
        self.assertEqual(job["name"], "DYNA Research")
        self.assertEqual(job["url"], DYNA_RESEARCH_URL)
        self.assertEqual(job["link"], DYNA_RESEARCH_URL)
        self.assertEqual(job["output"], "dyna_research.xml")
        self.assertEqual(job["title"], "DYNA Research")
        self.assertEqual(job["catalog"]["section"], "research")
        self.assertIn("DYNA Robotics", job["description"])
        self.assertEqual(
            job["selectors"]["items"],
            "a.border-t[href]:has(p.font-saans):has(p.font-mono)",
        )
        self.assertEqual(job["selectors"]["title"], "p.font-saans")
        self.assertEqual(job["selectors"]["date"], "p.font-mono")
        self.assertNotIn("link", job["selectors"])

    def test_fixture_normalizes_urls_and_skips_bad_cards(self):
        job = _dyna_job()
        parser = HTMLParser(
            FIXTURE.read_text(encoding="utf-8"),
            base_url="https://www.dyna.co",
        )
        items = parser.parse_items(job["selectors"], max_items=50)

        self.assertEqual(
            [(item["title"], item["link"]) for item in items],
            [
                (
                    "Dyna-2.1: A Physical Agent for End-to-End Workflows",
                    "https://www.dyna.co/dyna-2.1",
                ),
                (
                    "Training Dyna-2 at million-hour scale, repeatably",
                    "https://www.dyna.co/research/dyna-2-infrastructure",
                ),
                (
                    "Dynamism v1 (Dyna-1) Model: A Breakthrough in Performance and Production-Ready Embodied AI",
                    "https://www.dyna.co/research/dyna-1",
                ),
                (
                    "Dyna-1 Pre-Training: Zero-Shot Dexterity Is Here",
                    "https://www.dyna.co/research/pre-training?from=index",
                ),
            ],
        )
        by_link = {item["link"]: item for item in items}
        self.assertEqual(
            by_link["https://www.dyna.co/dyna-2.1"]["pubDate"],
            "Mon, 28 Sep 2026 00:00:00 +0000",
        )
        self.assertEqual(
            by_link["https://www.dyna.co/research/dyna-2-infrastructure"]["pubDate"],
            "Mon, 17 Aug 2026 00:00:00 +0000",
        )
        self.assertEqual(
            by_link["https://www.dyna.co/research/dyna-1"]["pubDate"],
            "Tue, 24 Jun 2025 00:00:00 +0000",
        )
        self.assertIsNone(
            by_link["https://www.dyna.co/research/pre-training?from=index"]["pubDate"]
        )
        self.assertNotIn("https://www.dyna.co/company", by_link)
        self.assertTrue(all(item["title"] != "Missing link" for item in items))

    def test_empty_index_returns_no_items(self):
        parser = HTMLParser(
            "<html><body><a href='/company'>Company</a></body></html>",
            base_url=DYNA_RESEARCH_URL,
        )
        self.assertEqual(
            parser.parse_items(_dyna_job()["selectors"], max_items=50),
            [],
        )

    @patch("src.feed_creator.WebScraper.fetch")
    def test_job_writes_rss_when_one_card_fails(self, fetch):
        fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        job = _dyna_job()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = SelectorScrapeJob(job).run(JobContext(feeds_dir=Path(temp_dir)))
            output = Path(temp_dir) / "dyna_research.xml"
            root = ET.parse(output).getroot()

        self.assertTrue(result.success)
        channel = root.find("channel")
        self.assertEqual(channel.findtext("title"), "DYNA Research")
        self.assertEqual(channel.findtext("link"), DYNA_RESEARCH_URL)
        items = root.findall("./channel/item")
        self.assertEqual(
            [(item.findtext("title"), item.findtext("link")) for item in items],
            [
                (
                    "Dyna-2.1: A Physical Agent for End-to-End Workflows",
                    "https://www.dyna.co/dyna-2.1",
                ),
                (
                    "Training Dyna-2 at million-hour scale, repeatably",
                    "https://www.dyna.co/research/dyna-2-infrastructure",
                ),
                (
                    "Dynamism v1 (Dyna-1) Model: A Breakthrough in Performance and Production-Ready Embodied AI",
                    "https://www.dyna.co/research/dyna-1",
                ),
                (
                    "Dyna-1 Pre-Training: Zero-Shot Dexterity Is Here",
                    "https://www.dyna.co/research/pre-training?from=index",
                ),
            ],
        )
        self.assertTrue(
            (items[0].findtext("pubDate") or "").startswith("Mon, 28 Sep 2026")
        )
        self.assertIsNone(items[-1].findtext("pubDate"))


if __name__ == "__main__":
    unittest.main()
