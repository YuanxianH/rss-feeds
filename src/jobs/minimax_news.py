"""从 MiniMax News 页面提取文章并生成 RSS。"""

import json
import logging
import re
from collections import deque
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from src.article_metadata import extract_article_item
from src.http_client import create_retry_session
from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

BASE_URL = "https://www.minimax.io"
NEWS_URL = f"{BASE_URL}/news"
OUTPUT_FILENAME = "minimax_blog.xml"
DEFAULT_MAX_ITEMS = 80
DEFAULT_MAX_DISCOVERY_PAGES = 60
DEFAULT_MAX_SITEMAP_FILES = 80
REQUEST_TIMEOUT = 20
NEWS_SLUG_PATTERN = re.compile(r"/news/[A-Za-z0-9._~/%\-]+")
# 需要过滤掉的无效 slug 模式（JSON-LD 类型标识符、语言代码、时间戳、FAQ 等）
INVALID_SLUG_PATTERNS = [
    # 语言代码: /news/en, /news/zh, /news/en-US
    re.compile(r"^/news/[a-z]{2}(-[A-Za-z]{2})?$"),
    # JSON-LD 类型（PascalCase 或全大写）: NewsArticle, WebPage, Organization, ImageObject, ListItem, BreadcrumbList
    re.compile(r"^/news/[A-Z][a-z]+(?:[A-Z][a-z]+)*$"),
    # 全大写单词: Brand, Global, News
    re.compile(r"^/news/[A-Z][a-z]+$"),
    # 全小写常见非文章单词: customer service, contact, about, home
    re.compile(r"^/news/(?:customer[ -]?service|contact|about|home|faq|help|support|blog|products?|terms|privacy|search)$", re.IGNORECASE),
    # 时间戳: /news/2026-02, /news/2021-12, /news/2026-02-14T11:04:30.812Z
    re.compile(r"^/news/\d{4}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?Z?)?)?$"),
    # ISO 时间戳格式: 2026-02-14T11:13:39.368Z
    re.compile(r"^/news/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z?$"),
    # 邮箱: /news/api@minimax.io
    re.compile(r"^/news/[\w.%+-]+@[\w.-]+$"),
    # 域名文本误判: /news/www.minimax.io, /news/minimax.io
    re.compile(r"^/news/(?:[\w-]+\.)*minimax\.io$", re.IGNORECASE),
    # 动态路由: /news/page-xxx.js, /news/[detail]/xxx
    re.compile(r"^/news/(?:\[[\w]+\]|page-[\w]+\.js)"),
    # 问句（FAQ）: /news/What should I do, /news/How can I, /news/Can I, /news/Making Music...
    re.compile(r"^/news/(?:What(?: should| does)?|How (?:can|do|does)|Can (?:I|you)|Is (?:it|there)|Where|When|Why|Which|Making |If you |Where can |How should)"),
    # URL 编码的反斜杠或特殊字符
    re.compile(r"^/news/.+[\\%]"),
    # 包含空格的标题类 slug（通常是文章标题，不是有效 slug）
    re.compile(r"^/news/.+ .+$"),
]
SITEMAP_CANDIDATES = [
    f"{BASE_URL}/sitemap.xml",
    f"{BASE_URL}/sitemap_index.xml",
    f"{BASE_URL}/sitemap-index.xml",
    f"{BASE_URL}/sitemaps.xml",
    f"{BASE_URL}/sitemap/news.xml",
    f"{BASE_URL}/sitemap-news.xml",
]
def create_session() -> requests.Session:
    return create_retry_session(
        accept="text/html,application/xml,application/xhtml+xml",
        retries=2,
        backoff_factor=0.5,
    )


def normalize_news_url(raw_url: str, base_url: str = NEWS_URL) -> Optional[str]:
    """将链接规范化为 minimax news 文章链接。"""
    if not raw_url:
        return None

    absolute = urljoin(base_url, raw_url.strip())
    parsed = urlparse(absolute)

    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc.endswith("minimax.io"):
        return None

    path = parsed.path.rstrip("/")
    if not path or path == "/news":
        return None
    if not path.startswith("/news/"):
        return None

    # 过滤掉无效的 slug 模式（JSON-LD 类型标识符、语言代码、时间戳等）
    for pattern in INVALID_SLUG_PATTERNS:
        if pattern.match(path):
            return None

    cleaned = parsed._replace(path=path, params="", query="", fragment="")
    return urlunparse(cleaned)


