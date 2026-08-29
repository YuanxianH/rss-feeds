"""Reusable ByteDance Seed list feeds from the live API and list-page SSR."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import requests

from src.http_client import create_retry_session
from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

DEFAULT_API_URL = "https://seed.bytedance.com/api/get_article_list_v2"
DEFAULT_BASE_URL = "https://seed.bytedance.com"
DEFAULT_LOCALE = "zh"
DEFAULT_API_LOCALE = "US"
DEFAULT_MAX_PAGES = 10
DEFAULT_PAGE_SIZE = 20
ARTICLE_TYPE_PUBLICATION = 1
ARTICLE_TYPE_BLOG = 2
ITEM_PATHS = {
    ARTICLE_TYPE_PUBLICATION: "public_papers",
    ARTICLE_TYPE_BLOG: "blog",
}
PATH_TO_ARTICLE_TYPE = {path: article_type for article_type, path in ITEM_PATHS.items()}
ARTICLE_LIST_KEYS = ("sub_article_list", "article_list")
EXTERNAL_LINK_LABELS = {
    1: "arXiv",
    2: "GitHub",
    3: "HuggingFace",
    4: "Video",
}
SHANGHAI = ZoneInfo("Asia/Shanghai")

logger = logging.getLogger(__name__)


def coerce_article_type(value: Any) -> int | None:
    """Parse the Seed article_type enum used by the list API."""
    try:
        article_type = int(value)
    except (TypeError, ValueError):
        return None
    if article_type not in ITEM_PATHS:
        return None
    return article_type


def item_path_for(article_type: int, override: str = "") -> str:
    """Return the public detail-page path segment for a collection."""
    custom = override.strip().strip("/")
    if custom:
        return custom
    return ITEM_PATHS[article_type]


def infer_collection(url: str) -> tuple[str, str, int] | None:
    """Infer locale, item path, and article_type from a live Seed list URL."""
    parsed = urlparse(str(url or "").strip())
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    item_path = parts[-1]
    article_type = PATH_TO_ARTICLE_TYPE.get(item_path)
    if article_type is None:
        return None
    locale = parts[0] if len(parts) >= 2 else DEFAULT_LOCALE
    return locale, item_path, article_type


def extract_article_rows(payload: Any) -> list[Any]:
    """Find the first Seed article list in an API or SSR JSON payload."""

    def looks_like_article(row: Any) -> bool:
        return isinstance(row, dict) and (
            isinstance(row.get("ArticleMeta"), dict)
            or isinstance(row.get("ArticleSubContentZh"), dict)
            or isinstance(row.get("ArticleSubContentEn"), dict)
        )

    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key in ARTICLE_LIST_KEYS:
                rows = current.get(key)
                if isinstance(rows, list) and any(looks_like_article(row) for row in rows):
                    return [row for row in rows if looks_like_article(row)]
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return []


def extract_window_json(html: str, name: str) -> Any | None:
    """Parse a ``window.NAME = {...}`` JSON assignment from Modern.js HTML."""
    marker = f"window.{name}"
    start = html.find(marker)
    if start < 0:
        return None
    equals = html.find("=", start + len(marker))
    if equals < 0:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(html[equals + 1 :].lstrip())
    except json.JSONDecodeError:
        return None
    return payload


def extract_router_articles(html: str) -> list[Any]:
    """Read article cards from ``window._ROUTER_DATA`` on a Seed list page."""
    payload = extract_window_json(html, "_ROUTER_DATA")
    if payload is None:
        return []
    return extract_article_rows(payload)


def localized_field(article: dict[str, Any], field: str, locale: str) -> str:
    """Prefer the requested locale, then fall back to the other language."""
    zh = article.get("ArticleSubContentZh")
    en = article.get("ArticleSubContentEn")
    zh_doc = zh if isinstance(zh, dict) else {}
    en_doc = en if isinstance(en, dict) else {}
    preferred, fallback = (
        (zh_doc, en_doc) if locale.lower().startswith("zh") else (en_doc, zh_doc)
    )
    value = str(preferred.get(field) or "").strip()
    if value:
        return value
    return str(fallback.get(field) or "").strip()


def article_link(base_url: str, locale: str, item_path: str, title_key: str) -> str | None:
    """Build a Seed detail URL and encode non-ASCII slugs."""
    slug = title_key.strip()
    if not slug:
        return None
    base = base_url.rstrip("/")
    loc = locale.strip().strip("/")
    path = item_path.strip().strip("/")
    if not base or not loc or not path:
        return None
    return f"{base}/{loc}/{path}/{quote(slug, safe='')}"


def publish_date(value: Any) -> str | None:
    """Convert Seed millisecond timestamps to Asia/Shanghai ISO dates."""
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp_ms <= 0:
        return None
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=SHANGHAI)
    return dt.isoformat()


def _external_link_label(link_type: Any) -> str:
    try:
        return EXTERNAL_LINK_LABELS[int(link_type)]
    except (TypeError, ValueError, KeyError):
        return "Link"


def external_links_text(meta: dict[str, Any]) -> str:
    """Format arXiv / GitHub / HuggingFace links for the RSS description."""
    raw_links = meta.get("ExternalLinks")
    if not isinstance(raw_links, list):
        return ""
    parts: list[str] = []
    seen: set[str] = set()
    for entry in raw_links:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("Link") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        parts.append(f"{_external_link_label(entry.get('ExternalLinkType'))}: {url}")
    return "\n".join(parts)


def article_guid(meta: dict[str, Any], link: str) -> str:
    """Prefer the numeric ArticleID so slug changes do not fork an entry."""
    article_id = meta.get("ArticleID")
    if article_id in (None, ""):
        return link
    return str(article_id)


def article_to_item(
    article: Any,
    *,
    locale: str,
    base_url: str,
    item_path: str,
) -> dict[str, str] | None:
    """Convert one Seed list payload into an RSS item."""
    if not isinstance(article, dict):
        return None
    meta = article.get("ArticleMeta")
    if not isinstance(meta, dict):
        meta = {}

    title = localized_field(article, "Title", locale)
    title_key = localized_field(article, "TitleKey", locale)
    link = article_link(base_url, locale, item_path, title_key)
    if not title or not link:
        return None

    description = localized_field(article, "Abstract", locale)
    extras = external_links_text(meta)
    if description and extras:
        description = f"{description}\n\n{extras}"
    elif extras:
        description = extras

    item = {
        "title": title,
        "link": link,
        "guid": article_guid(meta, link),
    }
    if description:
        item["description"] = description
    published = publish_date(meta.get("PublishDate"))
    if published:
        item["pubDate"] = published
    return item


def collect_items(
    articles: list[Any],
    *,
    locale: str,
    base_url: str,
    item_path: str,
    seen_ids: set[str],
    limit: int,
) -> list[dict[str, str]]:
    """Normalize articles and skip duplicates or incomplete rows."""
    items: list[dict[str, str]] = []
    for article in articles:
        if len(items) >= limit:
            break
        item = article_to_item(
            article,
            locale=locale,
            base_url=base_url,
            item_path=item_path,
        )
        if not item or item["guid"] in seen_ids:
            continue
        seen_ids.add(item["guid"])
        items.append(item)
    return items


def resolve_collection(config: dict[str, Any]) -> tuple[str, str, int] | None:
    """Resolve a Seed collection from explicit fields or the live list URL."""
    list_url = str(config.get("url") or config.get("link") or "").strip()
    inferred = infer_collection(list_url) if list_url else None
    article_type = coerce_article_type(config.get("article_type"))
    if article_type is None and inferred is not None:
        article_type = inferred[2]
    if article_type is None:
        return None
    locale = str(config.get("locale") or "").strip()
    if not locale:
        locale = inferred[0] if inferred else DEFAULT_LOCALE
    item_path = item_path_for(article_type, str(config.get("item_path") or ""))
    if inferred and not str(config.get("item_path") or "").strip():
        item_path = inferred[1]
    return locale or DEFAULT_LOCALE, item_path, article_type


@register_job
class SeedBytedanceJob(FeedJob):
    """Refresh Seed RSS from the live list API, with list-page SSR fallback."""

    job_type = "seed_bytedance"

    def run(self, context: JobContext) -> JobResult:
        options = self.config.get("options") or {}
        collection = resolve_collection(self.config)
        if collection is None:
            return JobResult(
                name=self.name,
                success=False,
                details="seed_bytedance 需要 url（/blog 或 /public_papers）或 article_type",
            )

        locale, item_path, article_type = collection
        list_url = str(
            self.config.get("url") or self.config.get("link") or ""
        ).strip()
        api_url = str(self.config.get("api_url") or DEFAULT_API_URL).strip()
        base_url = str(self.config.get("base_url") or DEFAULT_BASE_URL).strip()
        output_file = str(self.config.get("output") or f"seed_{item_path}.xml").strip()
        max_items = int(options.get("max_items", 50))
        max_pages = int(options.get("max_pages", DEFAULT_MAX_PAGES))
        page_size = min(max(int(options.get("page_size", DEFAULT_PAGE_SIZE)), 1), 50)
        timeout = float(options.get("timeout", 20))
        api_locale = str(self.config.get("api_locale") or DEFAULT_API_LOCALE).strip()

        session = create_retry_session(
            user_agent=options.get("user_agent"),
            accept="application/json,text/html",
            retries=int(options.get("retries", 2)),
            backoff_factor=float(options.get("backoff_factor", 0.5)),
        )

        items: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        page_token = "0"
        request_headers = (
            {"x-tt-locale": api_locale} if article_type == ARTICLE_TYPE_PUBLICATION else None
        )
        api_error: str | None = None

        for page_index in range(max_pages):
            if len(items) >= max_items:
                break
            try:
                response = session.get(
                    api_url,
                    params={
                        "article_type": article_type,
                        "order_desc": "true",
                        "count": page_size,
                        "page_token": page_token,
                    },
                    headers=request_headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                api_error = f"调用 Seed API 失败: {exc}"
                if items:
                    logger.warning("Seed 后续分页失败，使用已解析条目: %s", exc)
                break
            except ValueError as exc:
                api_error = f"Seed API 返回非法 JSON: {exc}"
                if items:
                    logger.warning("Seed 后续分页 JSON 非法，使用已解析条目: %s", exc)
                break

            if not isinstance(payload, dict):
                api_error = "Seed API 返回非法 JSON"
                if items:
                    logger.warning("Seed 后续分页结构异常，使用已解析条目")
                break

            rows = extract_article_rows(payload)
            items.extend(
                collect_items(
                    rows,
                    locale=locale,
                    base_url=base_url,
                    item_path=item_path,
                    seen_ids=seen_ids,
                    limit=max_items - len(items),
                )
            )

            if page_index == 0 and not items:
                break

            if not payload.get("has_more"):
                break
            next_token = str(payload.get("next_page_token") or "").strip()
            if not next_token or next_token == page_token:
                break
            page_token = next_token

        if not items and list_url:
            try:
                page = session.get(list_url, timeout=timeout)
                page.raise_for_status()
                items.extend(
                    collect_items(
                        extract_router_articles(page.text),
                        locale=locale,
                        base_url=base_url,
                        item_path=item_path,
                        seen_ids=seen_ids,
                        limit=max_items,
                    )
                )
                if items:
                    logger.info("Seed API 不可用，改从列表页 SSR 解析到 %s 条", len(items))
            except requests.RequestException as exc:
                logger.warning("抓取 Seed 列表页失败: %s", exc)

        if not items:
            return JobResult(
                name=self.name,
                success=False,
                details=api_error or "未找到任何 Seed 条目",
            )

        default_link = f"{base_url.rstrip('/')}/{locale}/{item_path}"
        generator = RSSGenerator(
            title=str(self.config.get("title") or self.name),
            link=str(self.config.get("link") or default_link),
            description=str(
                self.config.get("description") or f"Latest posts from {self.name}"
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
