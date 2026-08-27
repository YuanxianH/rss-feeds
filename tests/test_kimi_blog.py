import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import requests

from src.jobs.base import JobContext
from src.jobs.kimi_blog import (
    BLOG_URL,
    KimiBlogJob,
    extract_article_item,
    extract_article_urls_from_index,
    normalize_article_url,
)


class FakeResponse:
    def __init__(self, text: str, url: str, status_code: int = 200):
        self.text = text
        self.url = url
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} response")


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse]):
        self.responses = responses

    def get(self, url: str, timeout: float):
        response = self.responses[url]
        return response


class KimiBlogJobTests(unittest.TestCase):
    def test_normalize_keeps_kimi_ai_article_and_rewrites_old_host(self):
        self.assertEqual(
            normalize_article_url("/blog/kimi-k3?from=home#top"),
            "https://www.kimi.ai/blog/kimi-k3",
        )
        self.assertEqual(
            normalize_article_url("https://www.kimi.com/blog/worldvqa"),
            "https://www.kimi.ai/blog/worldvqa",
        )
        self.assertIsNone(normalize_article_url("https://www.kimi.ai/blog/"))
        self.assertIsNone(normalize_article_url("https://www.kimi.ai/de/blog/kimi-k3"))
        self.assertIsNone(normalize_article_url("/blog/ListItem"))
        self.assertIsNone(normalize_article_url("/blog/Research"))
        self.assertIsNone(normalize_article_url("https://example.com/blog/kimi-k3"))

    def test_extracts_visible_and_next_flight_links_without_vitepress_map(self):
        html = """
        <html>
          <body>
            <a href="/blog/kimi-k3">Kimi K3</a>
            <a href="/blog/">Blog home</a>
            <a href="/blog/ListItem">schema noise</a>
            <script>
              self.__next_f.push([1, "href:\\"/blog/worldvqa\\""])
              self.__next_f.push([1, "https://www.kimi.ai/blog/kimi-k2-6"])
            </script>
          </body>
        </html>
        """

        self.assertEqual(
            extract_article_urls_from_index(html),
            [
                "https://www.kimi.ai/blog/kimi-k3",
                "https://www.kimi.ai/blog/worldvqa",
                "https://www.kimi.ai/blog/kimi-k2-6",
            ],
        )

    def test_extracts_vitepress_hash_map_as_fallback(self):
        html = r"""
        <script>
          __VP_HASH_MAP__=JSON.parse("{\"index.md\":\"aaa\",\"kimi-k1.md\":\"bbb\"}")
        </script>
        """
        self.assertEqual(
            extract_article_urls_from_index(html),
            ["https://www.kimi.ai/blog/kimi-k1"],
        )

    def test_extract_article_item_prefers_open_graph(self):
        html = """
        <html>
          <head>
            <title>Browser title</title>
            <meta property="og:title" content="Kimi K3 Tech Blog" />
            <meta property="og:description" content="Open frontier intelligence" />
          </head>
        </html>
        """
        item = extract_article_item("https://www.kimi.ai/blog/kimi-k3", html)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["title"], "Kimi K3 Tech Blog")
        self.assertEqual(item["description"], "Open frontier intelligence")
        self.assertEqual(item["link"], "https://www.kimi.ai/blog/kimi-k3")

    def test_empty_index_without_article_links(self):
        self.assertEqual(extract_article_urls_from_index("<html><body>No posts</body></html>"), [])

    @patch("src.jobs.kimi_blog.create_session")
    def test_job_writes_rss_when_one_article_fails(self, create_session):
        index_html = '<a href="/blog/kimi-k3">K3</a><a href="/blog/kimi-k2">K2</a>'
        article_html = """
        <html><head>
          <meta property="og:title" content="Kimi K3" />
          <meta name="description" content="A release" />
        </head></html>
        """
        create_session.return_value = FakeSession(
            {
                BLOG_URL: FakeResponse(index_html, BLOG_URL),
                "https://www.kimi.ai/blog/kimi-k3": FakeResponse(
                    article_html, "https://www.kimi.ai/blog/kimi-k3"
                ),
                "https://www.kimi.ai/blog/kimi-k2": FakeResponse(
                    "", "https://www.kimi.ai/blog/kimi-k2", status_code=503
                ),
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = KimiBlogJob(
                {
                    "name": "Kimi Blog",
                    "output": "kimi_blog.xml",
                    "title": "Kimi Blog",
                    "link": BLOG_URL,
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            output = Path(temp_dir) / "kimi_blog.xml"
            root = ET.parse(output).getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(root.findall("./channel/item")), 1)
        self.assertEqual(root.findtext("./channel/item/title"), "Kimi K3")
        self.assertEqual(
            root.findtext("./channel/item/link"),
            "https://www.kimi.ai/blog/kimi-k3",
        )


if __name__ == "__main__":
    unittest.main()
