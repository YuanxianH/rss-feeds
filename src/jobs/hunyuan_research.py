"""Hunyuan research preset for the reusable JSON list API job."""

from __future__ import annotations

from typing import Any

from .json_list_api import (
    JsonListApiJob,
    article_to_item as generic_article_to_item,
    article_url as generic_article_url,
    merge_defaults,
    select_articles as generic_select_articles,
    unix_timestamp_to_iso,
)
from .registry import register_job

DEFAULT_API_URL = "https://api.hunyuan.tencent.com/api/blog/publicList"
DEFAULT_ARTICLE_BASE_URL = "https://hy.tencent.com/research"
DEFAULT_LINK = "https://hy.tencent.com/research"
DEFAULT_OUTPUT = "hunyuan_research.xml"
DEFAULT_LOCALE = "zh"
HUNYUAN_SLUG_FIELDS = ("customUrl", "id")
HUNYUAN_FIELDS = {
    "list": "data.list",
    "total": "data.totalNum",
    "title": ["title"],
    "description": ["desc", "summary", "description"],
    "author": ["author", "createdUid"],
    "date": ["displayPublishTime", "publishedAt", "publicAt", "createdAt"],
    "slug": list(HUNYUAN_SLUG_FIELDS),
}

HUNYUAN_DEFAULTS: dict[str, Any] = {
    "api_url": DEFAULT_API_URL,
    "method": "POST",
    "article_base_url": DEFAULT_ARTICLE_BASE_URL,
    "link": DEFAULT_LINK,
    "output": DEFAULT_OUTPUT,
    "locale": DEFAULT_LOCALE,
    "source_label": "混元",
    "empty_details": "未找到任何研究成果",
    "fields": HUNYUAN_FIELDS,
    "request": {
        "page_key": "pageNum",
        "page_size_key": "pageSize",
        "extra_body": {"needFilter": False},
        "headers": {
            "Origin": "https://hy.tencent.com",
            "Referer": "https://hy.tencent.com/research",
        },
    },
}


def article_url(doc: dict[str, Any], article_base_url: str) -> str | None:
    """Build the public Hunyuan research URL from customUrl or numeric id."""
    return generic_article_url(doc, article_base_url, HUNYUAN_SLUG_FIELDS)


def article_to_item(
    doc: dict[str, Any], *, article_base_url: str
) -> dict[str, str] | None:
    """Convert one Hunyuan public-list document into an RSS item."""
    return generic_article_to_item(
        doc, article_base_url=article_base_url, fields=HUNYUAN_FIELDS
    )


def select_articles(
    docs: Any, *, article_base_url: str
) -> list[dict[str, str]]:
    """Normalize Hunyuan research items and drop incomplete rows."""
    return generic_select_articles(
        docs, article_base_url=article_base_url, fields=HUNYUAN_FIELDS
    )


@register_job
class HunyuanResearchJob(JsonListApiJob):
    """Hunyuan defaults on top of the reusable JSON list API job."""

    job_type = "hunyuan_research"

    def __init__(self, config: dict[str, Any]):
        merged = merge_defaults(HUNYUAN_DEFAULTS, config)
        options = config.get("options") or {}
        if "need_filter" in options:
            merged.setdefault("request", {}).setdefault("extra_body", {})[
                "needFilter"
            ] = bool(options["need_filter"])
        super().__init__(merged)


__all__ = [
    "DEFAULT_API_URL",
    "DEFAULT_ARTICLE_BASE_URL",
    "DEFAULT_LINK",
    "DEFAULT_OUTPUT",
    "HunyuanResearchJob",
    "article_to_item",
    "article_url",
    "select_articles",
    "unix_timestamp_to_iso",
]
