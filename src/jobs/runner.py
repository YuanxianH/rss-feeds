"""Unified runner for all config-driven jobs."""

import logging
from pathlib import Path
from typing import Dict

# Ensure built-in jobs are registered even when importing runner directly.
from . import minimax_news as _minimax_news  # noqa: F401
from . import minimax_releases as _minimax_releases  # noqa: F401
from . import openai_research as _openai_research  # noqa: F401
from . import selector_scrape as _selector_scrape  # noqa: F401
from . import waymo_blog as _waymo_blog  # noqa: F401
from .base import JobContext
from .registry import create_job

logger = logging.getLogger(__name__)


class JobRunner:
    """Execute configured jobs and aggregate result status."""

    def __init__(self, feeds_dir: str):
        self.feeds_dir = Path(feeds_dir)
        self.feeds_dir.mkdir(parents=True, exist_ok=True)

    def run_jobs(self, job_configs: list[dict]) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
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
                logger.error(f"{fallback_name}: job 配置错误 - {exc}")
                results[fallback_name] = False
                continue

            try:
                result = job.run(context)
            except Exception as exc:
                logger.error(f"{job.name}: 执行异常 - {exc}")
                results[job.name] = False
                continue

            results[result.name] = result.success
            if not result.success and result.details:
                logger.error(f"{result.name}: {result.details}")

        if results:
            success_count = sum(1 for ok in results.values() if ok)
            logger.info(f"jobs 完成: {success_count}/{len(results)} 成功")

        return results
