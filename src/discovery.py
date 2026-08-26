"""Reusable URL discovery helpers for dynamic and partially rendered sites."""

from __future__ import annotations

from collections import deque
import json
import logging
import re
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

UrlNormalizer = Callable[[str, str], str | None]

_ASSET_SUFFIXES = {
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".map",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
    ".xml",
}


def make_url_normalizer(
    *,
    allowed_hosts: Iterable[str],
    path_prefix: str,
) -> UrlNormalizer:
    """Build a normalizer constrained to known hosts and an article path."""
    hosts = tuple(
        host.lower().split(":", 1)[0].lstrip(".")
        for host in allowed_hosts
        if str(host).strip()
    )
    prefix = "/" + path_prefix.strip("/")

    def normalize(raw_url: str, base_url: str) -> str | None:
        if not raw_url:
            return None
        absolute = urljoin(base_url, str(raw_url).strip())
        parsed = urlparse(absolute)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https"):
            return None
        if not hostname or not any(
            hostname == host or hostname.endswith(f".{host}") for host in hosts
        ):
            return None

        path = parsed.path.rstrip("/")
        if path == prefix or not path.startswith(f"{prefix}/"):
            return None
        if any(character.isspace() for character in path):
            return None
        if any(path.lower().endswith(suffix) for suffix in _ASSET_SUFFIXES):
            return None

        return urlunparse(
            parsed._replace(path=path, params="", query="", fragment="")
        )

    return normalize


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


def extract_article_urls(
    html: str,
    *,
    page_url: str,
    normalize_url: UrlNormalizer,
    link_selector: str = "a[href]",
) -> list[str]:
    """Discover article URLs from anchors, metadata, embedded JSON and text."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        normalized = normalize_url(candidate, page_url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)

    for anchor in soup.select(link_selector):
        add(anchor.get("href", ""))

    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical:
        add(canonical.get("href", ""))
    for property_name in ("og:url", "twitter:url"):
        meta = soup.find("meta", attrs={"property": property_name})
        if meta:
            add(meta.get("content", ""))

    for script in soup.find_all("script"):
        raw_text = script.string or script.get_text()
        if not raw_text:
            continue
        script_id = str(script.get("id") or "")
        script_type = str(script.get("type") or "")
        if script_id == "__NEXT_DATA__" or script_type in (
            "application/json",
            "application/ld+json",
        ):
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                continue
            for value in _iter_json_strings(payload):
                add(value)

    # Next.js flight data and similar payloads often contain escaped URLs in
    # non-JSON script tags. Keep this last so visible links retain their order.
    searchable = html.replace("\\\\/", "/").replace("\\/", "/")
    prefix = urlparse(page_url).path.rstrip("/")
    if prefix:
        path_pattern = re.escape(prefix) + r"/[A-Za-z0-9][A-Za-z0-9._~%/-]*"
        candidate_pattern = (
            r"(?:https?://[A-Za-z0-9.-]+(?::\d+)?)?" + path_pattern
        )
        for match in re.findall(candidate_pattern, searchable):
            add(match)

    return urls


def discover_sitemap_urls(
    session: requests.Session,
    sitemap_urls: Iterable[str],
    *,
    normalize_url: UrlNormalizer,
    timeout: float,
    max_files: int = 20,
    logger: logging.Logger | None = None,
) -> list[str]:
    """Walk sitemap indexes and return article URLs accepted by a normalizer."""
    log = logger or logging.getLogger(__name__)
    queue = deque(str(url) for url in sitemap_urls if str(url).strip())
    seen_sitemaps: set[str] = set()
    article_urls: list[str] = []
    seen_articles: set[str] = set()

    while queue and len(seen_sitemaps) < max_files:
        sitemap_url = queue.popleft()
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)

        try:
            response = session.get(sitemap_url, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            log.warning("读取 sitemap 失败 %s: %s", sitemap_url, exc)
            continue

        try:
            root = ET.fromstring(response.text)
            locations = [
                (node.text or "").strip()
                for node in root.iter()
                if node.tag.rsplit("}", 1)[-1] == "loc" and (node.text or "").strip()
            ]
        except ET.ParseError:
            locations = re.findall(r"https?://[^\s<>\"]+", response.text)

        for location in locations:
            normalized = normalize_url(location, sitemap_url)
            if normalized:
                if normalized not in seen_articles:
                    seen_articles.add(normalized)
                    article_urls.append(normalized)
                continue
            if urlparse(location).path.lower().endswith(".xml"):
                queue.append(location)

    return article_urls
