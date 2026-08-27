"""Kimi Blog RSS 任务 - 从 kimi.ai 的 Next.js 博客提取文章."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from src.http_client import create_retry_session
from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

BASE_URL = "https://www.kimi.ai"
BLOG_URL = f"{BASE_URL}/blog/"
DEFAULT_OUTPUT = "kimi_blog.xml"
REQUEST_TIMEOUT = 20
ALLOWED_HOSTS = ("kimi.ai", "kimi.com")
DENIED_SLUGS = {
    "blog",
    "breadcrumblist",
    "home",
    "index",
    "listitem",
    "research",
}
ARTICLE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BLOG_PATH_RE = re.compile(r"(?:https?://[^/]+)?(/blog/[A-Za-z0-9][A-Za-z0-9\-_]*)")
VP_HASH_MAP_RE = re.compile(r'__VP_HASH_MAP__\s*=\s*JSON\.parse\("(.+?)"\)')


def create_session() -> requests.Session:
    return create_retry_session(
        accept="text/html,application/xhtml+xml",
        retries=2,
        backoff_factor=0.5,
    )


def normalize_article_url(raw_url: str, base_url: str = BLOG_URL) -> Optional[str]:
    """Keep only kimi blog article permalinks, drop locale/index/schema noise."""
    if not raw_url:
        return None

    parsed = urlparse(urljoin(base_url, str(raw_url).strip()))
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        return None
    if not hostname or not any(
        hostname == host or hostname.endswith(f".{host}") for host in ALLOWED_HOSTS
    ):
        return None

    path = parsed.path.rstrip("/")
    if not path.startswith("/blog/"):
        return None

    slug = path.rsplit("/", 1)[-1].lower()
    if slug in DENIED_SLUGS or not ARTICLE_SLUG_RE.fullmatch(slug):
        return None

    return urlunparse(("https", "www.kimi.ai", f"/blog/{slug}", "", "", ""))


def extract_article_urls_from_index(html: str, base_url: str = BLOG_URL) -> list[str]:
    """Discover article links from HTML, Next.js payloads, or VitePress maps."""
    urls: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        normalized = normalize_article_url(candidate, base_url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        add(anchor.get("href", ""))

    for match in BLOG_PATH_RE.finditer(html):
        add(match.group(1))

    vp_match = VP_HASH_MAP_RE.search(html)
    if vp_match:
        json_str = vp_match.group(1).encode().decode("unicode_escape")
        try:
            pages = json.loads(json_str)
        except json.JSONDecodeError:
            pages = {}
        for page_name in pages:
            if page_name == "index.md":
                continue
            article_path = str(page_name).replace(".md", "")
            add(urljoin(base_url, article_path))

    return urls


def extract_article_item(url: str, html: str) -> Optional[dict]:
    """从文章页面提取 RSS 条目。"""
    soup = BeautifulSoup(html, "html.parser")

    title = None
    if og_title := soup.find("meta", attrs={"property": "og:title"}):
        title = (og_title.get("content") or "").strip()
    if not title and (title_tag := soup.find("title")):
        title = title_tag.get_text(strip=True)
    if not title:
        return None

    description = None
    if og_desc := soup.find("meta", attrs={"property": "og:description"}):
        description = (og_desc.get("content") or "").strip()
    if not description:
        if meta_desc := soup.find("meta", attrs={"name": "description"}):
            description = (meta_desc.get("content") or "").strip()
    if not description:
        for p in soup.select("div.markdown p, article p, main p"):
            text = p.get_text(strip=True)
            if text and len(text) > 50:
                description = text[:500]
                break

    item = {
        "title": title,
        "link": url,
    }
    if description:
        item["description"] = description
    return item


@register_job
class KimiBlogJob(FeedJob):
    job_type = "kimi_blog"

    def run(self, context: JobContext) -> JobResult:
        output_file = self.config.get("output", DEFAULT_OUTPUT)
        output_path = resolve_output_path(context.feeds_dir, output_file)
        logger = logging.getLogger(__name__)

        session = create_session()
        logger.info(f"正在从 {BLOG_URL} 获取文章列表...")

        try:
            response = session.get(BLOG_URL, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            return JobResult(name=self.name, success=False, details=f"抓取失败: {exc}")

        article_urls = extract_article_urls_from_index(response.text, response.url)
        if not article_urls:
            return JobResult(name=self.name, success=False, details="未找到任何文章链接")

        logger.info(f"找到 {len(article_urls)} 篇文章")

        items = []
        for idx, article_url in enumerate(article_urls, start=1):
            logger.info(f"解析文章 {idx}/{len(article_urls)}: {article_url}")
            try:
                resp = session.get(article_url, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.warning(f"抓取文章失败 {article_url}: {exc}")
                continue

            item = extract_article_item(article_url, resp.text)
            if item:
                items.append(item)
                logger.info(f"  - {item.get('title', 'N/A')[:50]}")

        if not items:
            return JobResult(name=self.name, success=False, details="未能解析任何文章")

        items = list(reversed(items))

        generator = RSSGenerator(
            title=self.config.get("title", "Kimi Blog"),
            link=self.config.get("link", BLOG_URL),
            description=self.config.get(
                "description", "Kimi Research Articles & Technical Blogs"
            ),
        )
        generator.add_items(items)

        success = generator.generate(str(output_path))
        if not success:
            return JobResult(name=self.name, success=False, details="RSS 生成失败")

        logger.info(f"成功生成 {len(items)} 篇 Kimi Blog 到 {output_path}")
        return JobResult(name=self.name, success=True, details=f"输出: {output_path}")
