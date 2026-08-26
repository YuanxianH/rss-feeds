"""Generate the small, static directory deployed alongside RSS feeds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape
import logging
from pathlib import Path
import re
import shutil
from string import Template
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

SECTION_ORDER = ("research", "blogs", "releases")
SECTION_META = {
    "research": ("Research", "Publications and lab notes."),
    "blogs": ("Blogs", "Engineering, product, and company writing."),
    "releases": ("Releases", "Models, repositories, and release streams."),
}
DEFAULT_SITE = {
    "title": "AI RSS Network",
    "url": "https://yuanxianh.github.io/rss-feeds/",
    "tagline": "Curated feeds from AI labs and research groups.",
    "description": "Subscribe to AI research, engineering, and release feeds.",
}
STALE_AFTER = timedelta(days=2)
SOURCE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = SOURCE_DIR / "templates" / "index.html"
STYLESHEET_PATH = SOURCE_DIR / "site_assets" / "site.css"


@dataclass(frozen=True)
class FeedCard:
    anchor_id: str
    title: str
    description: str
    section: str
    source_url: str
    rss_path: str
    updated_display: str
    updated_iso: str
    updated_sort: datetime | None
    rss_available: bool
    status_label: str
    status_class: str
    sort_rank: int


def generate_site_index(config: dict, feeds_dir: str) -> Path:
    """Render the directory and copy its static stylesheet."""
    feeds_path = Path(feeds_dir)
    feeds_path.mkdir(parents=True, exist_ok=True)
    assets_path = feeds_path / "assets"
    assets_path.mkdir(exist_ok=True)
    shutil.copyfile(STYLESHEET_PATH, assets_path / "site.css")

    site = {**DEFAULT_SITE, **(config.get("site") or {})}
    jobs = [job for job in config.get("jobs", []) if job.get("enabled", True)]
    grouped_cards = {section: [] for section in SECTION_ORDER}
    all_cards: list[FeedCard] = []
    now = datetime.now(timezone.utc)

    for job in jobs:
        card = _build_feed_card(job, feeds_path, now=now)
        grouped_cards[card.section].append(card)
        all_cards.append(card)

    grouped_cards = {
        section: _sort_cards(grouped_cards[section]) for section in SECTION_ORDER
    }
    latest_build = max(
        (card.updated_sort for card in all_cards if card.updated_sort),
        default=None,
    )
    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    output_path = feeds_path / "index.html"
    output_path.write_text(
        template.substitute(
            lang=escape(str(site.get("lang") or "en")),
            title=escape(str(site["title"])),
            description=escape(str(site["description"])),
            tagline=escape(str(site["tagline"])),
            site_url=escape(str(site["url"]), quote=True),
            latest_build=escape(
                _format_datetime(latest_build) if latest_build else "Awaiting first build"
            ),
            section_nav=_render_section_nav(grouped_cards),
            sections=_render_sections(grouped_cards),
        ),
        encoding="utf-8",
    )
    logger.info("Generated landing page: %s", output_path)
    return output_path


def _build_feed_card(job: dict, feeds_path: Path, *, now: datetime) -> FeedCard:
    output_name = str(job.get("output") or "").strip()
    xml_path = feeds_path / output_name if output_name else None
    channel_meta = _read_channel_metadata(xml_path) if xml_path else {}
    section = _normalize_section((job.get("catalog") or {}).get("section"))
    rss_available = bool(output_name and xml_path and xml_path.exists())
    updated_sort = _parse_datetime(channel_meta.get("lastBuildDate") or "")
    status_label, status_class, sort_rank, updated_display = _status_metadata(
        rss_available=rss_available,
        updated_sort=updated_sort,
        now=now,
    )
    return FeedCard(
        anchor_id=_feed_anchor_id(
            output_name=output_name,
            title=job.get("title") or job.get("name"),
            section=section,
        ),
        title=_normalize_text(
            str(
                job.get("title")
                or channel_meta.get("title")
                or job.get("name")
                or output_name
                or "Untitled feed"
            )
        ),
        description=_normalize_text(
            str(job.get("description") or channel_meta.get("description") or "RSS feed")
        ),
        section=section,
        source_url=_resolve_source_url(job, channel_meta),
        rss_path=output_name,
        updated_display=updated_display,
        updated_iso=updated_sort.isoformat() if updated_sort else "",
        updated_sort=updated_sort,
        rss_available=rss_available,
        status_label=status_label,
        status_class=status_class,
        sort_rank=sort_rank,
    )


def _status_metadata(
    *,
    rss_available: bool,
    updated_sort: datetime | None,
    now: datetime,
) -> tuple[str, str, int, str]:
    if not rss_available:
        return ("Unavailable", "is-unavailable", 3, "Awaiting build")
    if updated_sort is None:
        return ("Live", "is-live", 1, "Unknown")
    if now - updated_sort > STALE_AFTER:
        return ("Stale", "is-stale", 2, _format_datetime(updated_sort))
    return ("Live", "is-live", 0, _format_datetime(updated_sort))


def _sort_cards(cards: list[FeedCard]) -> list[FeedCard]:
    return sorted(
        cards,
        key=lambda card: (
            card.sort_rank,
            -(card.updated_sort.timestamp()) if card.updated_sort else 0,
            card.title.lower(),
        ),
    )


def _normalize_section(value: str | None) -> str:
    return value if value in SECTION_META else "blogs"


def _feed_anchor_id(*, output_name: str, title: str | None, section: str) -> str:
    base = Path(output_name).stem if output_name else str(title or "feed")
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "feed"
    return f"feed-{section}-{slug}"


def _resolve_source_url(job: dict, channel_meta: dict[str, str]) -> str:
    for key in ("link", "url"):
        if value := str(job.get(key) or "").strip():
            return value
    if value := str(channel_meta.get("link") or "").strip():
        return value
    for key in ("source_url", "base_url", "api_url"):
        if value := str(job.get(key) or "").strip():
            return value
    return ""


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _read_channel_metadata(xml_path: Path | None) -> dict[str, str]:
    if not xml_path or not xml_path.exists():
        return {}
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError) as exc:
        logger.warning("Failed to parse %s: %s", xml_path, exc)
        return {}
    channel = root.find("channel")
    if channel is None:
        return {}
    return {
        "title": channel.findtext("title", default="").strip(),
        "link": channel.findtext("link", default="").strip(),
        "description": channel.findtext("description", default="").strip(),
        "lastBuildDate": channel.findtext("lastBuildDate", default="").strip(),
    }


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def _render_section_nav(grouped_cards: dict[str, list[FeedCard]]) -> str:
    links = []
    for section in SECTION_ORDER:
        title, _ = SECTION_META[section]
        links.append(
            '<a href="#section-{section}">{title}<span>{count}</span></a>'.format(
                section=escape(section),
                title=escape(title),
                count=len(grouped_cards[section]),
            )
        )
    return "".join(links)


def _render_sections(grouped_cards: dict[str, list[FeedCard]]) -> str:
    return "".join(
        _render_section(section, grouped_cards[section]) for section in SECTION_ORDER
    )


def _render_section(section: str, cards: list[FeedCard]) -> str:
    title, description = SECTION_META[section]
    rows = "".join(_render_row(card) for card in cards)
    if not rows:
        rows = '<p class="empty">No feeds configured.</p>'
    return """
      <section class="feed-section" id="section-{section}" aria-labelledby="heading-{section}">
        <header class="section-heading">
          <h2 id="heading-{section}">{title}</h2>
          <p>{description}</p>
        </header>
        <div class="feed-list">{rows}</div>
      </section>""".format(
        section=escape(section),
        title=escape(title),
        description=escape(description),
        rows=rows,
    )


def _render_row(card: FeedCard) -> str:
    rss_action = (
        '<a class="action action-primary" href="{path}">RSS</a>'.format(
            path=escape(card.rss_path, quote=True)
        )
        if card.rss_available
        else '<span class="action is-disabled">RSS unavailable</span>'
    )
    source_action = (
        '<a class="action" href="{url}" rel="noopener">Source</a>'.format(
            url=escape(card.source_url, quote=True)
        )
        if card.source_url
        else '<span class="action is-disabled">Source unavailable</span>'
    )
    updated = (
        '<time datetime="{iso}">{display}</time>'.format(
            iso=escape(card.updated_iso, quote=True),
            display=escape(card.updated_display),
        )
        if card.updated_iso
        else escape(card.updated_display)
    )
    return """
          <article class="feed {status_class}" id="{anchor_id}">
            <div class="feed-copy">
              <h3>{title}</h3>
              <p>{description}</p>
              <div class="feed-meta">
                <span class="status"><span class="status-dot" aria-hidden="true"></span>{status}</span>
                <span>Updated {updated}</span>
              </div>
            </div>
            <div class="feed-actions">{rss_action}{source_action}</div>
          </article>""".format(
        status_class=escape(card.status_class),
        anchor_id=escape(card.anchor_id, quote=True),
        title=escape(card.title),
        description=escape(card.description),
        status=escape(card.status_label),
        updated=updated,
        rss_action=rss_action,
        source_action=source_action,
    )
