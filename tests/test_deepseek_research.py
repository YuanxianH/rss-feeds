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
FIXTURE = Path(__file__).parent / "fixtures" / "deepseek_news_index.html"
DEEPSEEK_NEWS_URL = "https://www.deepseek.com/news/"


def _deepseek_job() -> dict:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    for job in config.get("jobs") or []:
        if job.get("name") == "DeepSeek Research Index":
            return job
    raise AssertionError("DeepSeek Research Index job missing from config.yaml")


class DeepSeekResearchFeedTests(unittest.TestCase):
    def test_config_targets_research_index_cards(self):
        job = _deepseek_job()
        self.assertEqual(job["type"], "selector_scrape")
        self.assertEqual(job["url"], DEEPSEEK_NEWS_URL)
        self.assertEqual(job["output"], "deepseek_research.xml")
        self.assertEqual(job["catalog"]["section"], "research")
        self.assertEqual(job["selectors"]["items"], "a.ds-research-item")
        self.assertEqual(job["selectors"]["title"], "span.ds-research-title")
        self.assertEqual(job["selectors"]["date"], "span.ds-research-date")
        self.assertNotIn("link", job["selectors"])

    def test_fixture_extracts_research_items_and_skips_news(self):
        job = _deepseek_job()
        parser = HTMLParser(
            FIXTURE.read_text(encoding="utf-8"),
            base_url="https://www.deepseek.com",
        )
        items = parser.parse_items(job["selectors"], max_items=20)

        self.assertEqual(
            [(item["title"], item["link"]) for item in items],
            [
                (
                    "DeepSeek-V4: Towards Highly Efficient Million-Token Context Intelligence",
                    "https://arxiv.org/abs/2606.19348",
                ),
                (
                    "DualPath: Breaking the Storage Bandwidth Bottleneck in Agentic LLM Inference",
                    "https://www.deepseek.com/abs/2602.21548",
                ),
                (
                    "Linear-Programming-Based Load Balancer (LPLB)",
                    "https://github.com/deepseek-ai/LPLB",
                ),
            ],
        )
        self.assertTrue(all("/news/" not in item["link"] for item in items))
        self.assertTrue(items[0]["pubDate"].startswith("Wed, 24 Jun 2026"))
        self.assertTrue(items[1]["pubDate"].startswith("Wed, 25 Feb 2026"))
        self.assertTrue(items[2]["pubDate"].startswith("Sat, 01 Nov 2025"))

    def test_empty_index_returns_no_items(self):
        parser = HTMLParser("<html><body>No papers</body></html>", base_url=DEEPSEEK_NEWS_URL)
        self.assertEqual(
            parser.parse_items(_deepseek_job()["selectors"], max_items=20),
            [],
        )

    @patch("src.feed_creator.WebScraper.fetch")
    def test_job_writes_rss_when_news_and_partial_cards_are_present(self, fetch):
        fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        job = _deepseek_job()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = SelectorScrapeJob(job).run(JobContext(feeds_dir=Path(temp_dir)))
            output = Path(temp_dir) / "deepseek_research.xml"
            root = ET.parse(output).getroot()

        self.assertTrue(result.success)
        items = root.findall("./channel/item")
        self.assertEqual(
            [(item.findtext("title"), item.findtext("link")) for item in items],
            [
                (
                    "DeepSeek-V4: Towards Highly Efficient Million-Token Context Intelligence",
                    "https://arxiv.org/abs/2606.19348",
                ),
                (
                    "DualPath: Breaking the Storage Bandwidth Bottleneck in Agentic LLM Inference",
                    "https://www.deepseek.com/abs/2602.21548",
                ),
                (
                    "Linear-Programming-Based Load Balancer (LPLB)",
                    "https://github.com/deepseek-ai/LPLB",
                ),
            ],
        )
        self.assertTrue((items[0].findtext("pubDate") or "").startswith("Wed, 24 Jun 2026"))
        self.assertTrue((items[1].findtext("pubDate") or "").startswith("Wed, 25 Feb 2026"))
        self.assertTrue((items[2].findtext("pubDate") or "").startswith("Sat, 01 Nov 2025"))
        self.assertTrue(
            all("/news/" not in (item.findtext("link") or "") for item in items)
        )


if __name__ == "__main__":
    unittest.main()
