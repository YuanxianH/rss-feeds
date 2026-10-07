"""xAI product changelog RSS job.

Grok Bot and Grok Build publish version blocks on one page. Each block is an
``article`` with a dated sidebar and an ``h2`` anchor, and the notes live in
that block instead of a separate article URL.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator, items_oldest_first
from src.scraper import WebScraper

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITEMS = 300
DEFAULT_IMPERSONATE = "chrome"
_VERSION_ID = re.compile(r"^v(\d+(?:\.\d+)+)(?:-\d{4}-\d{2}-\d{2})?$")


def changelog_entry_url(page_url: str, anchor_id: str) -> str:
    """Build the stable item link: changelog page URL plus heading fragment."""
    parts = urlsplit((page_url or "").strip())
    path = parts.path.rstrip("/")
    if not path:
        path = "/"
    base = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    anchor = (anchor_id or "").strip().lstrip("#")
    if not anchor:
        return base
    return f"{base}#{anchor}"


def extract_xai_changelog_items(
    html: str,
    page_url: str,
    *,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> list[dict[str, str]]:
    """Extract version entries from an x.ai changelog page.

    Entries without a version anchor or a ``time[datetime]`` are skipped so one
    malformed block does not drop the rest of the page.
    """
    soup = BeautifulSoup(html or "", "lxml")
    items: list[dict[str, str]] = []
    seen_links: set[str] = set()

    for article in soup.find_all("article"):
        heading = article.find("h2", id=True)
        if not isinstance(heading, Tag):
            continue
        anchor_id = str(heading.get("id") or "").strip()
        match = _VERSION_ID.match(anchor_id)
        if not match:
            continue

        time_elem = article.find("time")
        pub_date = ""
        if isinstance(time_elem, Tag):
            pub_date = str(time_elem.get("datetime") or "").strip()
        if not pub_date:
            continue

        title = _version_title(heading, match.group(1))
        if not title:
            continue

        link = changelog_entry_url(page_url, anchor_id)
        if not link or link in seen_links:
            continue

        item = {
            "title": title,
            "link": link,
            "guid": link,
            "pubDate": pub_date,
        }
        description = _extract_notes(heading)
        if description:
            item["description"] = description

        items.append(item)
        seen_links.add(link)
        if len(items) >= max_items:
            break

    return items


def _version_title(heading: Tag, version: str) -> str:
    title = _normalize_whitespace(heading.get_text(" ", strip=True))
    if not title:
        return ""
    if version not in title:
        return f"{title} ({version})"
    return title


def _extract_notes(heading: Tag) -> str:
    content = heading.parent
    if not isinstance(content, Tag):
        return ""

    lines: list[str] = []
    for element in content.find_all(["h3", "li"]):
        if element.name == "li" and element.find_parent("li") is not None:
            continue
        text = _normalize_whitespace(element.get_text(" ", strip=True))
        if not text or (lines and text == lines[-1]):
            continue
        lines.append(text)
    return "\n".join(lines)


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


@register_job
class XaiChangelogJob(FeedJob):
    """Build an RSS feed from an x.ai product changelog page."""

    job_type = "xai_changelog"

    def run(self, context: JobContext) -> JobResult:
        url = str(self.config.get("url") or "").strip()
        output_file = str(self.config.get("output") or "")
        if not url or not output_file:
            return JobResult(name=self.name, success=False, details="缺少 url 或 output 配置")

        options = self.config.get("options") or {}
        impersonate = str(options.get("impersonate") or DEFAULT_IMPERSONATE)
        scraper = WebScraper(
            timeout=options.get("timeout", 30),
            user_agent=options.get("user_agent"),
            retries=options.get("retries", 2),
            backoff_factor=options.get("backoff_factor", 0.5),
            impersonate=impersonate,
        )
        html = scraper.fetch(url, encoding=options.get("encoding"))
        if not html:
            return JobResult(name=self.name, success=False, details="抓取 changelog 页面失败")

        items = extract_xai_changelog_items(
            html,
            url,
            max_items=int(options.get("max_items", DEFAULT_MAX_ITEMS)),
        )
        if not items:
            return JobResult(name=self.name, success=False, details="未解析到 changelog 版本条目")

        output_path = resolve_output_path(context.feeds_dir, output_file)
        generator = RSSGenerator(
            title=str(self.config.get("title") or self.name),
            link=str(self.config.get("link") or url.split("#", 1)[0]),
            description=str(self.config.get("description") or f"{self.name} RSS Feed"),
        )
        generator.add_items(items_oldest_first(items))
        success = generator.generate(str(output_path))
        details = f"输出: {Path(output_path).name} ({len(items)} 条)" if success else "RSS 生成失败"
        return JobResult(name=self.name, success=success, details=details)
