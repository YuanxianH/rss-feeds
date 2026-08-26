"""Unified runner for all config-driven jobs."""

import logging
from pathlib import Path

from .base import JobContext, JobResult, JobRunReport
from .registry import create_job

logger = logging.getLogger(__name__)


class JobRunner:
    """Execute configured jobs and aggregate result status."""

    def __init__(self, feeds_dir: str):
        self.feeds_dir = Path(feeds_dir)
        self.feeds_dir.mkdir(parents=True, exist_ok=True)

    def run_jobs(self, job_configs: list[dict]) -> JobRunReport:
        results: dict[str, JobResult] = {}
        context = JobContext(feeds_dir=self.feeds_dir)

        for config in job_configs:
            if not config.get("enabled", True):
                name = str(config.get("name") or config.get("type") or "未命名")
                logger.info(f"跳过已禁用 job: {name}")
                continue

            fallback_name = str(config.get("name") or config.get("type") or "未命名")
            try:
                job = create_job(config)
            except Exception as exc:
                details = f"job 配置错误 - {exc}"
                logger.error(f"{fallback_name}: {details}")
                results[fallback_name] = JobResult(
                    name=fallback_name,
                    success=False,
                    details=details,
                )
                continue

            try:
                result = job.run(context)
            except Exception as exc:
                details = f"执行异常 - {exc}"
                logger.error(f"{job.name}: {details}")
                results[job.name] = JobResult(
                    name=job.name,
                    success=False,
                    details=details,
                )
                continue

            results[result.name] = result
            if not result.success and result.details:
                logger.error(f"{result.name}: {result.details}")

        if results:
            success_count = sum(1 for result in results.values() if result.success)
            logger.info(f"jobs 完成: {success_count}/{len(results)} 成功")

        return JobRunReport(results=results)
