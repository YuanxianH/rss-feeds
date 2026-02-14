"""Waymo Blog Technology job."""

import argparse
import logging
from pathlib import Path
from typing import Optional

import requests

from src.http_client import create_retry_session
from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator
from src.runtime import setup_logging

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

DEFAULT_API_URL = "https://waymo.com/api/blog/posts"
DEFAULT_BASE_URL = "https://waymo.com"
DEFAULT_TAG = "Technology"
DEFAULT_OUTPUT_FILENAME = "waymo_blog_tech.xml"
DEFAULT_MAX_ITEMS = 50

logger = logging.getLogger(__name__)
DEFAULT_FEEDS_DIR = Path(__file__).resolve().parents[2] / "feeds"


@register_job
class WaymoBlogTechnologyJob(FeedJob):
    job_type = "waymo_blog_technology"

    def run(self, context: JobContext) -> JobResult:
        options = self.config.get("options", {})
        api_url = self.config.get("api_url", DEFAULT_API_URL)
        base_url = self.config.get("base_url", DEFAULT_BASE_URL)
        tag = self.config.get("tag", DEFAULT_TAG)
        max_items = int(options.get("max_items", DEFAULT_MAX_ITEMS))
        output_file = self.config.get("output", DEFAULT_OUTPUT_FILENAME)

        output_path = resolve_output_path(context.feeds_dir, output_file)
        logger.info("正在从 Waymo Blog API 获取文章...")

        session = create_retry_session(
            user_agent=options.get("user_agent"),
            accept="application/json",
            retries=int(options.get("retries", 2)),
            backoff_factor=float(options.get("backoff_factor", 0.5)),
        )

        try:
            response = session.get(api_url, timeout=int(options.get("timeout", 15)))
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            return JobResult(name=self.name, success=False, details=f"调用 Waymo API 失败: {exc}")
        except ValueError as exc:
            return JobResult(name=self.name, success=False, details=f"Waymo API 返回非法 JSON: {exc}")

        posts = payload.get("posts", [])
        logger.info(f"Waymo API 返回 {len(posts)} 篇文章")

        tech_posts = [post for post in posts if tag in post.get("tags", [])]
        tech_posts.sort(key=lambda post: post.get("date", ""), reverse=True)
        logger.info(f"过滤后 {len(tech_posts)} 篇 {tag} 文章")

        latest_posts = tech_posts[:max_items]
        latest_posts.reverse()

        items = []
        for post in latest_posts:
            url = post.get("url", "")
            if url and not url.startswith("http"):
                url = base_url + url

            items.append(
                {
                    "title": post.get("title", ""),
                    "link": url,
                    "description": post.get("summary", ""),
                    "pubDate": post.get("date", ""),
                    "author": post.get("author", ""),
                }
            )

        if not items:
            return JobResult(name=self.name, success=False, details=f"未找到任何 {tag} 文章")

        generator = RSSGenerator(
            title=self.config.get("title", "Waymo Blog - Technology"),
            link=self.config.get("link", "https://waymo.com/blog/search/?t=Technology"),
            description=self.config.get("description", "Waymo Blog Technology 分类文章"),
        )
        generator.add_items(items)
        success = generator.generate(str(output_path))
        details = f"输出: {output_path}" if success else "RSS 生成失败"
        return JobResult(name=self.name, success=success, details=details)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Waymo Blog Technology posts and generate RSS")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS, help="Maximum feed items")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_FILENAME, help="Output RSS filename")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    job = WaymoBlogTechnologyJob(
        {
            "name": "Waymo Blog Technology",
            "output": args.output,
            "options": {"max_items": args.max_items},
        }
    )
    result = job.run(JobContext(feeds_dir=DEFAULT_FEEDS_DIR))
    return 0 if result.success else 1
