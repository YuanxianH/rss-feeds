"""Config-driven RSS job for dynamic or partially rendered blog indexes."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests

from src.article_metadata import extract_article_item
from src.cms_records import record_to_item
from src.discovery import (
    discover_collection_records,
    discover_sitemap_urls,
    extract_article_urls,
    make_url_normalizer,
)
from src.http_client import create_retry_session
from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator

from .base import FeedJob, JobContext, JobResult
from .registry import register_job


@register_job
class DynamicSiteJob(FeedJob):
    """Discover article links from HTML, embedded data, APIs and sitemaps."""

    job_type = "dynamic_site"

    def run(self, context: JobContext) -> JobResult:
        index_url = str(self.config.get("url") or "").strip()
        path_prefix = str(self.config.get("path_prefix") or "").strip()
        output_file = str(self.config.get("output") or "").strip()
        if not index_url or not path_prefix or not output_file:
            return JobResult(
                name=self.name,
                success=False,
                details="dynamic_site 需要 url、path_prefix 和 output",
            )

        options = self.config.get("options") or {}
        timeout = float(options.get("timeout", 20))
        retries = int(options.get("retries", 2))
        backoff_factor = float(options.get("backoff_factor", 0.5))
        max_items = int(options.get("max_items", 50))
        minimum_items = int(options.get("minimum_items", 1))
        max_sitemaps = int(options.get("max_sitemaps", 20))
        max_pages = int(options.get("max_pages", 10))
        page_size = min(max(int(options.get("page_size", 50)), 1), 100)
        category = str(self.config.get("category") or "").strip()
        locale = str(self.config.get("locale") or "").strip()
        require_active = bool(options.get("require_active", False))
        allowed_hosts = self.config.get("allowed_hosts") or [
            urlparse(index_url).hostname or ""
        ]
        normalize_url = make_url_normalizer(
            allowed_hosts=allowed_hosts,
            path_prefix=path_prefix,
        )
        session = create_retry_session(
            user_agent=options.get("user_agent"),
            accept="text/html,application/xhtml+xml,application/xml,application/json",
            retries=retries,
            backoff_factor=backoff_factor,
        )
        logger = logging.getLogger(__name__)

        index_html = ""
        index_response_url = index_url
        try:
            response = session.get(index_url, timeout=timeout)
            response.raise_for_status()
            index_html = response.text
            index_response_url = response.url
        except requests.RequestException as exc:
            if not (self.config.get("api_urls") or self.config.get("sitemap_urls")):
                return JobResult(
                    name=self.name,
                    success=False,
                    details=f"抓取列表页失败: {exc}",
                )
            logger.warning("抓取列表页失败，继续尝试 API/sitemap: %s", exc)

        article_urls = extract_article_urls(
            index_html,
            page_url=index_response_url,
            normalize_url=normalize_url,
            link_selector=str(self.config.get("link_selector") or "a[href]"),
            category=category,
            require_active=require_active,
        )
        sitemap_urls = self.config.get("sitemap_urls") or []
        if sitemap_urls:
            for url in discover_sitemap_urls(
                session,
                sitemap_urls,
                normalize_url=normalize_url,
                timeout=timeout,
                max_files=max_sitemaps,
                logger=logger,
            ):
                if url not in article_urls:
                    article_urls.append(url)

        cms_items: list[dict[str, str]] = []
        api_urls = self.config.get("api_urls") or []
        if api_urls:
            collection_urls, records = discover_collection_records(
                session,
                api_urls,
                page_url=index_url,
                path_prefix=path_prefix,
                normalize_url=normalize_url,
                timeout=timeout,
                max_pages=max_pages,
                page_size=page_size,
                category=category,
                require_active=require_active,
                logger=logger,
            )
            for url in collection_urls:
                if url not in article_urls:
                    article_urls.append(url)
            seen_cms_links: set[str] = set()
            for record in records:
                item = record_to_item(
                    record,
                    page_url=index_url,
                    path_prefix=path_prefix,
                    locale=locale,
                    normalize_url=normalize_url,
                )
                if not item or item["link"] in seen_cms_links:
                    continue
                seen_cms_links.add(item["link"])
                cms_items.append(item)

        if not article_urls and not cms_items:
            return JobResult(
                name=self.name,
                success=False,
                details="未找到任何文章链接",
            )

        items: list[dict[str, str]] = []
        seen_links: set[str] = set()
        for item in cms_items:
            if item["link"] in seen_links:
                continue
            seen_links.add(item["link"])
            items.append(item)
            if len(items) >= max_items:
                break

        for article_url in article_urls:
            if len(items) >= max_items:
                break
            if article_url in seen_links:
                continue
            try:
                article_response = session.get(article_url, timeout=timeout)
                article_response.raise_for_status()
            except requests.RequestException as exc:
                logger.warning("抓取文章失败 %s: %s", article_url, exc)
                continue

            item = extract_article_item(
                article_url,
                article_response.text,
                response_url=article_response.url,
                normalize_url=normalize_url,
            )
            if not item or item["link"] in seen_links:
                continue
            seen_links.add(item["link"])
            item["guid"] = item["link"]
            items.append(item)

        if len(items) < minimum_items:
            return JobResult(
                name=self.name,
                success=False,
                details=(
                    f"仅解析到 {len(items)} 篇文章，低于 minimum_items={minimum_items}"
                ),
            )

        items.sort(key=lambda item: item.get("pubDate") or "", reverse=True)
        items = items[:max_items]

        # feedgen emits entries in stack order.
        generator = RSSGenerator(
            title=str(self.config.get("title") or self.name),
            link=str(self.config.get("link") or index_url),
            description=str(self.config.get("description") or f"Latest posts from {self.name}"),
        )
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
