"""Shared article metadata extraction for site-backed RSS jobs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from src.discovery import UrlNormalizer


def _parse_datetime(candidate: str) -> datetime | None:
    if not candidate or not candidate.strip():
        return None
    normalized = (
        candidate.strip()
        .replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace(".", "-")
        .replace("/", "-")
    )
    try:
        parsed = date_parser.parse(normalized, fuzzy=True)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _first_meta(
    soup: BeautifulSoup,
    candidates: list[tuple[str, str]],
) -> str | None:
    for attr_name, attr_value in candidates:
        tag = soup.find("meta", attrs={attr_name: attr_value})
        content = str(tag.get("content") or "").strip() if tag else ""
        if content:
            return content
    return None


def _extract_json_ld(soup: BeautifulSoup) -> list[Any]:
    entries: list[Any] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        entries.extend(parsed if isinstance(parsed, list) else [parsed])
    return entries


def _iter_dicts(value: Any):
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _extract_publish_date(soup: BeautifulSoup) -> str | None:
    candidates: list[str] = []
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
        candidates.append(meta_date)

    candidates.extend(
        str(time_tag.get("datetime") or time_tag.get_text(strip=True))
        for time_tag in soup.select("time")
    )
    for payload in _extract_json_ld(soup):
        for obj in _iter_dicts(payload):
            candidates.extend(
                value
                for key in ("datePublished", "dateCreated", "uploadDate")
                if isinstance((value := obj.get(key)), str)
            )

    text = soup.get_text(" ", strip=True)
    candidates.extend(
        re.findall(
            r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}"
            r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?",
            text,
        )
    )
    for candidate in candidates:
        parsed = _parse_datetime(candidate)
        if parsed is not None:
            return parsed.isoformat()
    return None


def _default_normalize(raw_url: str, base_url: str) -> str | None:
    absolute = urljoin(base_url, raw_url)
    parsed = urlparse(absolute)
    return absolute if parsed.scheme in ("http", "https") and parsed.netloc else None


def extract_article_item(
    url: str,
    html: str,
    *,
    response_url: str | None = None,
    normalize_url: UrlNormalizer | None = None,
) -> dict[str, str] | None:
    """Extract a normalized RSS item from an article page."""
    soup = BeautifulSoup(html, "html.parser")
    effective_url = response_url or url
    normalizer = normalize_url or _default_normalize
    normalized_effective_url = normalizer(effective_url, url)
    if not normalized_effective_url:
        return None

    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical_url = str(canonical_tag.get("href") or "") if canonical_tag else ""
    og_url = _first_meta(soup, [("property", "og:url")]) or ""
    link = (
        normalizer(canonical_url, effective_url)
        or normalizer(og_url, effective_url)
        or normalized_effective_url
    )

    title = _first_meta(
        soup,
        [
            ("property", "og:title"),
            ("name", "twitter:title"),
            ("name", "title"),
        ],
    )
    if not title and (heading := soup.select_one("h1")):
        title = heading.get_text(" ", strip=True)
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    if not title:
        slug = urlparse(link).path.rsplit("/", 1)[-1]
        title = slug.replace("-", " ").strip().title()
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
    if not description and (paragraph := soup.select_one("article p, main p")):
        description = paragraph.get_text(" ", strip=True)

    item = {"title": title, "link": link}
    if description:
        item["description"] = description
    if published := _extract_publish_date(soup):
        item["pubDate"] = published
    if author := _first_meta(
        soup,
        [("name", "author"), ("property", "article:author")],
    ):
        item["author"] = author
    return item
