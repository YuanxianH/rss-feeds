import unittest

from scripts.feed_jobs.fetch_minimax_blog import (
    extract_article_item_from_html,
    extract_news_urls_from_html,
    _extract_news_urls_from_text,
    normalize_news_url,
)


class MiniMaxFeedJobTests(unittest.TestCase):
    def test_normalize_news_url(self):
        self.assertEqual(
            normalize_news_url("/news/minimax-m25?utm_source=test#top"),
            "https://www.minimax.io/news/minimax-m25",
        )
        self.assertIsNone(normalize_news_url("https://www.minimax.io/news"))
        self.assertIsNone(normalize_news_url("https://example.com/news/minimax-m25"))

    def test_extract_news_urls_from_html_with_anchor_and_embedded_json(self):
        html = """
        <html>
          <body>
            <a href="/news/minimax-m25">M2.5</a>
            <a href="https://www.minimax.io/news/minimax-mcp?ref=abc">MCP</a>
            <script id="__NEXT_DATA__" type="application/json">
              {"props":{"items":[{"url":"/news/minimax-agent"},{"url":"/news/minimax-m25"}]}}
            </script>
          </body>
        </html>
        """
        urls = extract_news_urls_from_html(html)
        self.assertEqual(
            urls,
            [
                "https://www.minimax.io/news/minimax-m25",
                "https://www.minimax.io/news/minimax-mcp",
                "https://www.minimax.io/news/minimax-agent",
            ],
        )

    def test_extract_article_item_from_html(self):
        html = """
        <html>
          <head>
            <meta property="og:title" content="MiniMax M2.5" />
            <meta property="og:description" content="MiniMax latest model update" />
            <meta property="article:published_time" content="2026-02-12T09:30:00Z" />
            <link rel="canonical" href="https://www.minimax.io/news/minimax-m25?x=1" />
          </head>
          <body><h1>Fallback Title</h1></body>
        </html>
        """
        item = extract_article_item_from_html("https://www.minimax.io/news/minimax-m25", html)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["title"], "MiniMax M2.5")
        self.assertEqual(item["description"], "MiniMax latest model update")
        self.assertEqual(item["link"], "https://www.minimax.io/news/minimax-m25")
        self.assertTrue(item["pubDate"].startswith("2026-02-12T09:30:00"))

    def test_extract_news_urls_from_text(self):
        text = """
        something /news/minimax-mcp and /news/minimax-m25?x=1
        plus /news/minimax-agent#section
        """
        urls = _extract_news_urls_from_text(text, "https://www.minimax.io/news")
        self.assertEqual(
            urls,
            [
                "https://www.minimax.io/news/minimax-mcp",
                "https://www.minimax.io/news/minimax-m25",
                "https://www.minimax.io/news/minimax-agent",
            ],
        )


if __name__ == "__main__":
    unittest.main()
