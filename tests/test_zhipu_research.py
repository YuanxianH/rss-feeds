import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import requests

from src.jobs.base import JobContext
from src.jobs.registry import create_job
from src.jobs.zhipu_research import (
    DEFAULT_ARTICLE_BASE_URL,
    article_to_item,
    article_url,
    select_articles,
    ZhipuResearchJob,
)

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

    def get(self, url: str, params=None, timeout: float = 0):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if not self.responses:
            raise requests.HTTPError("unexpected extra request")
        return self.responses.pop(0)


def _page(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ZhipuResearchHelperTests(unittest.TestCase):
    def test_article_url_uses_numeric_research_path(self):
        self.assertEqual(
            article_url(163, DEFAULT_ARTICLE_BASE_URL),
            "https://www.zhipuai.cn/zh/research/163",
        )
        self.assertEqual(
            article_url("153", "https://www.zhipuai.cn/zh/research/"),
            "https://www.zhipuai.cn/zh/research/153",
        )
        self.assertIsNone(article_url("", DEFAULT_ARTICLE_BASE_URL))
        self.assertIsNone(article_url("glm-5", DEFAULT_ARTICLE_BASE_URL))
        self.assertIsNone(article_url(0, DEFAULT_ARTICLE_BASE_URL))

    def test_article_to_item_prefers_zh_title_and_resume(self):
        item = article_to_item(
            {
                "id": 162,
                "title_zh": "GLM-5.3",
                "title_en": "English title",
                "resume_zh": "中文摘要",
                "createAt": "2026-08-14T06:00:00.000Z",
            },
            locale="zh",
            article_base_url=DEFAULT_ARTICLE_BASE_URL,
        )
        self.assertEqual(
            item,
            {
                "title": "GLM-5.3",
                "link": "https://www.zhipuai.cn/zh/research/162",
                "guid": "https://www.zhipuai.cn/zh/research/162",
                "description": "中文摘要",
                "pubDate": "2026-08-14T06:00:00.000Z",
            },
        )

    def test_article_to_item_falls_back_to_english_and_tags(self):
        item = article_to_item(
            {
                "id": 150,
                "title_zh": "",
                "title_en": "GLM-OCR",
                "tag_zh": ["多模态"],
            },
            locale="zh",
            article_base_url=DEFAULT_ARTICLE_BASE_URL,
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["title"], "GLM-OCR")
        self.assertEqual(item["description"], "多模态")

    def test_select_articles_skips_news_inactive_and_partial_docs(self):
        items = select_articles(
            _page("zhipu_articles_page1.json")["docs"],
            category="blog",
            require_active=True,
            locale="zh",
            article_base_url=DEFAULT_ARTICLE_BASE_URL,
        )
        self.assertEqual(
            [item["link"] for item in items],
            [
                "https://www.zhipuai.cn/zh/research/163",
                "https://www.zhipuai.cn/zh/research/162",
            ],
        )
        self.assertEqual(items[0]["title"], "GLM-5.3-Flash：前沿智能进入普惠时代")
        self.assertEqual(items[0]["description"], "基座模型")
        self.assertEqual(items[1]["description"], "A coding and security update")

    def test_select_articles_returns_empty_when_no_public_blogs(self):
        items = select_articles(
            [{"id": 1, "title_zh": "News only", "category": "news", "active": True}],
            category="blog",
            require_active=True,
            locale="zh",
            article_base_url=DEFAULT_ARTICLE_BASE_URL,
        )
        self.assertEqual(items, [])


class ZhipuResearchJobTests(unittest.TestCase):
    def test_registry_creates_zhipu_job(self):
        job = create_job({"type": "zhipu_research", "name": "Zhipu AI Research"})
        self.assertIsInstance(job, ZhipuResearchJob)
        self.assertEqual(job.job_type, "zhipu_research")

    @patch("src.jobs.zhipu_research.create_retry_session")
    def test_job_paginates_and_writes_rss(self, create_session):
        session = FakeSession(
            [
                FakeResponse(_page("zhipu_articles_page1.json"), "https://www.zhipuai.cn/api/articles"),
                FakeResponse(_page("zhipu_articles_page2.json"), "https://www.zhipuai.cn/api/articles"),
            ]
        )
        create_session.return_value = session

        with tempfile.TemporaryDirectory() as temp_dir:
            result = ZhipuResearchJob(
                {
                    "name": "Zhipu AI Research",
                    "output": "zhipu_research.xml",
                    "title": "Zhipu AI Research",
                    "link": DEFAULT_ARTICLE_BASE_URL,
                    "options": {"page_size": 6, "max_items": 10},
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            output = Path(temp_dir) / "zhipu_research.xml"
            root = ET.parse(output).getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0]["params"]["page"], 1)
        self.assertEqual(session.calls[1]["params"]["page"], 2)
        self.assertEqual(session.calls[0]["params"]["where[category][equals]"], "blog")
        titles = [item.findtext("title") for item in root.findall("./channel/item")]
        links = [item.findtext("link") for item in root.findall("./channel/item")]
        self.assertEqual(
            titles,
            [
                "GLM-5.3-Flash：前沿智能进入普惠时代",
                "GLM-5.3：前沿编程能力与涌现的网络安全能力",
                "GLM-OCR",
            ],
        )
        self.assertEqual(
            links,
            [
                "https://www.zhipuai.cn/zh/research/163",
                "https://www.zhipuai.cn/zh/research/162",
                "https://www.zhipuai.cn/zh/research/150",
            ],
        )
        self.assertEqual(
            root.findtext("./channel/item/description"),
            "基座模型",
        )

    @patch("src.jobs.zhipu_research.create_retry_session")
    def test_job_keeps_working_when_later_page_has_partial_docs(self, create_session):
        create_session.return_value = FakeSession(
            [
                FakeResponse(_page("zhipu_articles_page1.json"), "https://www.zhipuai.cn/api/articles"),
                FakeResponse(
                    {"docs": [{"id": "bad", "category": "blog", "active": True}], "hasNextPage": False},
                    "https://www.zhipuai.cn/api/articles",
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = ZhipuResearchJob(
                {"name": "Zhipu AI Research", "output": "zhipu_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "zhipu_research.xml").getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(root.findall("./channel/item")), 2)

    @patch("src.jobs.zhipu_research.create_retry_session")
    def test_empty_public_list_fails(self, create_session):
        create_session.return_value = FakeSession(
            [
                FakeResponse(
                    {"docs": [{"id": 1, "title_zh": "News", "category": "news", "active": True}], "hasNextPage": False},
                    "https://www.zhipuai.cn/api/articles",
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ZhipuResearchJob(
                {"name": "Zhipu AI Research", "output": "zhipu_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
        self.assertFalse(result.success)
        self.assertIn("未找到任何研究博客", result.details)

    @patch("src.jobs.zhipu_research.create_retry_session")
    def test_api_http_error_fails(self, create_session):
        create_session.return_value = FakeSession(
            [FakeResponse({}, "https://www.zhipuai.cn/api/articles", status_code=503)]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ZhipuResearchJob(
                {"name": "Zhipu AI Research", "output": "zhipu_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
        self.assertFalse(result.success)
        self.assertIn("调用智谱 API 失败", result.details)

    @patch("src.jobs.zhipu_research.create_retry_session")
    def test_invalid_payload_fails(self, create_session):
        create_session.return_value = FakeSession(
            [FakeResponse(["not", "an", "object"], "https://www.zhipuai.cn/api/articles")]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ZhipuResearchJob(
                {"name": "Zhipu AI Research", "output": "zhipu_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
        self.assertFalse(result.success)
        self.assertIn("非法 JSON", result.details)


if __name__ == "__main__":
    unittest.main()
