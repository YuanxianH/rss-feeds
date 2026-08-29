"""Generic CMS/JSON article records used by dynamic-site jobs."""

from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urljoin

_TITLE_FIELDS = ("title", "name", "headline")
_DESCRIPTION_FIELDS = ("resume", "summary", "description", "excerpt", "abstract")
_DATE_KEYS = (
    "createAt",
    "createdAt",
    "publishedAt",
    "datePublished",
    "date",
    "pubDate",
)
_PATH_KEYS = ("url", "href", "permalink", "path", "slug")


def numeric_id(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def first_text(doc: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def localized_text(doc: dict[str, Any], field: str, locale: str = "") -> str:
    keys: list[str] = []
    if locale:
        keys.append(f"{field}_{locale}")
    keys.extend((field, f"{field}_zh", f"{field}_en"))
    return first_text(doc, keys)


def _tag_names(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, list):
        return []

    names: list[str] = []
    for tag in value:
        if isinstance(tag, str) and tag.strip():
            names.append(tag.strip())
            continue
        if isinstance(tag, dict):
            text = first_text(
                tag, ("name", "title", "label", "name_zh", "title_zh")
            )
            if text:
                names.append(text)
    return names


def is_article_record(
    doc: Any,
    *,
    category: str = "",
    require_active: bool = False,
) -> bool:
    """Return whether a JSON object looks like a public article record."""
    if not isinstance(doc, dict):
        return False
    if not any(localized_text(doc, field) for field in _TITLE_FIELDS):
        return False
    has_id = numeric_id(doc.get("id")) is not None
    has_path = any(
        isinstance(doc.get(key), str) and str(doc.get(key)).strip()
        for key in _PATH_KEYS
    )
    if not has_id and not has_path:
        return False
    if category:
        record_category = str(doc.get("category") or doc.get("type") or "").strip()
        if record_category and record_category.lower() != category.lower():
            return False
    if require_active and "active" in doc and doc.get("active") is not True:
        return False
    return True


def record_url(doc: dict[str, Any], *, page_url: str, path_prefix: str) -> str | None:
    """Build an article URL from a path field or a numeric CMS id."""
    for key in _PATH_KEYS:
        raw = doc.get(key)
        if isinstance(raw, str) and raw.strip():
            value = raw.strip()
            if value.startswith(("http://", "https://", "/")):
                return urljoin(page_url, value)
            prefix = "/" + path_prefix.strip("/")
            return urljoin(page_url, f"{prefix}/{value.lstrip('/')}")

    article_id = numeric_id(doc.get("id"))
    if article_id is None or not path_prefix.strip():
        return None
    prefix = "/" + path_prefix.strip("/")
    return urljoin(page_url, f"{prefix}/{article_id}")


def record_to_item(
    doc: dict[str, Any],
    *,
    page_url: str,
    path_prefix: str,
    locale: str = "",
    normalize_url=None,
) -> dict[str, str] | None:
    """Convert a CMS record into an RSS item."""
    raw_url = record_url(doc, page_url=page_url, path_prefix=path_prefix)
    if not raw_url:
        return None
    link = normalize_url(raw_url, page_url) if normalize_url else raw_url
    title = next(
        (
            text
            for field in _TITLE_FIELDS
            if (text := localized_text(doc, field, locale))
        ),
        "",
    )
    if not link or not title:
        return None

    description = next(
        (
            text
            for field in _DESCRIPTION_FIELDS
            if (text := localized_text(doc, field, locale))
        ),
        "",
    )
    if not description:
        tags = _tag_names(
            (doc.get(f"tag_{locale}") if locale else None)
            or doc.get("tag")
            or doc.get("tag_zh")
            or doc.get("tag_en")
            or doc.get("tags")
        )
        description = " · ".join(tags)

    item = {"title": title, "link": link, "guid": link}
    if description:
        item["description"] = description
    published = first_text(doc, _DATE_KEYS)
    if published:
        item["pubDate"] = published
    return item


def iter_article_records(value: Any) -> Iterable[dict[str, Any]]:
    """Yield dicts that look like articles from a nested JSON payload."""
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if is_article_record(current):
                yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def collect_article_records(
    payload: Any,
    *,
    category: str = "",
    require_active: bool = False,
) -> list[dict[str, Any]]:
    """Collect unique article records, preferring Payload-style ``docs`` lists."""
    records: list[dict[str, Any]] = []
    seen: set[tuple[Any, str]] = set()

    candidates: Iterable[Any]
    if isinstance(payload, dict) and isinstance(payload.get("docs"), list):
        candidates = payload["docs"]
    else:
        candidates = iter_article_records(payload)

    for doc in candidates:
        if not is_article_record(
            doc, category=category, require_active=require_active
        ):
            continue
        key = (doc.get("id"), localized_text(doc, "title"))
        if key in seen:
            continue
        seen.add(key)
        records.append(doc)
    return records
