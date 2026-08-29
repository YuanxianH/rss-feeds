import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import requests

from src.cms_records import record_to_item, record_url, collect_article_records
from src.discovery import extract_article_urls, make_url_normalizer
from src.jobs.base import JobContext
from src.jobs.dynamic_site import DynamicSiteJob
from src.jobs.registry import create_job
from src.jobs.zhipu_research import (
    DEFAULT_ARTICLE_BASE_URL,
    ZHIPU_API_URL,
    ZHIPU_RESEARCH_URL,
    ZhipuResearchJob,
)

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, text="", url="", status_code=200, payload=None):
        self.url = url
        self.status_code = status_code
        if payload is not None:
            self._payload = payload
            self.text = json.dumps(payload)
        else:
            self._payload = None
            self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} response")

    def json(self):
        if self._payload is not None:
            return self._payload
        raise ValueError("No JSON object could be decoded")


class FakeSession:
    def __init__(self, responses: dict):
        self.responses = responses
        self.calls: list[dict] = []

    def get(self, url: str, timeout: float = 0, params=None, **kwargs):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        value = self.responses[url]
        if isinstance(value, list):
            if not value:
                raise requests.HTTPError("unexpected extra request")
            return value.pop(0)
        return value


def _normalize():
    return make_url_normalizer(
        allowed_hosts=["zhipuai.cn"],
        path_prefix="/zh/research",
    )