def _extract_news_urls_from_text(text: str, base_url: str) -> list[str]:
    results = []
    seen = set()
    for match in NEWS_SLUG_PATTERN.findall(text):
        normalized = normalize_news_url(match, base_url=base_url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            results.append(normalized)
    return results


def _extract_news_urls_from_json_value(value: str, base_url: str) -> list[str]:
    """从 JSON 字符串值中提取 news 链接，忽略普通文本。"""
    text = value.strip()
    if not text:
        return []

    candidates = []
    seen = set()

    def add_candidate(raw: str):
        normalized = normalize_news_url(raw, base_url=base_url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)

    # 直接 URL 或相对路径
    if text.startswith(("http://", "https://", "/news/", "news/")):
        raw = f"/{text}" if text.startswith("news/") else text
        add_candidate(raw)

    # 长文本中嵌入的 /news/... 片段
    for extracted in _extract_news_urls_from_text(text, base_url=base_url):
        if extracted not in seen:
            seen.add(extracted)
            candidates.append(extracted)

    return candidates


def _iter_json_strings(value: Any) -> Iterable[str]:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            yield current
        elif isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def extract_news_urls_from_html(html: str, page_url: str = NEWS_URL) -> list[str]:
    """从 news 页面 HTML 中提取文章链接。"""
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    urls = []

    def add_url(candidate: str):
        normalized = normalize_news_url(candidate, base_url=page_url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)

    for anchor in soup.select("a[href]"):
        add_url(anchor.get("href", ""))

    # 页面级 canonical / OG URL 也可能是新闻链接
    if canonical := soup.find("link", attrs={"rel": "canonical"}):
        add_url(canonical.get("href", ""))
    for meta_key in ("og:url",):
        meta = soup.find("meta", attrs={"property": meta_key})
        if meta:
            add_url(meta.get("content", ""))

    # 回退：从内嵌 JSON 结构提取 /news/ 链接
    for script in soup.find_all("script"):
        raw_text = script.string or script.get_text()
        if not raw_text:
            continue
        script_id = (script.get("id") or "").strip()
        script_type = (script.get("type") or "").strip()
        if script_id == "__NEXT_DATA__" or script_type in ("application/json", "application/ld+json"):
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                continue
            for value in _iter_json_strings(payload):
                for candidate in _extract_news_urls_from_json_value(value, page_url):
                    add_url(candidate)

    # 最后回退：正则匹配字符串中的相对 news 路径
    for candidate in _extract_news_urls_from_text(html, page_url):
        add_url(candidate)

    return urls


def extract_article_item_from_html(
    url: str,
    html: str,
    response_url: Optional[str] = None,
) -> Optional[dict]:
    """从文章页面提取 RSS 所需字段。"""
    return extract_article_item(
        url,
        html,
        response_url=response_url,
        normalize_url=lambda candidate, base: normalize_news_url(candidate, base_url=base),
    )


def _fetch_article_item(session: requests.Session, url: str, logger: logging.Logger) -> Optional[dict]:
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(f"抓取文章失败 {url}: {exc}")
        return None

    item = extract_article_item_from_html(url, response.text, response_url=response.url)
    if not item:
        logger.warning(f"解析文章失败（无有效内容）: {url}")
    return item


def _fetch_news_urls_from_sitemap(
    session: requests.Session,
    logger: logging.Logger,
    max_sitemap_files: int,
) -> list[str]:
    """通过 sitemap 发现 news 文章链接。"""
    logger.info("尝试从 sitemap 回退提取 news 链接...")
    urls: list[str] = []
    seen_urls = set()

    def add_url(raw: str):
        normalized = normalize_news_url(raw, base_url=BASE_URL)
        if normalized and normalized not in seen_urls:
            seen_urls.add(normalized)
            urls.append(normalized)

    def fetch_locs(xml_url: str) -> list[str]:
        try:
            resp = session.get(xml_url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(f"读取 sitemap 失败 {xml_url}: {exc}")
            return []
        soup = BeautifulSoup(resp.text, "xml")
        locs = [loc.get_text(strip=True) for loc in soup.find_all("loc")]
        if locs:
            return locs

        # 某些站点可能返回了 HTML 或非标准内容，做文本回退
        text_locs = re.findall(r"https?://[^\s<>\"]+", resp.text)
        return text_locs

    # robots.txt 中若声明了 sitemap，优先加入候选
    sitemap_queue = deque(SITEMAP_CANDIDATES)
    seen_sitemaps = set()
    try:
        robots_resp = session.get(f"{BASE_URL}/robots.txt", timeout=REQUEST_TIMEOUT)
        if robots_resp.ok:
            for line in robots_resp.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    if sitemap_url:
                        sitemap_queue.appendleft(sitemap_url)
    except requests.RequestException:
        pass

    scanned = 0
    while sitemap_queue and scanned < max_sitemap_files:
        sitemap_url = sitemap_queue.popleft()
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        scanned += 1

        for loc in fetch_locs(sitemap_url):
            if loc.endswith(".xml") and "minimax.io" in loc:
                if loc not in seen_sitemaps:
                    sitemap_queue.append(loc)
                continue
            add_url(loc)

    return urls


def _crawl_related_news_urls(
    session: requests.Session,
    seed_urls: list[str],
    logger: logging.Logger,
    max_discovery_pages: int,
) -> list[str]:
    """从已有文章继续递归发现站内 /news/ 链接。"""
    discovered = []
    discovered_set = set()
    queue = deque(seed_urls)
    visited_pages = set()

    for url in seed_urls:
        if url not in discovered_set:
            discovered_set.add(url)
            discovered.append(url)

    while queue and len(visited_pages) < max_discovery_pages:
        current_url = queue.popleft()
        if current_url in visited_pages:
            continue
        visited_pages.add(current_url)

        try:
            response = session.get(current_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.debug(f"递归抓取失败 {current_url}: {exc}")
            continue

        related_urls = extract_news_urls_from_html(response.text, page_url=current_url)
        for related_url in related_urls:
            if related_url in discovered_set:
                continue
            discovered_set.add(related_url)
            discovered.append(related_url)
            if related_url not in visited_pages:
                queue.append(related_url)

    return discovered


def _fetch_news_urls(session: requests.Session, logger: logging.Logger) -> list[str]:
    try:
        response = session.get(NEWS_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error(f"抓取 News 列表页失败: {exc}")
        return []

    urls = extract_news_urls_from_html(response.text, page_url=NEWS_URL)
    if urls:
        return urls

    logger.warning("News 列表页未提取到文章链接")
    return []


@register_job
class MiniMaxNewsJob(FeedJob):
    job_type = "minimax_news"

    def run(self, context: JobContext) -> JobResult:
        options = self.config.get("options", {})
        max_items = int(options.get("max_items", DEFAULT_MAX_ITEMS))
        max_discovery_pages = int(options.get("max_discovery_pages", DEFAULT_MAX_DISCOVERY_PAGES))
        max_sitemaps = int(options.get("max_sitemaps", DEFAULT_MAX_SITEMAP_FILES))
        output_file = self.config.get("output", OUTPUT_FILENAME)

        output_path = resolve_output_path(context.feeds_dir, output_file)
        logger = logging.getLogger(__name__)
        session = create_session()
        logger.info(f"正在从 {NEWS_URL} 获取文章...")

        list_page_urls = _fetch_news_urls(session, logger)
        sitemap_urls = _fetch_news_urls_from_sitemap(session, logger, max_sitemap_files=max_sitemaps)
        seed_urls = []
        for url in list_page_urls + sitemap_urls:
            if url not in seed_urls:
                seed_urls.append(url)

        article_urls = _crawl_related_news_urls(
            session,
            seed_urls,
            logger,
            max_discovery_pages=max_discovery_pages,
        )
        if not article_urls:
            return JobResult(name=self.name, success=False, details="未找到任何 MiniMax News 文章链接")

        logger.info(
            "提取到 %s 条候选文章链接（列表页: %s, sitemap: %s, 递归后总计: %s）",
            len(article_urls),
            len(list_page_urls),
            len(sitemap_urls),
            len(article_urls),
        )

        items = []
        seen_links = set()
        for idx, article_url in enumerate(article_urls, start=1):
            logger.info(f"解析文章 {idx}/{len(article_urls)}: {article_url}")
            item = _fetch_article_item(session, article_url, logger)
            if not item:
                continue
            link = item.get("link")
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            if not item.get("guid"):
                item["guid"] = article_url
            items.append(item)
            if len(items) >= max_items:
                break

        if not items:
            return JobResult(name=self.name, success=False, details="MiniMax News 文章解析失败，未生成任何条目")

        # feedgen 内部会以栈顺序输出，反转以保持“最新优先”阅读体验。
        ordered_items = list(reversed(items))

        generator = RSSGenerator(
            title=self.config.get("title", "MiniMax News"),
            link=self.config.get("link", NEWS_URL),
            description=self.config.get("description", "Latest news and updates from MiniMax"),
        )
        generator.add_items(ordered_items)

        success = generator.generate(str(output_path))
        if not success:
            return JobResult(name=self.name, success=False, details="RSS 生成失败")

        logger.info(f"成功生成 {len(items)} 篇 MiniMax News 到 {output_path}")
        return JobResult(name=self.name, success=True, details=f"输出: {output_path}")
