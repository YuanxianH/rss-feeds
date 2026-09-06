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
FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "qwen_research_list.json"
QWEN_API_URL = "https://qwen.ai/api/page_config?code=research.research-list"


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


def _fixture() -> list:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class QwenResearchConfigTests(unittest.TestCase):
    def test_config_targets_research_list_api(self):
        job = _qwen_job()
        self.assertEqual(job["type"], "json_list_api")
        self.assertEqual(job["api_url"], QWEN_API_URL)
        self.assertEqual(job["method"], "GET")
        self.assertEqual(job["output"], "qwen_research.xml")
        self.assertEqual(job["link"], "https://qwen.ai/research")
        self.assertEqual(job["catalog"]["section"], "research")
        self.assertEqual(job["fields"]["slug"], ["id"])
        self.assertEqual(
            job["fields"]["url_template"], "https://qwen.ai/blog?id={slug}"
        )
        self.assertEqual(job["fields"]["description"], ["description", "introduction"])
        self.assertEqual(job["options"]["max_pages"], 1)
        self.assertEqual(job["options"]["sort"], "date_desc")


class QwenResearchJobTests(unittest.TestCase):
    @patch("src.jobs.json_list_api.create_retry_session")
    def test_job_writes_rss_from_root_array_newest_first(self, create_session):
        session = FakeSession(
            [FakeResponse(_fixture(), QWEN_API_URL)]
        )
        create_session.return_value = session
        job = _qwen_job()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = JsonListApiJob(job).run(JobContext(feeds_dir=Path(temp_dir)))
            root = ET.parse(Path(temp_dir) / "qwen_research.xml").getroot()

        self.assertTrue(result.success)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["method"], "GET")
        self.assertEqual(session.calls[0]["url"], QWEN_API_URL)
        items = root.findall("./channel/item")
        self.assertEqual(
            [item.findtext("title") for item in items],
            [
                "GSPO: Towards Scalable Reinforcement Learning for Language Models",
                "Code with CodeQwen1.5",
                "Chinese CLIP: Contrastive Vision-Language Pretraining in Chinese",
            ],
        )
        self.assertEqual(
            [item.findtext("link") for item in items],
            [
                "https://qwen.ai/blog?id=gspo",
                "https://qwen.ai/blog?id=codeqwen1.5",
                "https://qwen.ai/blog?id=chinese-clip",
            ],
        )
        self.assertIn(
            "Reinforcement Learning has emerged as a pivotal paradigm",
            items[0].findtext("description") or "",
        )
        self.assertTrue((items[0].findtext("pubDate") or "").startswith("Sun, 27 Jul 2025"))

    @patch("src.jobs.json_list_api.create_retry_session")
    def test_empty_array_fails(self, create_session):
        create_session.return_value = FakeSession(
            [FakeResponse([], QWEN_API_URL)]
        )
        job = _qwen_job()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = JsonListApiJob(job).run(JobContext(feeds_dir=Path(temp_dir)))

        self.assertFalse(result.success)
        self.assertIn("未找到", result.details)
