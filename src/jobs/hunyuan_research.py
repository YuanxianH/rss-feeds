"""Tencent Hunyuan research job backed by the public blog list API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urljoin

import requests

from src.http_client import create_retry_session
from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

DEFAULT_API_URL = "https://api.hunyuan.tencent.com/api/blog/publicList"
DEFAULT_ARTICLE_BASE_URL = "https://hy.tencent.com/research"
DEFAULT_LINK = "https://hy.tencent.com/research"
DEFAULT_OUTPUT = "hunyuan_research.xml"
DEFAULT_LOCALE = "zh"
DEFAULT_MAX_PAGES = 10
DEFAULT_PAGE_SIZE = 50

logger = logging.getLogger(__name__)


def article_url(doc: dict[str, Any], article_base_url: str) -> str | None:
    """Build the public research URL from customUrl or numeric id."""
    slug = str(doc.get("customUrl") or "").strip()
    if not slug:
        article_id = doc.get("id")
        try:
            numeric = int(article_id)
        except (TypeError, ValueError):
            return None
        if numeric <= 0:
            return None
        slug = str(numeric)
    return urljoin(article_base_url.rstrip("/") + "/", slug)


def unix_timestamp_to_iso(value: Any) -> str:
    """Convert Hunyuan unix seconds (or milliseconds) to an ISO datetime."""
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _first_timestamp(*values: Any) -> str:
    for value in values:
        converted = unix_timestamp_to_iso(value)
        if converted:
            return converted
    return ""


def _normalize_author(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = [part.strip() for part in text.replace("；", ";").split(";") if part.strip()]
    return ", ".join(parts) if parts else text


def article_to_item(doc: dict[str, Any], *, article_base_url: str) -> dict[str, str] | None:
    """Convert one public list document into an RSS item."""
    title = str(doc.get("title") or "").strip()
    link = article_url(doc, article_base_url)
    if not title or not link:
        return None

    item = {"title": title, "link": link, "guid": link}
    description = str(doc.get("desc") or "").strip()
    if description:
        item["description"] = description
    author = _normalize_author(doc.get("author") or doc.get("createdUid"))
    if author:
        item["author"] = author
    published = _first_timestamp(
        doc.get("displayPublishTime"),
        doc.get("publishedAt"),
        doc.get("publicAt"),
        doc.get("createdAt"),
    )
    if published:
        item["pubDate"] = published
    return item


def select_articles(
    docs: Iterable[Any],
    *,
    article_base_url: str,
) -> list[dict[str, str]]:
    """Normalize public research items and drop incomplete or duplicate rows."""
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        item = article_to_item(doc, article_base_url=article_base_url)
        if not item or item["link"] in seen:
            continue
        seen.add(item["link"])
        items.append(item)
    return items


@register_job
class HunyuanResearchJob(FeedJob):
    """Build RSS from Hunyuan's public research list API."""

    job_type = "hunyuan_research"

    def run(self, context: JobContext) -> JobResult:
        options = self.config.get("options") or {}
        api_url = str(self.config.get("api_url") or DEFAULT_API_URL).strip()
        article_base_url = str(
            self.config.get("article_base_url") or DEFAULT_ARTICLE_BASE_URL
        ).strip()
        locale = str(self.config.get("locale") or DEFAULT_LOCALE).strip() or DEFAULT_LOCALE
        output_file = str(self.config.get("output") or DEFAULT_OUTPUT).strip()
        max_items = int(options.get("max_items", 50))
        max_pages = int(options.get("max_pages", DEFAULT_MAX_PAGES))
        timeout = float(options.get("timeout", 20))
        page_size = min(max(int(options.get("page_size", DEFAULT_PAGE_SIZE)), 1), 100)
        need_filter = bool(options.get("need_filter", False))

        session = create_retry_session(
            user_agent=options.get("user_agent"),
            accept="application/json",
            retries=int(options.get("retries", 2)),
            backoff_factor=float(options.get("backoff_factor", 0.5)),
        )

        docs: list[dict[str, Any]] = []
        try:
            for page in range(1, max_pages + 1):
                response = session.post(
                    api_url,
                    json={
                        "pageNum": page,
                        "pageSize": page_size,
                        "needFilter": need_filter,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "accept-language": locale,
                        "Origin": "https://hy.tencent.com",
                        "Referer": "https://hy.tencent.com/research",
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("code") not in (0, "0"):
                    return JobResult(
                        name=self.name,
                        success=False,
                        details="混元 API 返回非法 JSON",
                    )
                data = payload.get("data")
                if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                    return JobResult(
                        name=self.name,
                        success=False,
                        details="混元 API 返回非法 JSON",
                    )
                page_docs = [item for item in data["list"] if isinstance(item, dict)]
                docs.extend(page_docs)
                total = data.get("totalNum")
                try:
                    total_count = int(total)
                except (TypeError, ValueError):
                    total_count = None
                if not page_docs or (
                    total_count is not None and len(docs) >= total_count
                ):
                    break
        except requests.RequestException as exc:
            return JobResult(
                name=self.name,
                success=False,
                details=f"调用混元 API 失败: {exc}",
            )
        except ValueError as exc:
            return JobResult(
                name=self.name,
                success=False,
                details=f"混元 API 返回非法 JSON: {exc}",
            )

        items = select_articles(docs, article_base_url=article_base_url)[:max_items]
        if not items:
            return JobResult(name=self.name, success=False, details="未找到任何研究成果")

        generator = RSSGenerator(
            title=str(self.config.get("title") or self.name),
            link=str(self.config.get("link") or DEFAULT_LINK),
            description=str(
                self.config.get("description")
                or "Latest research publications from Tencent Hunyuan"
            ),
        )
        # feedgen emits entries in stack order.
        generator.add_items(list(reversed(items)))
        output_path = resolve_output_path(context.feeds_dir, output_file)
        if not generator.generate(str(output_path)):
            return JobResult(name=self.name, success=False, details="RSS 生成失败")

        logger.info("成功生成 %s 篇 %s 到 %s", len(items), self.name, output_path)
        return JobResult(
            name=self.name,
            success=True,
            details=f"{len(items)} items → {output_path}",
        )
