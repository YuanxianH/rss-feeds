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

    def test_parse_items_uses_anchor_text_when_container_is_link(self):
        html = """
        <main>
          <p>Work at <a href="https://oaklab.example">Oak Lab</a>.</p>
          <ul>
            <li><a href="IncIdeas/BitterLesson.html">The Bitter Lesson</a></li>
            <li><a href="IncIdeas/BitterLesson.html">Duplicate bitter lesson</a></li>
            <li><a href="mailto:lynda.vang@amii.ca">media contact</a></li>
            <li><a href="javascript:void(0)">noop</a></li>
            <li><a href="">empty</a></li>
          </ul>
        </main>
        """
        parser = HTMLParser(html, base_url="http://www.incompleteideas.net")
        items = parser.parse_items(
            selectors={
                "items": 'a[href]:not([href^="mailto:"]):not([href^="javascript:"])',
            },
            max_items=20,
        )

        self.assertEqual(
            [(item["title"], item["link"]) for item in items],
            [
                ("Oak Lab", "https://oaklab.example"),
                (
                    "The Bitter Lesson",
                    "http://www.incompleteideas.net/IncIdeas/BitterLesson.html",
                ),
            ],
        )

    def test_parse_items_infers_dates_from_link_context(self):
        html = """
        <ul>
          <li><a href="IncIdeas/BitterLesson.html">The Bitter Lesson</a> 3/13/2019</li>
          <li><a href="IncIdeas/WrongWithAI.html">What's Wrong with AI</a> 11/12/01</li>
          <li><a href="IncIdeas/eoai.pdf">half a manifesto...</a> 2007</li>
          <li><a href="https://oaklab.example">Oak Lab</a></li>
        </ul>
        """
        parser = HTMLParser(html, base_url="http://www.incompleteideas.net")
        items = parser.parse_items(
            selectors={"items": "a[href]"},
            max_items=10,
            infer_dates_from_context=True,
        )
        by_title = {item["title"]: item for item in items}
        self.assertIn("13 Mar 2019", by_title["The Bitter Lesson"]["pubDate"])
        self.assertIn("12 Nov 2001", by_title["What's Wrong with AI"]["pubDate"])
        self.assertIn("01 Jan 2007", by_title["half a manifesto..."]["pubDate"])
        self.assertNotIn("pubDate", by_title["Oak Lab"])

    def test_parse_items_does_not_take_dates_from_huge_parent(self):
        html = """
        <div>
          <a href="/oak">Oak Lab</a>
          <a href="/other">Other</a>
          The Bitter Lesson 3/13/2019 and many other notes """ + ("x " * 120) + """
        </div>
        """
        parser = HTMLParser(html, base_url="http://www.incompleteideas.net")
        items = parser.parse_items(
            selectors={"items": "a[href]"},
            max_items=5,
            infer_dates_from_context=True,
        )
        self.assertEqual(items[0]["title"], "Oak Lab")
        self.assertNotIn("pubDate", items[0])

    def test_parse_items_collapses_whitespace_in_anchor_titles(self):
        html = """
        <a href="IncIdeas/BitterLesson.html">The
                    Bitter
                    Lesson</a>
        """
        parser = HTMLParser(html, base_url="http://www.incompleteideas.net")
        items = parser.parse_items(selectors={"items": "a[href]"}, max_items=5)
        self.assertEqual(items[0]["title"], "The Bitter Lesson")


if __name__ == "__main__":
    unittest.main()
