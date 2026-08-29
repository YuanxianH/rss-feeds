import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import requests

from src.jobs.base import JobContext
from src.jobs.hunyuan_research import (
    DEFAULT_ARTICLE_BASE_URL,
    HunyuanResearchJob,
    article_to_item,
    article_url,
    select_articles,
    unix_timestamp_to_iso,
)
from src.jobs.registry import create_job

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, payload, url: str, status_code: int = 200):
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)
        self.url = url
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} response")

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("No JSON object could be decoded")
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url: str, json=None, headers=None, timeout: float = 0):
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        if not self.responses:
            raise requests.HTTPError("unexpected extra request")
        return self.responses.pop(0)


def _page(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class HunyuanResearchHelperTests(unittest.TestCase):
    def test_article_url_prefers_custom_slug(self):
        self.assertEqual(
            article_url({"customUrl": "elr", "id": 100091}, DEFAULT_ARTICLE_BASE_URL),
            "https://hy.tencent.com/research/elr",
        )
        self.assertEqual(
            article_url({"customUrl": "hy4-preview"}, "https://hy.tencent.com/research/"),
            "https://hy.tencent.com/research/hy4-preview",
        )

    def test_article_url_falls_back_to_numeric_id(self):
        self.assertEqual(
            article_url({"id": 100041, "customUrl": ""}, DEFAULT_ARTICLE_BASE_URL),
            "https://hy.tencent.com/research/100041",
        )
        self.assertEqual(
            article_url({"id": "100025"}, DEFAULT_ARTICLE_BASE_URL),
            "https://hy.tencent.com/research/100025",
        )
        self.assertIsNone(article_url({"id": "", "customUrl": ""}, DEFAULT_ARTICLE_BASE_URL))
        self.assertIsNone(article_url({"id": 0}, DEFAULT_ARTICLE_BASE_URL))
        self.assertIsNone(article_url({"id": "hy4"}, DEFAULT_ARTICLE_BASE_URL))

    def test_unix_timestamp_to_iso_handles_seconds_and_millis(self):
        self.assertEqual(
            unix_timestamp_to_iso(1787846400),
            "2026-08-27T16:00:00+00:00",
        )
        self.assertEqual(
            unix_timestamp_to_iso(1787846400000),
            "2026-08-27T16:00:00+00:00",
        )
        self.assertEqual(unix_timestamp_to_iso(""), "")
        self.assertEqual(unix_timestamp_to_iso(0), "")

    def test_article_to_item_uses_desc_author_and_display_time(self):
        item = article_to_item(
            {
                "id": 100091,
                "title": "From LR to ELR",
                "desc": "引入有效学习率。",
                "author": "Pretrain Team",
                "displayPublishTime": 1786377600,
                "customUrl": "elr",
            },
            article_base_url=DEFAULT_ARTICLE_BASE_URL,
        )
        self.assertEqual(
            item,
            {
                "title": "From LR to ELR",
                "link": "https://hy.tencent.com/research/elr",
                "guid": "https://hy.tencent.com/research/elr",
                "description": "引入有效学习率。",
                "author": "Pretrain Team",
                "pubDate": "2026-08-10T16:00:00+00:00",
            },
        )

    def test_article_to_item_normalizes_semicolon_authors(self):
        item = article_to_item(
            {
                "id": 100041,
                "title": "Hy-MT2",
                "author": "pokolv;moonzheng;jasonzli",
            },
            article_base_url=DEFAULT_ARTICLE_BASE_URL,
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["author"], "pokolv, moonzheng, jasonzli")
        self.assertEqual(item["link"], "https://hy.tencent.com/research/100041")

    def test_select_articles_skips_partial_docs_and_preserves_order(self):
        items = select_articles(
            _page("hunyuan_public_list_page1.json")["data"]["list"],
            article_base_url=DEFAULT_ARTICLE_BASE_URL,
        )
        self.assertEqual(
            [item["link"] for item in items],
            [
                "https://hy.tencent.com/research/hy4-preview",
                "https://hy.tencent.com/research/elr",
                "https://hy.tencent.com/research/100041",
            ],
        )
        self.assertEqual(items[0]["title"], "Hy4 preview 发布")
        self.assertEqual(items[1]["description"], "引入有效学习率来控制模型权重的方向变化。")
        self.assertEqual(items[2]["author"], "pokolv, moonzheng, jasonzli")

    def test_select_articles_returns_empty_when_no_public_posts(self):
        items = select_articles(
            [{"id": None, "title": "bad"}, {"title": ""}],
            article_base_url=DEFAULT_ARTICLE_BASE_URL,
        )
        self.assertEqual(items, [])


class HunyuanResearchJobTests(unittest.TestCase):
    def test_registry_creates_hunyuan_job(self):
        job = create_job({"type": "hunyuan_research", "name": "Tencent Hunyuan Research"})
        self.assertIsInstance(job, HunyuanResearchJob)
        self.assertEqual(job.job_type, "hunyuan_research")

    @patch("src.jobs.hunyuan_research.create_retry_session")
    def test_job_paginates_and_writes_rss(self, create_session):
        session = FakeSession(
            [
                FakeResponse(
                    _page("hunyuan_public_list_page1.json"),
                    "https://api.hunyuan.tencent.com/api/blog/publicList",
                ),
                FakeResponse(
                    _page("hunyuan_public_list_page2.json"),
                    "https://api.hunyuan.tencent.com/api/blog/publicList",
                ),
            ]
        )
        create_session.return_value = session

        with tempfile.TemporaryDirectory() as temp_dir:
            result = HunyuanResearchJob(
                {
                    "name": "Tencent Hunyuan Research",
                    "output": "hunyuan_research.xml",
                    "title": "Tencent Hunyuan Research",
                    "link": DEFAULT_ARTICLE_BASE_URL,
                    "options": {"page_size": 4, "max_items": 10},
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            output = Path(temp_dir) / "hunyuan_research.xml"
            root = ET.parse(output).getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0]["json"]["pageNum"], 1)
        self.assertEqual(session.calls[1]["json"]["pageNum"], 2)
        self.assertEqual(session.calls[0]["json"]["pageSize"], 4)
        self.assertFalse(session.calls[0]["json"]["needFilter"])
        self.assertEqual(session.calls[0]["headers"]["accept-language"], "zh")
        titles = [item.findtext("title") for item in root.findall("./channel/item")]
        links = [item.findtext("link") for item in root.findall("./channel/item")]
        self.assertEqual(
            titles,
            [
                "Hy4 preview 发布",
                "From LR to ELR: A Better Heuristic for Pretraining Dynamics",
                "Hy-MT2：面向实际应用场景的高性能多语言翻译模型",
                "Learning from context is harder than we thought",
                "Stabilizing RLVR via Token-level Gradient Diagnosis and Layerwise Clipping",
            ],
        )
        self.assertEqual(
            links,
            [
                "https://hy.tencent.com/research/hy4-preview",
                "https://hy.tencent.com/research/elr",
                "https://hy.tencent.com/research/100041",
                "https://hy.tencent.com/research/100025",
                "https://hy.tencent.com/research/100015",
            ],
        )
        self.assertEqual(
            root.findtext("./channel/item/description"),
            "引入有效学习率来控制模型权重的方向变化。",
        )

    @patch("src.jobs.hunyuan_research.create_retry_session")
    def test_job_keeps_working_when_later_page_has_partial_docs(self, create_session):
        create_session.return_value = FakeSession(
            [
                FakeResponse(
                    _page("hunyuan_public_list_page1.json"),
                    "https://api.hunyuan.tencent.com/api/blog/publicList",
                ),
                FakeResponse(
                    {
                        "code": 0,
                        "data": {
                            "totalNum": 6,
                            "list": [
                                {"id": "bad", "title": "broken"},
                                {
                                    "id": 100025,
                                    "title": "Learning from context is harder than we thought",
                                },
                            ],
                        },
                    },
                    "https://api.hunyuan.tencent.com/api/blog/publicList",
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = HunyuanResearchJob(
                {"name": "Tencent Hunyuan Research", "output": "hunyuan_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "hunyuan_research.xml").getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(root.findall("./channel/item")), 4)

    @patch("src.jobs.hunyuan_research.create_retry_session")
    def test_empty_public_list_fails(self, create_session):
        create_session.return_value = FakeSession(
            [
                FakeResponse(
                    {"code": 0, "data": {"totalNum": 0, "list": []}},
                    "https://api.hunyuan.tencent.com/api/blog/publicList",
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = HunyuanResearchJob(
                {"name": "Tencent Hunyuan Research", "output": "hunyuan_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
        self.assertFalse(result.success)
        self.assertIn("未找到任何研究成果", result.details)

    @patch("src.jobs.hunyuan_research.create_retry_session")
    def test_api_http_error_fails(self, create_session):
        create_session.return_value = FakeSession(
            [
                FakeResponse(
                    {},
                    "https://api.hunyuan.tencent.com/api/blog/publicList",
                    status_code=503,
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = HunyuanResearchJob(
                {"name": "Tencent Hunyuan Research", "output": "hunyuan_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
        self.assertFalse(result.success)
        self.assertIn("调用混元 API 失败", result.details)

    @patch("src.jobs.hunyuan_research.create_retry_session")
    def test_invalid_payload_fails(self, create_session):
        create_session.return_value = FakeSession(
            [
                FakeResponse(
                    ["not", "an", "object"],
                    "https://api.hunyuan.tencent.com/api/blog/publicList",
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = HunyuanResearchJob(
                {"name": "Tencent Hunyuan Research", "output": "hunyuan_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
        self.assertFalse(result.success)
        self.assertIn("非法 JSON", result.details)

    @patch("src.jobs.hunyuan_research.create_retry_session")
    def test_business_error_code_fails(self, create_session):
        create_session.return_value = FakeSession(
            [
                FakeResponse(
                    {"code": 1, "msg": "denied", "data": {"list": []}},
                    "https://api.hunyuan.tencent.com/api/blog/publicList",
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = HunyuanResearchJob(
                {"name": "Tencent Hunyuan Research", "output": "hunyuan_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
        self.assertFalse(result.success)
        self.assertIn("非法 JSON", result.details)


if __name__ == "__main__":
    unittest.main()
