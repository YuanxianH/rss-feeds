"""OpenAI RSS filter job."""

import argparse
import logging
from pathlib import Path
from typing import Optional

from src.path_utils import resolve_output_path
from src.rss_filter import RSSFilter
from src.runtime import setup_logging

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

DEFAULT_SOURCE_URL = "https://openai.com/news/rss.xml"
DEFAULT_OUTPUT_FILENAME = "openai_research_only.xml"
DEFAULT_CATEGORIES = ["Research", "research", "Science", "science"]

logger = logging.getLogger(__name__)
DEFAULT_FEEDS_DIR = Path(__file__).resolve().parents[2] / "feeds"


@register_job
class OpenAIResearchFilterJob(FeedJob):
    job_type = "openai_research_filter"

    def run(self, context: JobContext) -> JobResult:
        source_url = self.config.get("source_url", DEFAULT_SOURCE_URL)
        output_file = self.config.get("output", DEFAULT_OUTPUT_FILENAME)
        categories = [str(item) for item in self.config.get("categories", DEFAULT_CATEGORIES)]
        options = self.config.get("options", {})

        output_path = resolve_output_path(context.feeds_dir, output_file)
        logger.info(f"开始过滤 OpenAI RSS（分类: {', '.join(categories)}）")

        filter_tool = RSSFilter(
            source_url,
            timeout=int(options.get("timeout", 15)),
            retries=int(options.get("retries", 2)),
            user_agent=options.get("user_agent"),
        )
        success = filter_tool.filter_by_category(
            categories=categories,
            output_path=str(output_path),
            title=self.config.get("title", "OpenAI Research Only"),
            description=self.config.get("description", "OpenAI 官方 RSS - 仅研究内容"),
        )
        details = f"输出: {output_path}" if success else "过滤失败"
        return JobResult(name=self.name, success=success, details=details)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Filter OpenAI RSS to research-only entries")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_FILENAME, help="Output RSS filename")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    job = OpenAIResearchFilterJob({"name": "OpenAI Research", "output": args.output})
    result = job.run(JobContext(feeds_dir=DEFAULT_FEEDS_DIR))
    return 0 if result.success else 1
