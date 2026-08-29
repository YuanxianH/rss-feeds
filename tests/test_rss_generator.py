import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from src.rss_generator import RSSGenerator, items_oldest_first


class RSSGeneratorTests(unittest.TestCase):
    def test_add_items_uses_stable_guid_and_deduplicates(self):
        generator = RSSGenerator(
            title="Test Feed",
            link="https://example.com",
            description="Test Description",
        )
        generator.add_items(
            [
                {
                    "title": "Item A",
                    "link": "https://example.com/a",
                    "pubDate": "not-a-date",
                },
                {
                    "title": "Item A duplicate",
                    "link": "https://example.com/a",
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "feed.xml"
            self.assertTrue(generator.generate(str(output_path)))

            tree = ET.parse(output_path)
            root = tree.getroot()
            channel_items = root.findall("./channel/item")

            self.assertEqual(len(channel_items), 1)
            self.assertEqual(channel_items[0].findtext("guid"), "https://example.com/a")
            self.assertIsNone(channel_items[0].find("pubDate"))

    def test_items_oldest_first_orders_by_pubdate(self):
        ordered = items_oldest_first(
            [
                {
                    "title": "New",
                    "link": "https://example.com/new",
                    "pubDate": "Wed, 24 Jun 2026 00:00:00 +0000",
                },
                {
                    "title": "Old",
                    "link": "https://example.com/old",
                    "pubDate": "Sat, 01 Nov 2025 00:00:00 +0000",
                },
                {
                    "title": "Undated",
                    "link": "https://example.com/none",
                },
            ]
        )

        self.assertEqual(
            [item["title"] for item in ordered],
            ["Undated", "Old", "New"],
        )

    def test_add_items_emits_newest_first_after_oldest_first_input(self):
        generator = RSSGenerator(
            title="Test Feed",
            link="https://example.com",
            description="Test Description",
        )
        generator.add_items(
            items_oldest_first(
                [
                    {
                        "title": "New",
                        "link": "https://example.com/new",
                        "pubDate": "Wed, 24 Jun 2026 00:00:00 +0000",
                    },
                    {
                        "title": "Old",
                        "link": "https://example.com/old",
                        "pubDate": "Sat, 01 Nov 2025 00:00:00 +0000",
                    },
                ]
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "feed.xml"
            self.assertTrue(generator.generate(str(output_path)))
            titles = [
                item.findtext("title")
                for item in ET.parse(output_path).getroot().findall("./channel/item")
            ]

        self.assertEqual(titles, ["New", "Old"])


if __name__ == "__main__":
    unittest.main()
