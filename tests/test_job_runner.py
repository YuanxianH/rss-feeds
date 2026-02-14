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
            results = runner.run_jobs([{"type": "unknown", "name": "bad job"}])

        self.assertEqual(results, {"bad job": False})

    @patch("src.jobs.runner.create_job")
    def test_run_jobs_collects_job_result(self, create_job):
        fake_job = MagicMock()
        fake_job.name = "demo"
        fake_job.run.return_value = JobResult(name="demo", success=True, details="ok")
        create_job.return_value = fake_job

        with tempfile.TemporaryDirectory() as temp_dir:
            runner = JobRunner(temp_dir)
            results = runner.run_jobs([{"type": "demo"}])

        self.assertEqual(results, {"demo": True})

    @patch("src.jobs.runner.create_job")
    def test_run_jobs_skips_disabled_jobs(self, create_job):
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = JobRunner(temp_dir)
            results = runner.run_jobs([{"type": "demo", "name": "skip me", "enabled": False}])

        self.assertEqual(results, {})
        create_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
