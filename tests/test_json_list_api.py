import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import requests

from src.jobs.base import JobContext
from src.jobs.json_list_api import (
    JsonListApiJob,
    article_to_item,
    coerce_pubdate,
    extract_page_docs,
    get_by_path,
)
from src.jobs.registry import create_job


class FakeResponse:
    def __init__(self, payload, url: str, status_code: int = 200):
        self._payload = payload
        self.url = url
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} response")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url: str, params=None, headers=None, timeout: float = 0):
        self.calls.append(
            {"method": "GET", "url": url, "params": params, "headers": headers}
        )
        if not self.responses:
            raise requests.HTTPError("unexpected extra request")
        return self.responses.pop(0)

    def post(self, url: str, json=None, headers=None, timeout: float = 0):
        self.calls.append(
            {"method": "POST", "url": url, "json": json, "headers": headers}
        )
        if not self.responses:
            raise requests.HTTPError("unexpected extra request")
        return self.responses.pop(0)


class JsonListApiHelperTests(unittest.TestCase):
    def test_get_by_path_reads_nested_list(self):
        self.assertEqual(get_by_path({"data": {"list": [1]}}, "data.list"), [1])
        self.assertIsNone(get_by_path({"data": {}}, "data.list"))

    def test_extract_page_docs_tries_default_list_paths(self):
        docs, total = extract_page_docs(
            {"code": 0, "data": {"docs": [{"id": 1}], "total": 3}},
            {},
        )
        self.assertEqual(docs, [{"id": 1}])
        self.assertEqual(total, 3)

    def test_article_to_item_uses_configured_fields_and_iso_dates(self):
        item = article_to_item(
            {
                "headline": "Reusable API post",
                "abstract": "Works after the page schema changes.",
                "path": "/posts/reusable",
                "published": "2026-08-20T08:00:00Z",
            },
            article_base_url="https://example.com",
            fields={
                "title": ["headline"],
                "description": ["abstract"],
                "slug": ["path"],
                "date": ["published"],
            },
        )
        self.assertEqual(
            item,
            {
                "title": "Reusable API post",
                "link": "https://example.com/posts/reusable",
                "guid": "https://example.com/posts/reusable",
                "description": "Works after the page schema changes.",
                "pubDate": "2026-08-20T08:00:00Z",
            },
        )

    def test_article_to_item_keeps_absolute_url_slugs(self):
        item = article_to_item(
            {
                "title": "External paper",
                "url": "https://arxiv.org/abs/1234.5678",
            },
            article_base_url="https://example.com/research",
            fields={"slug": ["url", "id"]},
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["link"], "https://arxiv.org/abs/1234.5678")

    def test_coerce_pubdate_accepts_unix_or_iso(self):
        self.assertEqual(coerce_pubdate(1787846400), "2026-08-27T16:00:00+00:00")
        self.assertEqual(coerce_pubdate("2026-08-01T00:00:00Z"), "2026-08-01T00:00:00Z")
        self.assertEqual(coerce_pubdate(""), "")


class JsonListApiJobTests(unittest.TestCase):
    def test_registry_creates_generic_job(self):
        job = create_job(
            {
                "type": "json_list_api",
                "name": "Example",
                "api_url": "https://example.com/api",
                "article_base_url": "https://example.com/blog",
                "output": "example.xml",
            }
        )
        self.assertIsInstance(job, JsonListApiJob)
        self.assertEqual(job.job_type, "json_list_api")

    @patch("src.jobs.json_list_api.create_retry_session")
    def test_get_job_paginates_a_different_schema(self, create_session):
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "items": [
                            {
                                "headline": "First",
                                "path": "first",
                                "published": "2026-08-02T00:00:00Z",
                            }
                        ],
                        "total": 2,
                    },
                    "https://example.com/api/posts",
                ),
                FakeResponse(
                    {
                        "items": [
                            {
                                "headline": "Second",
                                "path": "second",
                                "published": "2026-08-01T00:00:00Z",
                            }
                        ],
                        "total": 2,
                    },
                    "https://example.com/api/posts",
                ),
            ]
        )
        create_session.return_value = session

        with tempfile.TemporaryDirectory() as temp_dir:
            result = JsonListApiJob(
                {
                    "name": "Example Research",
                    "api_url": "https://example.com/api/posts",
                    "article_base_url": "https://example.com/blog",
                    "method": "GET",
                    "output": "example.xml",
                    "fields": {
                        "list": "items",
                        "total": "total",
                        "title": ["headline"],
                        "slug": ["path"],
                        "date": ["published"],
                    },
                    "request": {"page_key": "page", "page_size_key": "limit"},
                    "options": {"page_size": 1, "max_items": 10},
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "example.xml").getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0]["method"], "GET")
        self.assertEqual(session.calls[0]["params"]["page"], 1)
        self.assertEqual(session.calls[1]["params"]["page"], 2)
        self.assertEqual(
            [item.findtext("title") for item in root.findall("./channel/item")],
            ["First", "Second"],
        )
        self.assertEqual(
            [item.findtext("link") for item in root.findall("./channel/item")],
            [
                "https://example.com/blog/first",
                "https://example.com/blog/second",
            ],
        )

    @patch("src.jobs.json_list_api.create_retry_session")
    def test_missing_required_config_fails(self, create_session):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = JsonListApiJob({"name": "Broken"}).run(
                JobContext(feeds_dir=Path(temp_dir))
            )
        self.assertFalse(result.success)
        self.assertIn("api_url", result.details)
        create_session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
