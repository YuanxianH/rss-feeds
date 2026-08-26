import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.jobs.base import JobResult
from src.jobs.runner import JobRunner


class JobRunnerTests(unittest.TestCase):
    @patch("src.jobs.runner.create_job")
    def test_run_jobs_handles_job_factory_errors(self, create_job):
        create_job.side_effect = ValueError("unknown")
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = JobRunner(temp_dir)
            report = runner.run_jobs([{"type": "unknown", "name": "bad job"}])

        self.assertEqual(report.total, 1)
        self.assertFalse(report.results["bad job"].success)
        self.assertIn("job 配置错误", report.results["bad job"].details)

    @patch("src.jobs.runner.create_job")
    def test_run_jobs_collects_job_result(self, create_job):
        fake_job = MagicMock()
        fake_job.name = "demo"
        fake_job.run.return_value = JobResult(name="demo", success=True, details="ok")
        create_job.return_value = fake_job

        with tempfile.TemporaryDirectory() as temp_dir:
            runner = JobRunner(temp_dir)
            report = runner.run_jobs([{"type": "demo"}])

        self.assertTrue(report.all_succeeded)
        self.assertEqual(report.results["demo"].details, "ok")

    @patch("src.jobs.runner.create_job")
    def test_run_jobs_skips_disabled_jobs(self, create_job):
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = JobRunner(temp_dir)
            report = runner.run_jobs([{"type": "demo", "name": "skip me", "enabled": False}])

        self.assertEqual(report.total, 0)
        create_job.assert_not_called()

    @patch("src.jobs.runner.create_job")
    def test_run_jobs_records_unhandled_job_errors(self, create_job):
        fake_job = MagicMock()
        fake_job.name = "broken"
        fake_job.run.side_effect = RuntimeError("boom")
        create_job.return_value = fake_job

        with tempfile.TemporaryDirectory() as temp_dir:
            report = JobRunner(temp_dir).run_jobs([{"type": "demo"}])

        self.assertFalse(report.any_succeeded)
        self.assertEqual(report.failed[0].name, "broken")
        self.assertIn("执行异常", report.failed[0].details)


if __name__ == "__main__":
    unittest.main()
