import unittest
from unittest.mock import patch

import main as app_main


class MainTests(unittest.TestCase):
    @patch("main.generate_site_index")
    @patch("main.JobRunner")
    def test_run_once_returns_false_when_any_job_fails(self, runner_cls, generate_site_index):
        runner_cls.return_value.run_jobs.return_value = {"job_a": True, "job_b": False}
        ok = app_main.run_once({"jobs": [{"type": "selector_scrape"}, {"type": "minimax_news"}]}, "feeds")
        self.assertFalse(ok)
        generate_site_index.assert_called_once()

    @patch("main.generate_site_index")
    @patch("main.JobRunner")
    def test_run_once_returns_false_when_extension_job_fails(self, runner_cls, generate_site_index):
        runner_cls.return_value.run_jobs.return_value = {"job_a": False}

        ok = app_main.run_once(
            {"jobs": [{"type": "openai_research_filter", "name": "job_a"}]},
            "feeds",
        )
        self.assertFalse(ok)
        generate_site_index.assert_called_once()

    @patch("main.generate_site_index")
    @patch("main.JobRunner")
    def test_run_once_returns_true_when_all_jobs_success(self, runner_cls, generate_site_index):
        runner_cls.return_value.run_jobs.return_value = {"job_a": True, "job_b": True}
        ok = app_main.run_once({"jobs": [{"type": "selector_scrape"}, {"type": "minimax_news"}]}, "feeds")
        self.assertTrue(ok)
        generate_site_index.assert_called_once()

    @patch("main.generate_site_index", side_effect=RuntimeError("boom"))
    @patch("main.JobRunner")
    def test_run_once_ignores_homepage_generation_failures(self, runner_cls, _):
        runner_cls.return_value.run_jobs.return_value = {"job_a": True}
        ok = app_main.run_once({"jobs": [{"type": "selector_scrape", "name": "job_a"}]}, "feeds")
        self.assertTrue(ok)

    @patch("main.load_config", return_value={"jobs": [{"type": "selector_scrape", "name": "job_a"}]})
    @patch("main.run_once", return_value=False)
    def test_main_returns_1_when_run_once_failed(self, _, __):
        code = app_main.main(["-c", "config.yaml"])
        self.assertEqual(code, 1)

    def test_main_returns_2_when_config_not_found(self):
        code = app_main.main(["-c", "/tmp/does-not-exist-rss-creator.yaml"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
