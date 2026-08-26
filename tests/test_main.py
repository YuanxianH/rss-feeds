import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main as app_main
from src.jobs.base import JobResult, JobRunReport


def _job_report(**statuses: bool) -> JobRunReport:
    return JobRunReport(
        results={
            name: JobResult(name=name, success=success, details="ok" if success else "failed")
            for name, success in statuses.items()
        }
    )


class MainTests(unittest.TestCase):
    @patch("main.generate_site_index")
    @patch("main.JobRunner")
    def test_run_once_reports_partial_success(self, runner_cls, generate_site_index):
        runner_cls.return_value.run_jobs.return_value = _job_report(job_a=True, job_b=False)
        report = app_main.run_once(
            {"jobs": [{"type": "selector_scrape"}, {"type": "minimax_news"}]},
            "feeds",
        )
        self.assertFalse(report.is_success())
        self.assertTrue(report.is_success(allow_partial=True))
        generate_site_index.assert_called_once()

    @patch("main.generate_site_index")
    @patch("main.JobRunner")
    def test_run_once_reports_total_failure(self, runner_cls, generate_site_index):
        runner_cls.return_value.run_jobs.return_value = _job_report(job_a=False)

        report = app_main.run_once(
            {"jobs": [{"type": "openai_research_filter", "name": "job_a"}]},
            "feeds",
        )
        self.assertFalse(report.is_success())
        self.assertFalse(report.is_success(allow_partial=True))
        generate_site_index.assert_called_once()

    @patch("main.generate_site_index")
    @patch("main.JobRunner")
    def test_run_once_reports_all_jobs_success(self, runner_cls, generate_site_index):
        runner_cls.return_value.run_jobs.return_value = _job_report(job_a=True, job_b=True)
        report = app_main.run_once(
            {"jobs": [{"type": "selector_scrape"}, {"type": "minimax_news"}]},
            "feeds",
        )
        self.assertTrue(report.is_success())
        generate_site_index.assert_called_once()

    @patch("main.generate_site_index", side_effect=RuntimeError("boom"))
    @patch("main.JobRunner")
    def test_run_once_treats_homepage_generation_failure_as_fatal(self, runner_cls, _):
        runner_cls.return_value.run_jobs.return_value = _job_report(job_a=True)
        report = app_main.run_once(
            {"jobs": [{"type": "selector_scrape", "name": "job_a"}]},
            "feeds",
        )
        self.assertFalse(report.is_success(allow_partial=True))
        self.assertEqual(report.index_error, "boom")

    @patch("main.load_config", return_value={"jobs": [{"type": "selector_scrape", "name": "job_a"}]})
    @patch(
        "main.run_once",
        return_value=app_main.RunReport(jobs=_job_report(job_a=False), index_generated=True),
    )
    def test_main_returns_1_when_run_failed(self, _, __):
        code = app_main.main(["-c", "config.yaml"])
        self.assertEqual(code, 1)

    @patch("main.load_config", return_value={"jobs": [{"type": "demo", "name": "good"}]})
    @patch(
        "main.run_once",
        return_value=app_main.RunReport(
            jobs=_job_report(good=True, bad=False),
            index_generated=True,
        ),
    )
    def test_main_allows_partial_success_when_requested(self, _, __):
        code = app_main.main(["-c", "config.yaml", "--allow-partial"])
        self.assertEqual(code, 0)

    def test_github_summary_reports_previous_output_kept(self):
        report = app_main.RunReport(
            jobs=_job_report(good=True, bad=False),
            index_generated=True,
        )
        config = {
            "jobs": [
                {"name": "good", "output": "good.xml"},
                {"name": "bad", "output": "bad.xml"},
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            feeds_dir = Path(temp_dir) / "feeds"
            feeds_dir.mkdir()
            (feeds_dir / "bad.xml").write_text("<rss/>", encoding="utf-8")
            summary_path = Path(temp_dir) / "summary.md"
            with patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": str(summary_path)}):
                app_main._write_github_summary(report, config, str(feeds_dir))
            summary = summary_path.read_text(encoding="utf-8")

        self.assertIn("| bad | Failed | Previous kept | failed |", summary)
        self.assertIn("Result: **partial**", summary)

    @patch("main.JobRunner")
    def test_run_jobs_merges_default_and_job_options(self, runner_cls):
        runner_cls.return_value.run_jobs.return_value = _job_report(demo=True)
        config = {
            "defaults": {
                "options": {
                    "timeout": 20,
                    "retries": 3,
                }
            },
            "jobs": [
                {
                    "type": "dynamic_site",
                    "name": "demo",
                    "options": {"timeout": 30},
                }
            ],
        }

        app_main._run_jobs(config, "feeds")

        submitted = runner_cls.return_value.run_jobs.call_args.args[0]
        self.assertEqual(submitted[0]["options"], {"timeout": 30, "retries": 3})

    def test_main_returns_2_when_config_not_found(self):
        code = app_main.main(["-c", "/tmp/does-not-exist-rss-creator.yaml"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
