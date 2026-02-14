import unittest

from src.parser import HTMLParser


class HTMLParserTests(unittest.TestCase):
    def test_parse_items_normalizes_and_deduplicates_links(self):
        html = """
        <main>
          <article>
            <h2>First</h2>
            <a href="/a">Read</a>
            <time datetime="2026-01-02T03:04:05Z"></time>
          </article>
          <article>
            <h2>Second</h2>
            <a href="../b">Read</a>
          </article>
          <article>
            <h2>Duplicate</h2>
            <a href="/a">Read</a>
          </article>
        </main>
        """
        parser = HTMLParser(html, base_url="https://example.com")
        items = parser.parse_items(
            selectors={
                "items": "article",
                "title": "h2",
                "link": "a",
                "date": "time",
            },
            max_items=10,
        )

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["link"], "https://example.com/a")
        self.assertEqual(items[1]["link"], "https://example.com/b")
        self.assertTrue(items[0]["pubDate"].endswith("+0000"))

    def test_parse_date_returns_none_when_invalid(self):
        parser = HTMLParser("<html></html>", base_url="https://example.com")
        self.assertIsNone(parser._parse_date("not a date"))

    def test_parse_items_requires_items_selector(self):
        parser = HTMLParser("<article><h2>Title</h2></article>", base_url="https://example.com")
        self.assertEqual(parser.parse_items(selectors={}), [])


if __name__ == "__main__":
    unittest.main()
