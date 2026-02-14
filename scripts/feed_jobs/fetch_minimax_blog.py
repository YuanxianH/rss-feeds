#!/usr/bin/env python3
"""从 MiniMax News 页面提取文章并生成 RSS。"""

import json
import logging
import re
import sys
import argparse
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.rss_generator import RSSGenerator

BASE_URL = "https://www.minimax.io"
NEWS_URL = f"{BASE_URL}/news"
OUTPUT_FILENAME = "minimax_blog.xml"
DEFAULT_MAX_ITEMS = 80
DEFAULT_MAX_DISCOVERY_PAGES = 60
DEFAULT_MAX_SITEMAP_FILES = 80
REQUEST_TIMEOUT = 20
NEWS_SLUG_PATTERN = re.compile(r"/news/[A-Za-z0-9._~/%\-]+")
SITEMAP_CANDIDATES = [
    f"{BASE_URL}/sitemap.xml",
    f"{BASE_URL}/sitemap_index.xml",
    f"{BASE_URL}/sitemap-index.xml",
    f"{BASE_URL}/sitemaps.xml",
    f"{BASE_URL}/sitemap/news.xml",
    f"{BASE_URL}/sitemap-news.xml",
]


def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xml,application/xhtml+xml",
        }
    )

    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        backoff_factor=0.5,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


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
                add_url(value)

    # 最后回退：正则匹配字符串中的相对 news 路径
    for candidate in _extract_news_urls_from_text(html, page_url):
        add_url(candidate)

    return urls


def _parse_datetime(candidate: str) -> Optional[datetime]:
    if not candidate:
        return None
    text = candidate.strip()
    if not text:
        return None

    normalized = text.replace("年", "-").replace("月", "-").replace("日", "")
    normalized = normalized.replace(".", "-").replace("/", "-")

    try:
        dt = date_parser.parse(normalized, fuzzy=True)
    except Exception:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _first_meta(soup: BeautifulSoup, candidates: list[tuple[str, str]]) -> Optional[str]:
    for attr_name, attr_value in candidates:
        tag = soup.find("meta", attrs={attr_name: attr_value})
        if tag and tag.get("content"):
            content = tag.get("content", "").strip()
            if content:
                return content
    return None


def _extract_json_ld(soup: BeautifulSoup) -> list[Any]:
    entries = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            entries.extend(parsed)
        else:
            entries.append(parsed)
    return entries


def _extract_publish_date(soup: BeautifulSoup) -> Optional[str]:
    meta_date = _first_meta(
        soup,
        [
            ("property", "article:published_time"),
            ("property", "og:published_time"),
            ("name", "publish_date"),
            ("name", "date"),
            ("name", "dc.date"),
        ],
    )
    if meta_date:
        dt = _parse_datetime(meta_date)
        if dt is not None:
            return dt.isoformat()

    for time_tag in soup.select("time"):
        candidate = time_tag.get("datetime") or time_tag.get_text(strip=True)
        dt = _parse_datetime(candidate)
        if dt is not None:
            return dt.isoformat()

    for obj in _extract_json_ld(soup):
        if not isinstance(obj, dict):
            continue
        for key in ("datePublished", "dateCreated", "uploadDate"):
            value = obj.get(key)
            if isinstance(value, str):
                dt = _parse_datetime(value)
                if dt is not None:
                    return dt.isoformat()

    text = soup.get_text(" ", strip=True)
    for match in re.findall(r"(20\d{2}[./-]\d{1,2}[./-]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?)", text):
        dt = _parse_datetime(match)
        if dt is not None:
            return dt.isoformat()

    return None


def _fallback_title_from_url(url: str) -> str:
    slug = urlparse(url).path.rsplit("/", 1)[-1]
    return slug.replace("-", " ").strip().title()


def extract_article_item_from_html(url: str, html: str) -> Optional[dict]:
    """从文章页面提取 RSS 所需字段。"""
    soup = BeautifulSoup(html, "html.parser")

    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical_url = canonical_tag.get("href", "") if canonical_tag else ""
    og_url = _first_meta(soup, [("property", "og:url")]) or ""
    link = normalize_news_url(canonical_url or og_url or url, base_url=url) or url

    title = _first_meta(
        soup,
        [
            ("property", "og:title"),
            ("name", "twitter:title"),
            ("name", "title"),
        ],
    )
    if not title:
        if h1 := soup.select_one("h1"):
            title = h1.get_text(strip=True)
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
    if not title:
        title = _fallback_title_from_url(link)
    if not title:
        return None

    description = _first_meta(
        soup,
        [
            ("property", "og:description"),
            ("name", "description"),
            ("name", "twitter:description"),
        ],
    )
    if not description:
        if p_tag := soup.select_one("article p, main p"):
            description = p_tag.get_text(" ", strip=True)

    item = {
        "title": title,
        "link": link,
    }
    if description:
        item["description"] = description

    pub_date = _extract_publish_date(soup)
    if pub_date:
        item["pubDate"] = pub_date

    author = _first_meta(soup, [("name", "author"), ("property", "article:author")])
    if author:
        item["author"] = author

    return item


def _fetch_article_item(session: requests.Session, url: str, logger: logging.Logger) -> Optional[dict]:
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(f"抓取文章失败 {url}: {exc}")
        return None

    item = extract_article_item_from_html(url, response.text)
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


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch MiniMax news and generate RSS")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS, help="Maximum feed items")
    parser.add_argument(
        "--max-discovery-pages",
        type=int,
        default=DEFAULT_MAX_DISCOVERY_PAGES,
        help="Maximum pages visited during recursive discovery",
    )
    parser.add_argument(
        "--max-sitemaps",
        type=int,
        default=DEFAULT_MAX_SITEMAP_FILES,
        help="Maximum sitemap files to scan",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    output_dir = ROOT_DIR / "feeds"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME

    session = create_session()
    logger.info(f"正在从 {NEWS_URL} 获取文章...")

    list_page_urls = _fetch_news_urls(session, logger)
    sitemap_urls = _fetch_news_urls_from_sitemap(session, logger, max_sitemap_files=args.max_sitemaps)
    seed_urls = []
    for url in list_page_urls + sitemap_urls:
        if url not in seed_urls:
            seed_urls.append(url)

    article_urls = _crawl_related_news_urls(
        session,
        seed_urls,
        logger,
        max_discovery_pages=args.max_discovery_pages,
    )
    if not article_urls:
        logger.error("未找到任何 MiniMax News 文章链接")
        return 1

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
        items.append(item)
        if len(items) >= args.max_items:
            break

    if not items:
        logger.error("MiniMax News 文章解析失败，未生成任何条目")
        return 1

    # feedgen 内部会以栈顺序输出，反转以保持“最新优先”阅读体验。
    ordered_items = list(reversed(items))

    generator = RSSGenerator(
        title="MiniMax News",
        link=NEWS_URL,
        description="Latest news and updates from MiniMax",
    )
    generator.add_items(ordered_items)

    if not generator.generate(str(output_path)):
        logger.error("RSS 生成失败")
        return 1

    logger.info(f"成功生成 {len(items)} 篇 MiniMax News 到 {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
