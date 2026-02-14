import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.jobs.base import JobContext
from src.jobs.selector_scrape import SelectorScrapeJob


class SelectorScrapeJobTests(unittest.TestCase):
    @patch("src.jobs.selector_scrape.FeedCreator")
    def test_selector_scrape_job_delegates_to_feed_creator(self, creator_cls):
        creator_cls.return_value.create_feed.return_value = True
        config = {
            "type": "selector_scrape",
            "name": "Demo",
            "url": "https://example.com",
            "selectors": {"items": "article", "title": "h2", "link": "a"},
            "output": "demo.xml",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            result = SelectorScrapeJob(config).run(JobContext(feeds_dir=Path(temp_dir)))

        creator_cls.assert_called_once()
        creator_cls.return_value.create_feed.assert_called_once_with(config)
        self.assertTrue(result.success)
        self.assertEqual(result.name, "Demo")


if __name__ == "__main__":
    unittest.main()
