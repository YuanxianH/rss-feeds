"""Generic selector-based scraping job."""

import logging

from src.feed_creator import FeedCreator

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

logger = logging.getLogger(__name__)


@register_job
class SelectorScrapeJob(FeedJob):
    """Build RSS by scraping a page with CSS selectors."""

    job_type = "selector_scrape"

    def run(self, context: JobContext) -> JobResult:
        creator = FeedCreator(feeds_dir=str(context.feeds_dir))
        success = creator.create_feed(self.config)
        details = f"输出: {self.config.get('output', f'{self.name}.xml')}" if success else "抓取或生成失败"
        return JobResult(name=self.name, success=success, details=details)
