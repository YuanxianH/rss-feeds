"""Zhipu AI research blog job backed by the public articles API."""

from __future__ import annotations

import logging
from typing import Any, Iterable
from urllib.parse import urljoin

import requests

from src.http_client import create_retry_session
from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

DEFAULT_API_URL = "https://www.zhipuai.cn/api/articles"
DEFAULT_ARTICLE_BASE_URL = "https://www.zhipuai.cn/zh/research"
DEFAULT_LINK = "https://www.zhipuai.cn/zh/research"
DEFAULT_OUTPUT = "zhipu_research.xml"
DEFAULT_CATEGORY = "blog"
DEFAULT_LOCALE = "zh"
DEFAULT_MAX_PAGES = 10

logger = logging.getLogger(__name__)


def article_url(article_id: Any, article_base_url: str) -> str | None:
    """Build a stable research article URL from a numeric CMS id."""
    try:
        numeric = int(article_id)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    return urljoin(article_base_url.rstrip("/") + "/", str(numeric))


def _localized(doc: dict[str, Any], field: str, locale: str) -> str:
    preferred = str(doc.get(f"{field}_{locale}") or "").strip()
    if preferred:
        return preferred
    for key in (f"{field}_zh", f"{field}_en"):
        value = str(doc.get(key) or "").strip()
        if value:
            return value
    return ""


def _tag_names(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, list):
        return []

    names: list[str] = []
    for tag in value:
        if isinstance(tag, str) and tag.strip():
            names.append(tag.strip())
            continue
        if isinstance(tag, dict):
            for key in ("name", "title", "label", "name_zh", "title_zh"):
                text = str(tag.get(key) or "").strip()
                if text:
                    names.append(text)
                    break
    return names


def is_listed_article(
    doc: Any,
    *,
    category: str,
    require_active: bool,
) -> bool:
    """Return whether a CMS document belongs on the public research list."""
    if not isinstance(doc, dict):
        return False
    if str(doc.get("category") or "").strip().lower() != category.lower():
        return False
    if require_active and doc.get("active") is not True:
        return False
    return True


def article_to_item(
    doc: dict[str, Any],
    *,
    locale: str,
    article_base_url: str,
) -> dict[str, str] | None:
    """Convert one CMS article into an RSS item."""
    link = article_url(doc.get("id"), article_base_url)
    title = _localized(doc, "title", locale)
    if not link or not title:
        return None

    description = _localized(doc, "resume", locale)
    if not description:
        tags = _tag_names(
            doc.get(f"tag_{locale}") or doc.get("tag_zh") or doc.get("tag_en")
        )
        description = " · ".join(tags)

    item = {"title": title, "link": link, "guid": link}
    if description:
        item["description"] = description
    published = str(doc.get("createAt") or doc.get("createdAt") or "").strip()
    if published:
        item["pubDate"] = published
    return item


def select_articles(
    docs: Iterable[Any],
    *,
    category: str,
    require_active: bool,
    locale: str,
    article_base_url: str,
) -> list[dict[str, str]]:
    """Filter, normalize, and sort research blog items newest first."""
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for doc in docs:
        if not is_listed_article(
            doc, category=category, require_active=require_active
        ):
            continue
        item = article_to_item(
            doc, locale=locale, article_base_url=article_base_url
        )
        if not item or item["link"] in seen:
            continue
        seen.add(item["link"])
        items.append(item)
    items.sort(key=lambda item: item.get("pubDate") or "", reverse=True)
    return items


@register_job
class ZhipuResearchJob(FeedJob):
    """Build RSS from Zhipu's Payload CMS articles API."""

    job_type = "zhipu_research"

    def run(self, context: JobContext) -> JobResult:
        options = self.config.get("options") or {}
        api_url = str(self.config.get("api_url") or DEFAULT_API_URL).strip()
        article_base_url = str(
            self.config.get("article_base_url") or DEFAULT_ARTICLE_BASE_URL
        ).strip()
        category = str(self.config.get("category") or DEFAULT_CATEGORY).strip()
        locale = str(self.config.get("locale") or DEFAULT_LOCALE).strip() or DEFAULT_LOCALE
        output_file = str(self.config.get("output") or DEFAULT_OUTPUT).strip()
        max_items = int(options.get("max_items", 50))
        max_pages = int(options.get("max_pages", DEFAULT_MAX_PAGES))
        require_active = bool(options.get("require_active", True))
        timeout = float(options.get("timeout", 20))
        page_size = min(max(int(options.get("page_size", 50)), 1), 100)

        session = create_retry_session(
            user_agent=options.get("user_agent"),
            accept="application/json",
            retries=int(options.get("retries", 2)),
            backoff_factor=float(options.get("backoff_factor", 0.5)),
        )

        docs: list[dict[str, Any]] = []
        try:
            for page in range(1, max_pages + 1):
                response = session.get(
                    api_url,
                    params={
                        "limit": page_size,
                        "page": page,
                        "depth": 0,
                        "sort": "-createAt",
                        "where[category][equals]": category,
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(
                    payload.get("docs"), list
                ):
                    return JobResult(
                        name=self.name,
                        success=False,
                        details="智谱 API 返回非法 JSON",
                    )
                docs.extend(
                    item for item in payload["docs"] if isinstance(item, dict)
                )
                if not payload.get("hasNextPage"):
                    break
        except requests.RequestException as exc:
            return JobResult(
                name=self.name,
                success=False,
                details=f"调用智谱 API 失败: {exc}",
            )
        except ValueError as exc:
            return JobResult(
                name=self.name,
                success=False,
                details=f"智谱 API 返回非法 JSON: {exc}",
            )

        items = select_articles(
            docs,
            category=category,
            require_active=require_active,
            locale=locale,
            article_base_url=article_base_url,
        )[:max_items]
        if not items:
            return JobResult(name=self.name, success=False, details="未找到任何研究博客")

        generator = RSSGenerator(
            title=str(self.config.get("title") or self.name),
            link=str(self.config.get("link") or DEFAULT_LINK),
            description=str(
                self.config.get("description")
                or "Latest research blogs from Zhipu AI"
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