def _page(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ZhipuRecordTests(unittest.TestCase):
    def test_record_url_uses_numeric_research_path(self):
        self.assertEqual(
            record_url(
                {"id": 163},
                page_url=DEFAULT_ARTICLE_BASE_URL,
                path_prefix="/zh/research",
            ),
            "https://www.zhipuai.cn/zh/research/163",
        )
        self.assertIsNone(
            record_url(
                {"id": "glm-5"},
                page_url=DEFAULT_ARTICLE_BASE_URL,
                path_prefix="/zh/research",
            )
        )

    def test_record_to_item_prefers_zh_title_and_resume(self):
        item = record_to_item(
            {
                "id": 162,
                "title_zh": "GLM-5.3",
                "title_en": "English title",
                "resume_zh": "中文摘要",
                "createAt": "2026-08-14T06:00:00.000Z",
            },
            page_url=DEFAULT_ARTICLE_BASE_URL,
            path_prefix="/zh/research",
            locale="zh",
            normalize_url=_normalize(),
        )
        self.assertEqual(item["title"], "GLM-5.3")
        self.assertEqual(item["link"], "https://www.zhipuai.cn/zh/research/162")
        self.assertEqual(item["description"], "中文摘要")
        self.assertEqual(item["pubDate"], "2026-08-14T06:00:00.000Z")

    def test_collect_records_skips_news_inactive_and_partial_docs(self):
        records = collect_article_records(
            _page("zhipu_articles_page1.json"),
            category="blog",
            require_active=True,
        )
        self.assertEqual([doc["id"] for doc in records], [163, 162])


class ZhipuDiscoveryTests(unittest.TestCase):
    def test_extracts_numeric_ids_from_next_flight_data(self):
        html = (FIXTURES / "zhipu_research_index.html").read_text(encoding="utf-8")
        urls = extract_article_urls(
            html,
            page_url=ZHIPU_RESEARCH_URL,
            normalize_url=_normalize(),
            category="blog",
            require_active=True,
        )
        self.assertEqual(
            urls,
            [
                "https://www.zhipuai.cn/zh/research/163",
                "https://www.zhipuai.cn/zh/research/162",
            ],
        )

    def test_without_filters_still_ignores_media_ids(self):
        html = (FIXTURES / "zhipu_research_index.html").read_text(encoding="utf-8")
        urls = extract_article_urls(
            html,
            page_url=ZHIPU_RESEARCH_URL,
            normalize_url=_normalize(),
        )
        self.assertIn("https://www.zhipuai.cn/zh/research/152", urls)
        self.assertNotIn("https://www.zhipuai.cn/zh/research/1064", urls)


class ZhipuResearchJobTests(unittest.TestCase):
    def test_adapter_fills_dynamic_site_defaults(self):
        job = create_job({"type": "zhipu_research", "name": "Zhipu AI Research"})
        self.assertIsInstance(job, ZhipuResearchJob)
        self.assertEqual(job.job_type, "zhipu_research")
        self.assertEqual(job.config["url"], ZHIPU_RESEARCH_URL)
        self.assertEqual(job.config["path_prefix"], "/zh/research")
        self.assertEqual(job.config["api_urls"], [ZHIPU_API_URL])
        self.assertEqual(job.config["category"], "blog")
        self.assertTrue(job.config["options"]["require_active"])

    @patch("src.jobs.dynamic_site.create_retry_session")
    def test_job_uses_api_records_and_skips_filtered_docs(self, create_session):
        create_session.return_value = FakeSession(
            {
                ZHIPU_RESEARCH_URL: FakeResponse(
                    "<html><body>cards without links</body></html>",
                    ZHIPU_RESEARCH_URL,
                ),
                ZHIPU_API_URL: [
                    FakeResponse(
                        url=ZHIPU_API_URL,
                        payload=_page("zhipu_articles_page1.json"),
                    ),
                    FakeResponse(
                        url=ZHIPU_API_URL,
                        payload=_page("zhipu_articles_page2.json"),
                    ),
                ],
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = ZhipuResearchJob(
                {
                    "name": "Zhipu AI Research",
                    "output": "zhipu_research.xml",
                    "title": "Zhipu AI Research",
                    "options": {"page_size": 6, "max_items": 10},
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "zhipu_research.xml").getroot()

        self.assertTrue(result.success)
        titles = [item.findtext("title") for item in root.findall("./channel/item")]
        self.assertEqual(
            titles,
            [
                "GLM-5.3-Flash：前沿智能进入普惠时代",
                "GLM-5.3：前沿编程能力与涌现的网络安全能力",
                "GLM-OCR",
            ],
        )

    @patch("src.jobs.dynamic_site.create_retry_session")
    def test_job_follows_live_page_when_api_fails(self, create_session):
        index_html = (FIXTURES / "zhipu_research_index.html").read_text(
            encoding="utf-8"
        )
        create_session.return_value = FakeSession(
            {
                ZHIPU_RESEARCH_URL: FakeResponse(index_html, ZHIPU_RESEARCH_URL),
                ZHIPU_API_URL: FakeResponse(
                    "", ZHIPU_API_URL, status_code=503
                ),
                "https://www.zhipuai.cn/zh/research/163": FakeResponse(
                    """
                    <html><head>
                      <meta property="og:title" content="GLM-5.3-Flash：前沿智能进入普惠时代" />
                      <meta name="description" content="基座模型" />
                    </head></html>
                    """,
                    "https://www.zhipuai.cn/zh/research/163",
                ),
                "https://www.zhipuai.cn/zh/research/162": FakeResponse(
                    """
                    <html><head>
                      <meta property="og:title" content="GLM-5.3：前沿编程能力与涌现的网络安全能力" />
                    </head></html>
                    """,
                    "https://www.zhipuai.cn/zh/research/162",
                ),
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = ZhipuResearchJob(
                {"name": "Zhipu AI Research", "output": "zhipu_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "zhipu_research.xml").getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(root.findall("./channel/item")), 2)
        self.assertEqual(
            root.findtext("./channel/item/title"),
            "GLM-5.3-Flash：前沿智能进入普惠时代",
        )

    @patch("src.jobs.dynamic_site.create_retry_session")
    def test_dynamic_config_picks_up_new_page_url_not_in_api(self, create_session):
        create_session.return_value = FakeSession(
            {
                ZHIPU_RESEARCH_URL: FakeResponse(
                    '<a href="/zh/research/200">New post</a>',
                    ZHIPU_RESEARCH_URL,
                ),
                ZHIPU_API_URL: FakeResponse(
                    url=ZHIPU_API_URL,
                    payload={
                        "docs": [
                            {
                                "id": 163,
                                "title_zh": "Old post",
                                "category": "blog",
                                "active": True,
                                "createAt": "2026-08-01T00:00:00.000Z",
                            }
                        ],
                        "hasNextPage": False,
                    },
                ),
                "https://www.zhipuai.cn/zh/research/200": FakeResponse(
                    """
                    <html><head>
                      <meta property="og:title" content="Brand new research post" />
                      <script type="application/ld+json">
                        {"@type":"Article","datePublished":"2026-08-28T00:00:00Z"}
                      </script>
                    </head></html>
                    """,
                    "https://www.zhipuai.cn/zh/research/200",
                ),
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = DynamicSiteJob(
                {
                    "name": "Zhipu AI Research",
                    "url": ZHIPU_RESEARCH_URL,
                    "path_prefix": "/zh/research",
                    "allowed_hosts": ["zhipuai.cn"],
                    "api_urls": [ZHIPU_API_URL],
                    "category": "blog",
                    "output": "zhipu_research.xml",
                    "options": {"require_active": True, "minimum_items": 1},
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "zhipu_research.xml").getroot()

        self.assertTrue(result.success)
        titles = [item.findtext("title") for item in root.findall("./channel/item")]
        self.assertEqual(titles, ["Brand new research post", "Old post"])

    @patch("src.jobs.dynamic_site.create_retry_session")
    def test_empty_public_list_fails(self, create_session):
        create_session.return_value = FakeSession(
            {
                ZHIPU_RESEARCH_URL: FakeResponse(
                    "<html><body>No posts</body></html>", ZHIPU_RESEARCH_URL
                ),
                ZHIPU_API_URL: FakeResponse(
                    url=ZHIPU_API_URL,
                    payload={
                        "docs": [
                            {
                                "id": 1,
                                "title_zh": "News",
                                "category": "news",
                                "active": True,
                            }
                        ],
                        "hasNextPage": False,
                    },
                ),
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ZhipuResearchJob(
                {"name": "Zhipu AI Research", "output": "zhipu_research.xml"}
            ).run(JobContext(feeds_dir=Path(temp_dir)))
        self.assertFalse(result.success)
        self.assertIn("未找到任何文章链接", result.details)


if __name__ == "__main__":
    unittest.main()
