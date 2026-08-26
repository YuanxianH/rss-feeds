import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import requests

from src.article_metadata import extract_article_item
from src.discovery import extract_article_urls, make_url_normalizer
from src.jobs.base import JobContext
from src.jobs.dynamic_site import DynamicSiteJob

FIXTURES = Path(__file__).parent / "fixtures"


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


class DynamicDiscoveryTests(unittest.TestCase):
    def test_extracts_kimi_visible_and_flight_data_links(self):
        html = (FIXTURES / "kimi_blog_index.html").read_text(encoding="utf-8")
        normalize = make_url_normalizer(
            allowed_hosts=["kimi.ai"],
            path_prefix="/blog",
        )

        urls = extract_article_urls(
            html,
            page_url="https://www.kimi.ai/blog/",
            normalize_url=normalize,
        )

        self.assertEqual(
            urls,
            [
                "https://www.kimi.ai/blog/kimi-k3",
                "https://www.kimi.ai/blog/kimi-k2",
                "https://www.kimi.ai/blog/kimi-k1",
            ],
        )

    def test_extracts_minimax_links_outside_article_elements(self):
        html = (FIXTURES / "minimax_blog_index.html").read_text(encoding="utf-8")
        normalize = make_url_normalizer(
            allowed_hosts=["minimax.io"],
            path_prefix="/blog",
        )

        urls = extract_article_urls(
            html,
            page_url="https://www.minimax.io/blog",
            normalize_url=normalize,
        )

        self.assertEqual(
            urls,
            [
                "https://www.minimax.io/blog/minimax-m2-5",
                "https://www.minimax.io/blog/agent-native-memory",
                "https://www.minimax.io/blog/speech-02-release",
            ],
        )

    def test_article_metadata_uses_canonical_and_json_ld_date(self):
        normalize = make_url_normalizer(
            allowed_hosts=["kimi.ai"],
            path_prefix="/blog",
        )
        html = """
        <html>
          <head>
            <meta property="og:title" content="Kimi K3" />
            <meta name="description" content="Kimi model update" />
            <link rel="canonical" href="/blog/kimi-k3?from=home" />
            <script type="application/ld+json">
              {"@type":"Article","datePublished":"2026-08-20T09:30:00Z"}
            </script>
          </head>
        </html>
        """

        item = extract_article_item(
            "https://www.kimi.ai/blog/kimi-k3",
            html,
            normalize_url=normalize,
        )

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["link"], "https://www.kimi.ai/blog/kimi-k3")
        self.assertEqual(item["title"], "Kimi K3")
        self.assertTrue(item["pubDate"].startswith("2026-08-20T09:30:00"))

    @patch("src.jobs.dynamic_site.create_retry_session")
    def test_dynamic_job_keeps_working_when_one_article_fails(self, create_session):
        index_url = "https://www.kimi.ai/blog/"
        article_url = "https://www.kimi.ai/blog/kimi-k3"
        failed_url = "https://www.kimi.ai/blog/kimi-k2"
        create_session.return_value = FakeSession(
            {
                index_url: FakeResponse(
                    f'<a href="{article_url}">K3</a><a href="{failed_url}">K2</a>',
                    index_url,
                ),
                article_url: FakeResponse(
                    """
                    <html><head>
                      <meta property="og:title" content="Kimi K3" />
                      <meta name="description" content="A release" />
                    </head></html>
                    """,
                    article_url,
                ),
                failed_url: FakeResponse("", failed_url, status_code=503),
            }
        )
        job = DynamicSiteJob(
            {
                "name": "Kimi Blog",
                "url": index_url,
                "path_prefix": "/blog",
                "allowed_hosts": ["kimi.ai"],
                "output": "kimi.xml",
                "options": {"minimum_items": 1},
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = job.run(JobContext(feeds_dir=Path(temp_dir)))
            output = Path(temp_dir) / "kimi.xml"
            root = ET.parse(output).getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(root.findall("./channel/item")), 1)
        self.assertEqual(root.findtext("./channel/item/title"), "Kimi K3")


if __name__ == "__main__":
    unittest.main()
