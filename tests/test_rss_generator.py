import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from src.rss_generator import RSSGenerator


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


if __name__ == "__main__":
    unittest.main()
