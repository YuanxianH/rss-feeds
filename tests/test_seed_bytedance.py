import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests

from src.jobs.base import JobContext
from src.jobs.registry import create_job
from src.jobs.seed_bytedance import (
    DEFAULT_API_URL,
    DEFAULT_BASE_URL,
    SeedBytedanceJob,
    article_link,
    article_to_item,
    collect_items,
    extract_article_rows,
    extract_router_articles,
    infer_collection,
    localized_field,
    publish_date,
    resolve_collection,
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

    def get(self, url: str, params=None, headers=None, timeout: float = 0):
        self.calls.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        if not self.responses:
            raise requests.HTTPError("unexpected extra request")
        return self.responses.pop(0)


def _page(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class SeedHelperTests(unittest.TestCase):
    def test_article_link_encodes_chinese_slug(self):
        slug = "seedrealtime-音视频全双工大模型发布-走向全模态自然交互"
        self.assertEqual(
            article_link(DEFAULT_BASE_URL, "zh", "blog", slug),
            f"https://seed.bytedance.com/zh/blog/{quote(slug, safe='')}",
        )
        self.assertEqual(
            article_link(
                DEFAULT_BASE_URL,
                "zh",
                "public_papers",
                "edgebench-unveiling-scaling-laws-of-learning-from-real-world-environments",
            ),
            "https://seed.bytedance.com/zh/public_papers/edgebench-unveiling-scaling-laws-of-learning-from-real-world-environments",
        )
        self.assertIsNone(article_link(DEFAULT_BASE_URL, "zh", "blog", ""))

    def test_localized_field_prefers_zh_then_en(self):
        article = _page("seed_blog_list.json")["sub_article_list"][0]
        self.assertEqual(
            localized_field(article, "Title", "zh"),
            "SeedRealtime 音视频全双工大模型发布：走向全模态自然交互",
        )
        paper = _page("seed_papers_list.json")["sub_article_list"][0]
        self.assertEqual(
            localized_field(paper, "Title", "zh"),
            "EdgeBench: Unveiling Scaling Laws of Learning from Real-World Environments",
        )

    def test_publish_date_uses_shanghai_calendar_day(self):
        self.assertEqual(publish_date(1785859200000), "2026-08-05T00:00:00+08:00")
        self.assertEqual(publish_date(1783267200000), "2026-07-06T00:00:00+08:00")
        self.assertIsNone(publish_date(""))
        self.assertIsNone(publish_date(0))

    def test_article_to_item_uses_zh_slug_and_article_id_guid(self):
        item = article_to_item(
            _page("seed_blog_list.json")["sub_article_list"][0],
            locale="zh",
            base_url=DEFAULT_BASE_URL,
            item_path="blog",
        )
        slug = quote("seedrealtime-音视频全双工大模型发布-走向全模态自然交互", safe="")
        self.assertEqual(
            item,
            {
                "title": "SeedRealtime 音视频全双工大模型发布：走向全模态自然交互",
                "link": f"https://seed.bytedance.com/zh/blog/{slug}",
                "guid": "1785893583524",
                "description": "作为原生音视频全双工大模型，联合理解声音、画面与时序信息",
                "pubDate": "2026-08-05T00:00:00+08:00",
            },
        )

    def test_article_to_item_appends_paper_external_links(self):
        item = article_to_item(
            _page("seed_papers_list.json")["sub_article_list"][0],
            locale="zh",
            base_url=DEFAULT_BASE_URL,
            item_path="public_papers",
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(
            item["link"],
            "https://seed.bytedance.com/zh/public_papers/edgebench-unveiling-scaling-laws-of-learning-from-real-world-environments",
        )
        self.assertIn("Pretraining scaling laws", item["description"])
        self.assertIn("arXiv: https://arxiv.org/pdf/2607.05155", item["description"])
        self.assertIn(
            "GitHub: https://github.com/bytedance-seed/EdgeBench",
            item["description"],
        )

    def test_infer_collection_from_live_list_urls(self):
        self.assertEqual(
            infer_collection("https://seed.bytedance.com/zh/blog?order_desc=true&offset=12"),
            ("zh", "blog", 2),
        )
        self.assertEqual(
            infer_collection(
                "https://seed.bytedance.com/zh/public_papers?view_from=research&order_desc=true"
            ),
            ("zh", "public_papers", 1),
        )
        self.assertEqual(
            infer_collection("https://seed.bytedance.com/en/blog"),
            ("en", "blog", 2),
        )
        self.assertIsNone(infer_collection("https://seed.bytedance.com/zh/career"))

    def test_resolve_collection_from_url_without_article_type(self):
        self.assertEqual(
            resolve_collection({"url": "https://seed.bytedance.com/zh/blog?order_desc=true"}),
            ("zh", "blog", 2),
        )

    def test_extract_rows_from_router_data_and_api_keys(self):
        router_rows = extract_article_rows(
            {
                "loaderData": {
                    "(locale$)/blog/page": {
                        "article_list": _page("seed_blog_list.json")["sub_article_list"]
                    }
                }
            }
        )
        self.assertEqual(len(router_rows), 4)
        self.assertEqual(
            extract_article_rows(_page("seed_blog_list.json"))[0]["ArticleMeta"]["ArticleID"],
            1785893583524,
        )

    def test_extract_router_articles_from_list_html(self):
        html = (FIXTURES / "seed_blog_ssr.html").read_text(encoding="utf-8")
        rows = extract_router_articles(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ArticleSubContentZh"]["Title"], "页面更新后的新博客")

    def test_collect_items_skips_incomplete_rows(self):
        items = collect_items(
            _page("seed_blog_list.json")["sub_article_list"],
            locale="zh",
            base_url=DEFAULT_BASE_URL,
            item_path="blog",
            seen_ids=set(),
            limit=10,
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["guid"], "1785893583524")
        self.assertEqual(items[1]["guid"], "1785461671473")


class SeedBytedanceJobTests(unittest.TestCase):
    def test_registry_creates_seed_job(self):
        job = create_job(
            {"type": "seed_bytedance", "name": "ByteDance Seed Blog", "article_type": 2}
        )
        self.assertIsInstance(job, SeedBytedanceJob)
        self.assertEqual(job.job_type, "seed_bytedance")

    def test_missing_collection_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = SeedBytedanceJob({"name": "Seed"}).run(
                JobContext(feeds_dir=Path(temp_dir))
            )
        self.assertFalse(result.success)
        self.assertIn("url", result.details)

    @patch("src.jobs.seed_bytedance.create_retry_session")
    def test_blog_job_paginates_and_deduplicates(self, create_session):
        session = FakeSession(
            [
                FakeResponse(_page("seed_blog_list.json"), DEFAULT_API_URL),
                FakeResponse(_page("seed_blog_list_page2.json"), DEFAULT_API_URL),
            ]
        )
        create_session.return_value = session

        with tempfile.TemporaryDirectory() as temp_dir:
            result = SeedBytedanceJob(
                {
                    "name": "ByteDance Seed Blog",
                    "article_type": 2,
                    "output": "seed_blog.xml",
                    "title": "ByteDance Seed Blog",
                    "link": "https://seed.bytedance.com/zh/blog",
                    "options": {"page_size": 20, "max_items": 10},
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "seed_blog.xml").getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0]["params"]["article_type"], 2)
        self.assertEqual(session.calls[0]["params"]["page_token"], "0")
        self.assertEqual(session.calls[1]["params"]["page_token"], "20")
        self.assertIsNone(session.calls[0]["headers"])
        titles = [item.findtext("title") for item in root.findall("./channel/item")]
        self.assertEqual(
            titles,
            [
                "SeedRealtime 音视频全双工大模型发布：走向全模态自然交互",
                "一镜成片，随心参考｜Seedance 2.5 正式发布",
                "Seed2.1 正式发布，深入 AI 生产力",
            ],
        )
        self.assertEqual(
            root.findtext("./channel/item/guid"),
            "1785893583524",
        )
        self.assertTrue(
            root.findtext("./channel/item/pubDate", "").endswith("2026")
            or "05 Aug 2026" in root.findtext("./channel/item/pubDate", "")
        )

    @patch("src.jobs.seed_bytedance.create_retry_session")
    def test_papers_job_sends_us_locale_header(self, create_session):
        session = FakeSession(
            [FakeResponse(_page("seed_papers_list.json"), DEFAULT_API_URL)]
        )
        create_session.return_value = session

        with tempfile.TemporaryDirectory() as temp_dir:
            result = SeedBytedanceJob(
                {
                    "name": "ByteDance Seed Papers",
                    "article_type": 1,
                    "output": "seed_papers.xml",
                    "title": "ByteDance Seed Public Papers",
                    "link": "https://seed.bytedance.com/zh/public_papers",
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "seed_papers.xml").getroot()

        self.assertTrue(result.success)
        self.assertEqual(session.calls[0]["params"]["article_type"], 1)
        self.assertEqual(session.calls[0]["headers"], {"x-tt-locale": "US"})
        item = root.find("./channel/item")
        self.assertEqual(
            item.findtext("title"),
            "EdgeBench: Unveiling Scaling Laws of Learning from Real-World Environments",
        )
        self.assertIn("arxiv.org/pdf/2607.05155", item.findtext("description"))

    @patch("src.jobs.seed_bytedance.create_retry_session")
    def test_later_page_failure_keeps_first_page(self, create_session):
        create_session.return_value = FakeSession(
            [
                FakeResponse(_page("seed_blog_list.json"), DEFAULT_API_URL),
                FakeResponse({}, DEFAULT_API_URL, status_code=503),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = SeedBytedanceJob(
                {
                    "name": "ByteDance Seed Blog",
                    "article_type": 2,
                    "output": "seed_blog.xml",
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "seed_blog.xml").getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(root.findall("./channel/item")), 2)

    @patch("src.jobs.seed_bytedance.create_retry_session")
    def test_empty_list_fails(self, create_session):
        create_session.return_value = FakeSession(
            [
                FakeResponse(
                    {"sub_article_list": [], "has_more": False, "total": 0},
                    DEFAULT_API_URL,
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = SeedBytedanceJob(
                {
                    "name": "ByteDance Seed Blog",
                    "article_type": 2,
                    "output": "seed_blog.xml",
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
        self.assertFalse(result.success)
        self.assertIn("未找到任何 Seed 条目", result.details)

    @patch("src.jobs.seed_bytedance.create_retry_session")
    def test_api_http_error_fails(self, create_session):
        create_session.return_value = FakeSession(
            [FakeResponse({}, DEFAULT_API_URL, status_code=503)]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = SeedBytedanceJob(
                {
                    "name": "ByteDance Seed Blog",
                    "article_type": 2,
                    "output": "seed_blog.xml",
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
        self.assertFalse(result.success)
        self.assertIn("调用 Seed API 失败", result.details)

    @patch("src.jobs.seed_bytedance.create_retry_session")
    def test_url_only_config_uses_inferred_blog_type(self, create_session):
        payload = _page("seed_blog_list.json")
        payload["has_more"] = False
        session = FakeSession(
            [FakeResponse(payload, DEFAULT_API_URL)]
        )
        create_session.return_value = session
        with tempfile.TemporaryDirectory() as temp_dir:
            result = SeedBytedanceJob(
                {
                    "name": "ByteDance Seed Blog",
                    "url": "https://seed.bytedance.com/zh/blog?order_desc=true",
                    "output": "seed_blog.xml",
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "seed_blog.xml").getroot()
        self.assertTrue(result.success)
        self.assertEqual(session.calls[0]["params"]["article_type"], 2)
        self.assertEqual(len(root.findall("./channel/item")), 2)

    @patch("src.jobs.seed_bytedance.create_retry_session")
    def test_list_page_ssr_fallback_when_api_fails(self, create_session):
        html = (FIXTURES / "seed_blog_ssr.html").read_text(encoding="utf-8")
        session = FakeSession(
            [
                FakeResponse({}, DEFAULT_API_URL, status_code=503),
                FakeResponse(html, "https://seed.bytedance.com/zh/blog"),
            ]
        )
        create_session.return_value = session
        with tempfile.TemporaryDirectory() as temp_dir:
            result = SeedBytedanceJob(
                {
                    "name": "ByteDance Seed Blog",
                    "url": "https://seed.bytedance.com/zh/blog?order_desc=true",
                    "output": "seed_blog.xml",
                }
            ).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "seed_blog.xml").getroot()
        self.assertTrue(result.success)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1]["url"], "https://seed.bytedance.com/zh/blog?order_desc=true")
        self.assertEqual(root.findtext("./channel/item/title"), "页面更新后的新博客")


if __name__ == "__main__":
    unittest.main()
