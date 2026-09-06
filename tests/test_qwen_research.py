import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import requests
import yaml

from src.jobs.base import JobContext
from src.jobs.json_list_api import JsonListApiJob

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "qwen_article_retrieval.json"
QWEN_API_URL = (
    "https://qwen.ai/api/v2/article/retrieval?type=qwen_ai&language=en-US"
)


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


def _qwen_job() -> dict:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    for job in config.get("jobs") or []:
        if job.get("name") == "Qwen Research Index":
            return job
    raise AssertionError("Qwen Research Index job missing from config.yaml")


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class QwenResearchConfigTests(unittest.TestCase):
    def test_config_targets_article_retrieval_api(self):
        job = _qwen_job()
        self.assertEqual(job["type"], "json_list_api")
        self.assertEqual(job["api_url"], QWEN_API_URL)
        self.assertEqual(job["method"], "GET")
        self.assertEqual(job["output"], "qwen_research.xml")
        self.assertEqual(job["link"], "https://qwen.ai/research")
        self.assertEqual(job["catalog"]["section"], "research")
        self.assertEqual(job["fields"]["list"], "data.articles")
        self.assertEqual(job["fields"]["slug"], ["path"])
        self.assertEqual(
            job["fields"]["url_template"], "https://qwen.ai/blog?id={slug}"
        )
        self.assertEqual(
            job["fields"]["description"],
            ["extra.description", "extra.introduction"],
        )
        self.assertEqual(job["fields"]["date"], ["extra.date"])
        self.assertEqual(job["options"]["max_pages"], 1)
        self.assertEqual(job["options"]["sort"], "date_desc")


class QwenResearchJobTests(unittest.TestCase):
    @patch("src.jobs.json_list_api.create_retry_session")
    def test_job_writes_latest_retrieval_items_first(self, create_session):
        session = FakeSession([FakeResponse(_fixture(), QWEN_API_URL)])
        create_session.return_value = session
        job = _qwen_job()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = JsonListApiJob(job).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "qwen_research.xml").getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["url"], QWEN_API_URL)
        items = root.findall("./channel/item")
        self.assertEqual(
            [item.findtext("title") for item in items],
            [
                "E-Commerce Bench: Long-Horizon Operations, Multi-Dimensional Evaluation",
                "Qwen-Drive-1.0: An Initial Step towards a Vision-Language Foundation Model for Autonomous Driving",
                "Qwen3.8-Flash-Next: A New Architecture, Towards Ultimate Cost-Efficiency",
            ],
        )
        self.assertEqual(
            [item.findtext("link") for item in items],
            [
                "https://qwen.ai/blog?id=e-commerce-bench",
                "https://qwen.ai/blog?id=qwen-drive-1.0",
                "https://qwen.ai/blog?id=qwen3.8-flash-next",
            ],
        )
        self.assertIn("Agent benchmarks", items[0].findtext("description") or "")
        self.assertIn("Qwen-Drive-1.0", items[1].findtext("description") or "")
        self.assertIn("Qwen3.8-Flash-Next", items[2].findtext("description") or "")
        self.assertTrue(
            (items[0].findtext("pubDate") or "").startswith("Thu, 03 Sep 2026")
        )
        self.assertTrue(
            (items[2].findtext("pubDate") or "").startswith("Wed, 26 Aug 2026")
        )

    @patch("src.jobs.json_list_api.create_retry_session")
    def test_empty_articles_fails(self, create_session):
        create_session.return_value = FakeSession(
            [FakeResponse({"success": True, "data": {"articles": []}}, QWEN_API_URL)]
        )
        job = _qwen_job()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = JsonListApiJob(job).run(JobContext(feeds_dir=Path(temp_dir)))

        self.assertFalse(result.success)
        self.assertIn("未找到", result.details)
