import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import requests

from src.article_metadata import extract_article_item
from src.discovery import extract_article_urls, make_url_normalizer
from src.jobs.base import JobContext
from src.jobs.kimi_blog import KIMI_BLOG_URL, KimiBlogJob


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
        response.url = response.url or url
        return response


def _kimi_normalize():
    return make_url_normalizer(allowed_hosts=["kimi.ai"], path_prefix="/blog")


class KimiBlogJobTests(unittest.TestCase):
    def test_adapter_fills_kimi_ai_defaults(self):
        job = KimiBlogJob({"name": "Kimi Blog"})
        self.assertEqual(job.job_type, "kimi_blog")
        self.assertEqual(job.config["url"], KIMI_BLOG_URL)
        self.assertEqual(job.config["path_prefix"], "/blog")
        self.assertEqual(job.config["allowed_hosts"], ["kimi.ai"])
        self.assertEqual(job.config["output"], "kimi_blog.xml")

    def test_normalize_keeps_kimi_ai_article_paths(self):
        normalize = _kimi_normalize()
        self.assertEqual(
            normalize("/blog/kimi-k3?from=home#top", KIMI_BLOG_URL),
            "https://www.kimi.ai/blog/kimi-k3",
        )
        self.assertIsNone(normalize("https://www.kimi.ai/blog/", KIMI_BLOG_URL))
        self.assertIsNone(normalize("https://www.kimi.ai/de/blog/kimi-k3", KIMI_BLOG_URL))
        self.assertIsNone(normalize("https://example.com/blog/kimi-k3", KIMI_BLOG_URL))

    def test_extracts_visible_and_next_flight_links(self):
        html = """
        <html>
          <body>
            <a href="/blog/kimi-k3">Kimi K3</a>
            <a href="/blog/">Blog home</a>
            <script>
              self.__next_f.push([1, "href:\\"/blog/worldvqa\\""])
              self.__next_f.push([1, "https://www.kimi.ai/blog/kimi-k2-6"])
            </script>
          </body>
        </html>
        """

        self.assertEqual(
            extract_article_urls(
                html,
                page_url=KIMI_BLOG_URL,
                normalize_url=_kimi_normalize(),
            ),
            [
                "https://www.kimi.ai/blog/kimi-k3",
                "https://www.kimi.ai/blog/worldvqa",
                "https://www.kimi.ai/blog/kimi-k2-6",
            ],
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
        item = extract_article_item(
            "https://www.kimi.ai/blog/kimi-k3",
            html,
            normalize_url=_kimi_normalize(),
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["title"], "Kimi K3 Tech Blog")
        self.assertEqual(item["description"], "Open frontier intelligence")
        self.assertEqual(item["link"], "https://www.kimi.ai/blog/kimi-k3")

    def test_empty_index_without_article_links(self):
        self.assertEqual(
            extract_article_urls(
                "<html><body>No posts</body></html>",
                page_url=KIMI_BLOG_URL,
                normalize_url=_kimi_normalize(),
            ),
            [],
        )

    @patch("src.jobs.dynamic_site.create_retry_session")
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
                KIMI_BLOG_URL: FakeResponse(index_html, KIMI_BLOG_URL),
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
                    "link": KIMI_BLOG_URL,
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
