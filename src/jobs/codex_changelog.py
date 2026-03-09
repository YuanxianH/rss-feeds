"""Codex changelog RSS job."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator
from src.scraper import WebScraper

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_URL = "https://developers.openai.com/codex/changelog"
DEFAULT_OUTPUT = "codex_github_releases.xml"
DEFAULT_TITLE = "Codex GitHub Releases"
DEFAULT_DESCRIPTION = "GitHub release entries from the official Codex changelog"
DEFAULT_LINK = f"{DEFAULT_SOURCE_URL}#github-release"
DEFAULT_FALLBACK_ATOM_URL = "https://github.com/openai/codex/releases.atom"
DEFAULT_MAX_ITEMS = 50
DEFAULT_ANCHOR_PREFIXES = ("github-release-",)


def extract_codex_changelog_items(
    html: str,
    page_url: str,
    *,
    anchor_prefixes: Iterable[str] | None = None,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> list[dict[str, str]]:
    """Extract changelog entries backed by copy-link anchors."""
    soup = BeautifulSoup(html, "lxml")
    normalized_page_url = page_url.split("#", 1)[0]
    prefixes = tuple(anchor_prefixes or DEFAULT_ANCHOR_PREFIXES)
    items: list[dict[str, str]] = []
    seen_guids: set[str] = set()

    for container in soup.select("main li.scroll-mt-28"):
        time_elem = container.find("time")
        heading = container.find("h3")
        article = container.find("article")
        anchor_id = _extract_anchor_id(container)

        if not time_elem or not heading or not article or not anchor_id:
            continue
        if prefixes and not anchor_id.startswith(prefixes):
            continue

        guid = f"{normalized_page_url}#{anchor_id}"
        if guid in seen_guids:
            continue

        title = _extract_heading_text(heading)
        if not title:
            continue

        link = _extract_release_link(article) or guid
        description = _extract_description(article)
        pub_date = time_elem.get("datetime") or time_elem.get_text(strip=True)

        item = {
            "title": title,
            "link": link,
            "guid": guid,
            "pubDate": pub_date,
        }
        if description:
            item["description"] = description

        items.append(item)
        seen_guids.add(guid)
        if len(items) >= max_items:
            break

    return items


def extract_github_release_atom_items(xml: str, *, max_items: int = DEFAULT_MAX_ITEMS) -> list[dict[str, str]]:
    """Extract release entries from GitHub's releases Atom feed."""
    soup = BeautifulSoup(xml, "xml")
    items: list[dict[str, str]] = []
    seen_guids: set[str] = set()

    for entry in soup.find_all("entry"):
        title = _normalize_whitespace(entry.title.get_text(" ", strip=True)) if entry.title else ""
        link = ""
        if entry.link and entry.link.get("href"):
            link = str(entry.link.get("href")).strip()
        guid = _normalize_whitespace(entry.id.get_text(" ", strip=True)) if entry.id else link
        pub_date = ""
        if entry.updated:
            pub_date = _normalize_whitespace(entry.updated.get_text(" ", strip=True))
        elif entry.published:
            pub_date = _normalize_whitespace(entry.published.get_text(" ", strip=True))

        if not title or not link or not guid or guid in seen_guids:
            continue

        description = _extract_atom_description(entry)
        item = {
            "title": title,
            "link": link,
            "guid": guid,
        }
        if pub_date:
            item["pubDate"] = pub_date
        if description:
            item["description"] = description

        items.append(item)
        seen_guids.add(guid)
        if len(items) >= max_items:
            break

    return items


def _extract_anchor_id(container: Tag) -> str | None:
    button = container.select_one("h3 button[data-anchor-id]")
    if not button:
        return None
    anchor_id = str(button.get("data-anchor-id") or "").strip()
    return anchor_id or None


def _extract_heading_text(heading: Tag) -> str:
    heading_copy = BeautifulSoup(str(heading), "lxml")
    for button in heading_copy.select("button"):
        button.decompose()
    return _normalize_whitespace(heading_copy.get_text(" ", strip=True))


def _extract_release_link(article: Tag) -> str | None:
    for anchor in article.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        text = _normalize_whitespace(anchor.get_text(" ", strip=True)).lower()
        if not href:
            continue
        if "/releases/tag/" in href or "full release" in text:
            return href
    return None


def _extract_description(article: Tag) -> str:
    article_copy = BeautifulSoup(str(article), "lxml")
    for selector in ("button", "img", "pre", "script", "style", "svg"):
        for element in article_copy.select(selector):
            element.decompose()
    for summary in article_copy.select("summary"):
        summary.decompose()

    lines: list[str] = []
    for raw_line in article_copy.get_text("\n", strip=True).splitlines():
        line = _normalize_whitespace(raw_line)
        if not line or line == "View details" or line == "Full release on Github":
            continue
        if lines and line == lines[-1]:
            continue
        lines.append(line)

    return "\n".join(lines)


def _extract_atom_description(entry: Tag) -> str:
    html = ""
    if entry.content:
        html = entry.content.get_text("", strip=False)
    elif entry.summary:
        html = entry.summary.get_text("", strip=False)
    if not html:
        return ""

    content_soup = BeautifulSoup(html, "lxml")
    lines: list[str] = []
    for raw_line in content_soup.get_text("\n", strip=True).splitlines():
        line = _normalize_whitespace(raw_line)
        if not line:
            continue
        if lines and line == lines[-1]:
            continue
        lines.append(line)
    return "\n".join(lines)


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


@register_job
class CodexChangelogJob(FeedJob):
    """Build an RSS feed from the official Codex changelog page."""

    job_type = "codex_changelog"

    def run(self, context: JobContext) -> JobResult:
        url = str(self.config.get("url") or DEFAULT_SOURCE_URL)
        fallback_atom_url = str(self.config.get("fallback_atom_url") or DEFAULT_FALLBACK_ATOM_URL)
        output_file = str(self.config.get("output") or DEFAULT_OUTPUT)
        options = self.config.get("options") or {}

        scraper = WebScraper(
            timeout=options.get("timeout", 15),
            user_agent=options.get("user_agent"),
            retries=options.get("retries", 2),
            backoff_factor=options.get("backoff_factor", 0.5),
        )
        max_items = int(options.get("max_items", DEFAULT_MAX_ITEMS))
        html = scraper.fetch(url, encoding=options.get("encoding"))
        items: list[dict[str, str]] = []
        if html:
            items = extract_codex_changelog_items(
                html,
                url,
                anchor_prefixes=self.config.get("anchor_prefixes"),
                max_items=max_items,
            )

        if not items and fallback_atom_url:
            logger.info("Codex changelog 页面不可用或未命中 release 条目，回退到 GitHub Releases Atom feed")
            atom_xml = scraper.fetch(fallback_atom_url, encoding=options.get("encoding"))
            if atom_xml:
                items = extract_github_release_atom_items(atom_xml, max_items=max_items)

        if not items:
            return JobResult(name=self.name, success=False, details="抓取 changelog 页面和 GitHub Releases Atom feed 均失败，或未解析到条目")

        output_path = resolve_output_path(context.feeds_dir, output_file)
        generator = RSSGenerator(
            title=str(self.config.get("title") or DEFAULT_TITLE),
            link=str(self.config.get("link") or DEFAULT_LINK),
            description=str(self.config.get("description") or DEFAULT_DESCRIPTION),
        )
        generator.add_items(items)
        success = generator.generate(str(output_path))
        details = f"输出: {Path(output_path).name}" if success else "RSS 生成失败"
        return JobResult(name=self.name, success=success, details=details)
