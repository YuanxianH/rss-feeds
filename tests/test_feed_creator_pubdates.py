import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from src.feed_creator import FeedCreator

HTML = """
<ul>
  <li><a href="/bitter">The Bitter Lesson</a> 3/13/2019</li>
  <li><a href="/oak">Oak Lab</a></li>
</ul>
"""


class FeedCreatorPubDateTests(unittest.TestCase):
    def _config(self) -> dict:
        return {
            "name": "Incomplete Ideas",
            "url": "http://www.incompleteideas.net/",
            "output": "incompleteideas.xml",
            "title": "Rich Sutton - Incomplete Ideas",
            "description": "test",
            "link": "http://www.incompleteideas.net/",
            "selectors": {"items": "a[href]"},
            "options": {
                "infer_dates_from_context": True,
                "persist_pubdates": True,
                "max_items": 20,
            },
        }

    def _items(self, xml_path: Path) -> list[ET.Element]:
        return ET.parse(xml_path).getroot().findall("./channel/item")

    @patch("src.feed_creator.WebScraper")
    def test_uses_context_dates_and_persists_undated_items(self, scraper_cls):
        scraper_cls.return_value.fetch.return_value = HTML
        with tempfile.TemporaryDirectory() as temp_dir:
            creator = FeedCreator(feeds_dir=temp_dir)
            self.assertTrue(creator.create_feed(self._config()))
            first = {item.findtext("title"): item for item in self._items(Path(temp_dir) / "incompleteideas.xml")}
            self.assertIn("13 Mar 2019", first["The Bitter Lesson"].findtext("pubDate") or "")
            oak_first = first["Oak Lab"].findtext("pubDate")
            self.assertTrue(oak_first)

            previous = Path(temp_dir) / "incompleteideas.xml"
            previous.write_text(
                previous.read_text(encoding="utf-8").replace(
                    oak_first,
                    "Wed, 01 Jan 2020 00:00:00 +0000",
                ),
                encoding="utf-8",
            )
            self.assertTrue(creator.create_feed(self._config()))
            second = {item.findtext("title"): item for item in self._items(Path(temp_dir) / "incompleteideas.xml")}
            self.assertIn("13 Mar 2019", second["The Bitter Lesson"].findtext("pubDate") or "")
            self.assertEqual(second["Oak Lab"].findtext("pubDate"), "Wed, 01 Jan 2020 00:00:00 +0000")

    @patch("src.feed_creator.WebScraper")
    def test_writes_newest_items_first(self, scraper_cls):
        scraper_cls.return_value.fetch.return_value = """
        <ul>
          <li><a href="/old">Old</a> 11/12/01</li>
          <li><a href="/new">New</a> 3/13/2019</li>
        </ul>
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            creator = FeedCreator(feeds_dir=temp_dir)
            self.assertTrue(creator.create_feed(self._config()))
            titles = [
                item.findtext("title")
                for item in self._items(Path(temp_dir) / "incompleteideas.xml")
            ]
            self.assertEqual(titles, ["New", "Old"])


if __name__ == "__main__":
    unittest.main()
