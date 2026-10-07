import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from src.jobs.base import JobContext
from src.jobs.xai_changelog import (
    XaiChangelogJob,
    changelog_entry_url,
    extract_xai_changelog_items,
)
from src.scraper import WebScraper

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "xai_changelog.html"
BOT_URL = "https://x.ai/changelog/bot"
BUILD_URL = "https://x.ai/changelog/build"


def _jobs_by_output() -> dict[str, dict]:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    return {
        job.get("output"): job
        for job in config.get("jobs") or []
        if str(job.get("output", "")).startswith("grok_")
    }


class XaiChangelogTests(unittest.TestCase):
    def test_changelog_entry_url_normalizes_page_and_fragment(self):
        self.assertEqual(
            changelog_entry_url(BOT_URL, "v0.66.0"),
            "https://x.ai/changelog/bot#v0.66.0",
        )
        self.assertEqual(
            changelog_entry_url(f"{BOT_URL}/#old", "#v0.66.0"),
            "https://x.ai/changelog/bot#v0.66.0",
        )
        self.assertEqual(
            changelog_entry_url(f"{BUILD_URL}/", "v1.0.46-2026-09-30"),
            "https://x.ai/changelog/build#v1.0.46-2026-09-30",
        )
        self.assertEqual(changelog_entry_url(BOT_URL, ""), BOT_URL)

    def test_fixture_discovers_version_blocks_and_skips_incomplete_ones(self):
        items = extract_xai_changelog_items(
            FIXTURE.read_text(encoding="utf-8"),
            f"{BOT_URL}#ignored",
            max_items=10,
        )

        self.assertEqual(
            [(item["title"], item["link"], item["pubDate"]) for item in items],
            [
                (
                    "Main Bot and more reliable updates (0.66.0)",
                    "https://x.ai/changelog/bot#v0.66.0",
                    "2026-10-02",
                ),
                (
                    "Grok Build 1.0.46",
                    "https://x.ai/changelog/bot#v1.0.46-2026-09-30",
                    "2026-09-30",
                ),
            ],
        )
        self.assertEqual(items[0]["guid"], items[0]["link"])
        self.assertEqual(
            items[0]["description"],
            "New\nChoose a primary Bot, marked Main Bot.\nFixed\nUpdate downloads resume after sleep.",
        )
        self.assertNotIn("October 2, 2026", items[0]["description"])
        self.assertIn("grok inspect", items[1]["description"])
        self.assertNotIn("must be skipped", "\n".join(item.get("description", "") for item in items))

    def test_empty_page_returns_no_items(self):
        self.assertEqual(extract_xai_changelog_items("", BOT_URL), [])
        self.assertEqual(
            extract_xai_changelog_items("<html><body><p>No releases</p></body></html>", BUILD_URL),
            [],
        )

    def test_config_registers_both_release_feeds(self):
        jobs = _jobs_by_output()
        self.assertEqual(set(jobs), {"grok_bot_changelog.xml", "grok_build_changelog.xml"})

        bot = jobs["grok_bot_changelog.xml"]
        build = jobs["grok_build_changelog.xml"]
        self.assertEqual(bot["type"], "xai_changelog")
        self.assertEqual(bot["url"], BOT_URL)
        self.assertEqual(bot["link"], BOT_URL)
        self.assertEqual(bot["catalog"]["section"], "releases")
        self.assertEqual(bot["options"]["impersonate"], "chrome")
        self.assertEqual(build["type"], "xai_changelog")
        self.assertEqual(build["url"], BUILD_URL)
        self.assertEqual(build["catalog"]["section"], "releases")
        self.assertEqual(build["options"]["impersonate"], "chrome")

    @patch("src.jobs.xai_changelog.WebScraper")
    def test_job_generates_rss_with_chrome_impersonation(self, scraper_cls):
        scraper_cls.return_value.fetch.return_value = FIXTURE.read_text(encoding="utf-8")
        config = _jobs_by_output()["grok_bot_changelog.xml"]

        with tempfile.TemporaryDirectory() as temp_dir:
            result = XaiChangelogJob(config).run(JobContext(feeds_dir=Path(temp_dir)))
            output_path = Path(temp_dir) / "grok_bot_changelog.xml"
            xml = output_path.read_text(encoding="utf-8")

        self.assertTrue(result.success)
        self.assertIn("2 条", result.details)
        scraper_cls.assert_called_once()
        self.assertEqual(scraper_cls.call_args.kwargs["impersonate"], "chrome")
        self.assertIn("Main Bot and more reliable updates (0.66.0)", xml)
        self.assertIn("https://x.ai/changelog/bot#v0.66.0", xml)
        self.assertLess(
            xml.index("Main Bot and more reliable updates (0.66.0)"),
            xml.index("Grok Build 1.0.46"),
        )

    @patch("src.jobs.xai_changelog.WebScraper.fetch")
    def test_same_day_versions_keep_page_order(self, fetch):
        fetch.return_value = """
        <article>
          <time datetime="2026-09-30"></time>
          <div>
            <h2 id="v0.65.0">Voice chat</h2>
            <ul><li>Newer same-day notes.</li></ul>
          </div>
        </article>
        <article>
          <time datetime="2026-09-30"></time>
          <div>
            <h2 id="v0.64.0">Managers</h2>
            <ul><li>Older same-day notes.</li></ul>
          </div>
        </article>
        """
        config = {
            "type": "xai_changelog",
            "name": "Grok Bot Changelog",
            "url": BOT_URL,
            "output": "grok_bot_changelog.xml",
            "options": {"impersonate": "chrome"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            result = XaiChangelogJob(config).run(JobContext(feeds_dir=Path(temp_dir)))
            xml = (Path(temp_dir) / "grok_bot_changelog.xml").read_text(encoding="utf-8")

        self.assertTrue(result.success)
        self.assertLess(xml.index("Voice chat (0.65.0)"), xml.index("Managers (0.64.0)"))

    @patch("src.jobs.xai_changelog.WebScraper.fetch", return_value=None)
    def test_job_fails_when_fetch_returns_nothing(self, _fetch):
        config = _jobs_by_output()["grok_build_changelog.xml"]
        with tempfile.TemporaryDirectory() as temp_dir:
            result = XaiChangelogJob(config).run(JobContext(feeds_dir=Path(temp_dir)))

        self.assertFalse(result.success)
        self.assertIn("抓取 changelog 页面失败", result.details)

    @patch("src.jobs.xai_changelog.WebScraper.fetch", return_value="<html></html>")
    def test_job_fails_when_page_has_no_versions(self, _fetch):
        config = _jobs_by_output()["grok_build_changelog.xml"]
        with tempfile.TemporaryDirectory() as temp_dir:
            result = XaiChangelogJob(config).run(JobContext(feeds_dir=Path(temp_dir)))

        self.assertFalse(result.success)
        self.assertIn("未解析到 changelog 版本条目", result.details)


class ImpersonatedFetchTests(unittest.TestCase):
    @patch("src.scraper.impersonated_get")
    def test_impersonated_fetch_retries_then_returns_html(self, impersonated_get):
        class _Response:
            status_code = 200
            text = "<html>ok</html>"

            def raise_for_status(self):
                return None

        impersonated_get.side_effect = [RuntimeError("403"), _Response()]
        scraper = WebScraper(timeout=5, retries=1, backoff_factor=0, impersonate="chrome")

        self.assertEqual(scraper.fetch(BOT_URL), "<html>ok</html>")
        self.assertEqual(impersonated_get.call_count, 2)
        self.assertEqual(impersonated_get.call_args.kwargs["impersonate"], "chrome")

    @patch("src.scraper.impersonated_get", side_effect=ImportError("curl_cffi"))
    def test_impersonated_fetch_fails_closed_without_curl_cffi(self, _impersonated_get):
        scraper = WebScraper(timeout=5, retries=2, backoff_factor=0, impersonate="chrome")
        self.assertIsNone(scraper.fetch(BOT_URL))


if __name__ == "__main__":
    unittest.main()
