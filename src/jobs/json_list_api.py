"""Config-driven RSS job for paginated JSON list APIs."""

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

DEFAULT_LIST_PATHS = (
    "data.list",
    "data.docs",
    "data.items",
    "list",
    "docs",
    "items",
)
DEFAULT_TOTAL_PATHS = ("data.totalNum", "data.total", "totalNum", "total")
DEFAULT_TITLE_FIELDS = ("title", "name", "headline")
DEFAULT_DESCRIPTION_FIELDS = ("desc", "description", "summary", "resume", "abstract")
DEFAULT_AUTHOR_FIELDS = ("author", "createdUid", "authors")
DEFAULT_DATE_FIELDS = (
    "displayPublishTime",
    "publishedAt",
    "publicAt",
    "createdAt",
    "date",
    "pubDate",
)
DEFAULT_SLUG_FIELDS = ("customUrl", "slug", "path", "url", "id")
DEFAULT_MAX_PAGES = 10
DEFAULT_PAGE_SIZE = 50

logger = logging.getLogger(__name__)


def merge_defaults(defaults: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge job config on top of reusable defaults."""
    merged: dict[str, Any] = dict(defaults)
    for key, value in config.items():
        current = merged.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merged[key] = merge_defaults(current, value)
        else:
            merged[key] = value
    return merged


def get_by_path(payload: Any, path: str) -> Any:
    """Read a dotted path such as ``data.list`` from a JSON object."""
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def field_names(value: Any, fallback: Iterable[str]) -> list[str]:
    if value is None:
        return [str(item) for item in fallback]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, (list, tuple)):
        names = [str(item).strip() for item in value if str(item).strip()]
        if names:
            return names
    return [str(item) for item in fallback]


def first_present(doc: dict[str, Any], keys: Iterable[str]) -> Any:
    """Return the first non-empty field, supporting dotted paths."""
    for key in keys:
        value = get_by_path(doc, key) if "." in key else doc.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def unix_timestamp_to_iso(value: Any) -> str:
    """Convert unix seconds (or milliseconds) to an ISO datetime."""
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def coerce_pubdate(value: Any) -> str:
    """Accept unix timestamps or already-parseable date strings."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return unix_timestamp_to_iso(value)
    text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        return unix_timestamp_to_iso(text)
    return text


def _normalize_author(value: Any) -> str:
    if isinstance(value, list):
        parts = [str(part).strip() for part in value if str(part).strip()]
        return ", ".join(parts)
    text = str(value or "").strip()
    if not text:
        return ""
    parts = [part.strip() for part in text.replace("；", ";").split(";") if part.strip()]
    return ", ".join(parts) if parts else text


def article_url(
    doc: dict[str, Any],
    article_base_url: str,
    slug_fields: Iterable[str] = DEFAULT_SLUG_FIELDS,
) -> str | None:
    """Build a public article URL from slug fields or an absolute link."""
    for field in slug_fields:
        raw = first_present(doc, (field,))
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if text.startswith("http://") or text.startswith("https://"):
            return text
        if field == "id":
            try:
                numeric = int(text)
            except ValueError:
                continue
            if numeric <= 0:
                continue
            text = str(numeric)
        return urljoin(article_base_url.rstrip("/") + "/", text)
    return None


def article_to_item(
    doc: dict[str, Any],
    *,
    article_base_url: str,
    fields: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Convert one list document into an RSS item using field mappings."""
    mapping = fields or {}
    title = str(
        first_present(doc, field_names(mapping.get("title"), DEFAULT_TITLE_FIELDS)) or ""
    ).strip()
    link = article_url(
        doc,
        article_base_url,
        field_names(mapping.get("slug"), DEFAULT_SLUG_FIELDS),
    )
    if not title or not link:
        return None

    item = {"title": title, "link": link, "guid": link}
    description = str(
        first_present(
            doc, field_names(mapping.get("description"), DEFAULT_DESCRIPTION_FIELDS)
        )
        or ""
    ).strip()
    if description:
        item["description"] = description
    author = _normalize_author(
        first_present(doc, field_names(mapping.get("author"), DEFAULT_AUTHOR_FIELDS))
    )
    if author:
        item["author"] = author
    published = coerce_pubdate(
        first_present(doc, field_names(mapping.get("date"), DEFAULT_DATE_FIELDS))
    )
    if published:
        item["pubDate"] = published
    return item


def select_articles(
    docs: Iterable[Any],
    *,
    article_base_url: str,
    fields: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Normalize list items and drop incomplete or duplicate rows."""
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        item = article_to_item(
            doc, article_base_url=article_base_url, fields=fields
        )
        if not item or item["link"] in seen:
            continue
        seen.add(item["link"])
        items.append(item)
    return items


def extract_page_docs(payload: Any, fields: dict[str, Any]) -> tuple[list[Any] | None, Any]:
    """Return the item list and optional total from a JSON payload."""
    if not isinstance(payload, dict):
        return None, None
    success_code = fields.get("success_code", 0)
    if "code" in payload and payload.get("code") not in (success_code, str(success_code)):
        return None, None

    configured_list = fields.get("list")
    list_paths = (
        [configured_list]
        if isinstance(configured_list, str) and configured_list.strip()
        else list(DEFAULT_LIST_PATHS)
    )
    raw_list = None
    for path in list_paths:
        candidate = get_by_path(payload, path)
        if isinstance(candidate, list):
            raw_list = candidate
            break
    if raw_list is None:
        return None, None

    configured_total = fields.get("total")
    total_paths = (
        [configured_total]
        if isinstance(configured_total, str) and configured_total.strip()
        else list(DEFAULT_TOTAL_PATHS)
    )
    total = None
    for path in total_paths:
        value = get_by_path(payload, path)
        if value is not None:
            total = value
            break
    return raw_list, total


@register_job
class JsonListApiJob(FeedJob):
    """Build RSS from a paginated JSON list API described in config."""

    job_type = "json_list_api"

    def run(self, context: JobContext) -> JobResult:
        options = self.config.get("options") or {}
        fields = self.config.get("fields") or {}
        request_cfg = self.config.get("request") or {}
        api_url = str(self.config.get("api_url") or "").strip()
        article_base_url = str(self.config.get("article_base_url") or "").strip()
        output_file = str(self.config.get("output") or "").strip()
        source_label = str(self.config.get("source_label") or "列表").strip() or "列表"
        if not api_url or not article_base_url or not output_file:
            return JobResult(
                name=self.name,
                success=False,
                details="json_list_api 需要 api_url、article_base_url 和 output",
            )

        method = str(self.config.get("method") or request_cfg.get("method") or "POST").upper()
        locale = str(self.config.get("locale") or "zh").strip() or "zh"
        max_items = int(options.get("max_items", 50))
        max_pages = int(options.get("max_pages", DEFAULT_MAX_PAGES))
        timeout = float(options.get("timeout", 20))
        page_size = min(max(int(options.get("page_size", DEFAULT_PAGE_SIZE)), 1), 200)
        page_key = str(request_cfg.get("page_key") or "pageNum")
        page_size_key = str(request_cfg.get("page_size_key") or "pageSize")
        extra_body = dict(request_cfg.get("extra_body") or {})
        extra_headers = {
            str(key): str(value)
            for key, value in dict(request_cfg.get("headers") or {}).items()
            if str(key).strip()
        }

        session = create_retry_session(
            user_agent=options.get("user_agent"),
            accept="application/json",
            retries=int(options.get("retries", 2)),
            backoff_factor=float(options.get("backoff_factor", 0.5)),
            allowed_methods=("GET", "HEAD", "POST"),
        )

        docs: list[dict[str, Any]] = []
        try:
            for page in range(1, max_pages + 1):
                body = {**extra_body, page_key: page, page_size_key: page_size}
                headers = {
                    "Content-Type": "application/json",
                    "accept-language": locale,
                    **extra_headers,
                }
                if method == "GET":
                    response = session.get(
                        api_url, params=body, headers=headers, timeout=timeout
                    )
                else:
                    response = session.post(
                        api_url, json=body, headers=headers, timeout=timeout
                    )
                response.raise_for_status()
                payload = response.json()
                raw_list, total = extract_page_docs(payload, fields)
                if raw_list is None:
                    return JobResult(
                        name=self.name,
                        success=False,
                        details=f"{source_label} API 返回非法 JSON",
                    )
                page_docs = [item for item in raw_list if isinstance(item, dict)]
                docs.extend(page_docs)
                try:
                    total_count = int(total) if total is not None else None
                except (TypeError, ValueError):
                    total_count = None
                has_next_path = str(fields.get("has_next") or "").strip()
                has_next = get_by_path(payload, has_next_path) if has_next_path else None
                if not page_docs:
                    break
                if has_next is False:
                    break
                if total_count is not None and len(docs) >= total_count:
                    break
                if total_count is None and has_next is None and len(page_docs) < page_size:
                    break
        except requests.RequestException as exc:
            return JobResult(
                name=self.name,
                success=False,
                details=f"调用{source_label} API 失败: {exc}",
            )
        except ValueError as exc:
            return JobResult(
                name=self.name,
                success=False,
                details=f"{source_label} API 返回非法 JSON: {exc}",
            )

        items = select_articles(
            docs, article_base_url=article_base_url, fields=fields
        )[:max_items]
        if not items:
            return JobResult(
                name=self.name,
                success=False,
                details=str(
                    self.config.get("empty_details") or f"未找到任何{source_label}条目"
                ),
            )

        generator = RSSGenerator(
            title=str(self.config.get("title") or self.name),
            link=str(self.config.get("link") or article_base_url),
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
