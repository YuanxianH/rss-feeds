"""Static landing page generator for the deployed RSS network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape
import logging
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

SECTION_ORDER = ("research", "blogs", "releases")
SECTION_META = {
    "research": {
        "title": "Research",
        "description": "Publications, lab notes, and filtered research streams.",
    },
    "blogs": {
        "title": "Blogs",
        "description": "Company blogs, engineering writing, and product news.",
    },
    "releases": {
        "title": "Releases",
        "description": "Model drops, repositories, and release-oriented feeds.",
    },
}

DEFAULT_SITE = {
    "title": "AI RSS Network",
    "url": "https://yuanxianh.github.io/rss-feeds/",
    "tagline": "A deployed RSS network for AI labs, research groups, and release channels.",
    "description": "Browse and subscribe to curated RSS feeds for AI research publications, engineering blogs, and product release streams.",
}


@dataclass(frozen=True)
class FeedCard:
    """Rendered feed metadata for the landing page."""

    title: str
    description: str
    section: str
    source_url: str
    source_label: str
    rss_path: str
    last_build_display: str
    last_build_sort: datetime | None
    rss_available: bool


def generate_site_index(config: dict, feeds_dir: str) -> Path:
    """Generate the subscriber-facing landing page inside feeds/."""
    feeds_path = Path(feeds_dir)
    feeds_path.mkdir(parents=True, exist_ok=True)

    site = {**DEFAULT_SITE, **(config.get("site") or {})}
    jobs = [job for job in config.get("jobs", []) if job.get("enabled", True)]

    grouped_cards = {section: [] for section in SECTION_ORDER}
    latest_build: datetime | None = None

    for job in jobs:
        card = _build_feed_card(job, feeds_path)
        grouped_cards[card.section].append(card)
        if card.last_build_sort and (
            latest_build is None or card.last_build_sort > latest_build
        ):
            latest_build = card.last_build_sort

    output_path = feeds_path / "index.html"
    output_path.write_text(
        _render_page(site, grouped_cards, latest_build, len(jobs)),
        encoding="utf-8",
    )
    logger.info("Generated landing page: %s", output_path)
    return output_path


def _build_feed_card(job: dict, feeds_path: Path) -> FeedCard:
    output_name = str(job.get("output") or "").strip()
    xml_path = feeds_path / output_name if output_name else None
    channel_meta = _read_channel_metadata(xml_path) if xml_path else {}

    section = _normalize_section((job.get("catalog") or {}).get("section"))
    source_url = _resolve_source_url(job, channel_meta)
    last_build_raw = channel_meta.get("lastBuildDate") or ""
    last_build = _parse_datetime(last_build_raw)

    return FeedCard(
        title=str(
            job.get("title")
            or channel_meta.get("title")
            or job.get("name")
            or output_name
            or "Untitled feed"
        ),
        description=str(
            job.get("description")
            or channel_meta.get("description")
            or "RSS feed"
        ),
        section=section,
        source_url=source_url,
        source_label=_source_label(source_url),
        rss_path=output_name,
        last_build_display=_format_datetime(last_build) if last_build else "Awaiting first build",
        last_build_sort=last_build,
        rss_available=bool(output_name and xml_path and xml_path.exists()),
    )


def _normalize_section(value: str | None) -> str:
    if value in SECTION_META:
        return value
    return "blogs"


def _resolve_source_url(job: dict, channel_meta: dict[str, str]) -> str:
    for key in ("link", "url"):
        value = str(job.get(key) or "").strip()
        if value:
            return value
    xml_link = str(channel_meta.get("link") or "").strip()
    if xml_link:
        return xml_link
    for key in ("source_url", "base_url", "api_url"):
        value = str(job.get(key) or "").strip()
        if value:
            return value
    return str(channel_meta.get("link") or "").strip()


def _source_label(url: str) -> str:
    if not url:
        return "Source site"
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    return host.removeprefix("www.") or "Source site"


def _read_channel_metadata(xml_path: Path | None) -> dict[str, str]:
    if not xml_path or not xml_path.exists():
        return {}

    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as exc:
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
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def _render_page(
    site: dict,
    grouped_cards: dict[str, list[FeedCard]],
    latest_build: datetime | None,
    total_feeds: int,
) -> str:
    section_count = sum(1 for section in SECTION_ORDER if grouped_cards[section])
    latest_display = _format_datetime(latest_build) if latest_build else "Awaiting first build"

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <style>
    :root {{
      --paper: #f6f1e8;
      --paper-strong: #efe4d3;
      --ink: #17211d;
      --muted: #55615b;
      --line: rgba(23, 33, 29, 0.14);
      --teal: #116466;
      --orange: #c96a34;
      --card: rgba(255, 252, 248, 0.88);
      --shadow: 0 18px 45px rgba(23, 33, 29, 0.08);
      --radius: 24px;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(17, 100, 102, 0.12), transparent 32%),
        radial-gradient(circle at top right, rgba(201, 106, 52, 0.12), transparent 28%),
        linear-gradient(180deg, #fbf7f0 0%, var(--paper) 45%, #f2ebdf 100%);
      font-family: "Avenir Next", "Helvetica Neue", sans-serif;
    }}

    a {{
      color: inherit;
    }}

    .page {{
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 32px 0 64px;
    }}

    .hero {{
      position: relative;
      overflow: hidden;
      padding: 32px;
      border: 1px solid var(--line);
      border-radius: 32px;
      background: rgba(255, 250, 244, 0.86);
      box-shadow: var(--shadow);
    }}

    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -10% -25% auto;
      width: 340px;
      height: 340px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(17, 100, 102, 0.18), transparent 68%);
      pointer-events: none;
    }}

    .eyebrow,
    .meta-kicker {{
      letter-spacing: 0.16em;
      text-transform: uppercase;
      font-size: 0.78rem;
      color: var(--teal);
      margin: 0 0 14px;
    }}

    h1,
    h2,
    h3 {{
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      font-weight: 600;
      margin: 0;
    }}

    h1 {{
      max-width: 13ch;
      font-size: clamp(2.6rem, 5vw, 5rem);
      line-height: 0.96;
      letter-spacing: -0.04em;
    }}

    .hero-grid {{
      position: relative;
      display: grid;
      gap: 28px;
      grid-template-columns: minmax(0, 1.3fr) minmax(280px, 0.9fr);
      z-index: 1;
    }}

    .hero-copy p {{
      max-width: 60ch;
      margin: 18px 0 0;
      color: var(--muted);
      font-size: 1.02rem;
      line-height: 1.7;
    }}

    .hero-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 26px;
    }}

    .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 13px 18px;
      border-radius: 999px;
      border: 1px solid transparent;
      text-decoration: none;
      font-weight: 600;
    }}

    .button-primary {{
      background: var(--ink);
      color: #fff;
    }}

    .button-secondary {{
      border-color: var(--line);
      background: rgba(255, 255, 255, 0.58);
    }}

    .stats {{
      display: grid;
      gap: 12px;
      align-content: start;
    }}

    .stat {{
      padding: 18px 20px;
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.62);
      backdrop-filter: blur(12px);
    }}

    .stat-label {{
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
    }}

    .stat-value {{
      margin-top: 8px;
      font-size: 1.35rem;
      line-height: 1.2;
      font-weight: 700;
    }}

    .network-map {{
      margin-top: 28px;
      padding: 26px 28px;
      border: 1px solid var(--line);
      border-radius: 28px;
      background: rgba(255, 250, 244, 0.78);
    }}

    .network-map p {{
      margin: 10px 0 0;
      color: var(--muted);
      max-width: 60ch;
      line-height: 1.65;
    }}

    .map-grid {{
      margin-top: 22px;
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}

    .map-node {{
      padding: 18px;
      border-radius: 22px;
      border: 1px solid var(--line);
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.46)),
        linear-gradient(180deg, rgba(17, 100, 102, 0.05), rgba(201, 106, 52, 0.02));
    }}

    .map-node strong {{
      display: block;
      font-size: 1.05rem;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
    }}

    .map-node span {{
      display: block;
      margin-top: 8px;
      color: var(--muted);
      line-height: 1.6;
    }}

    .sections {{
      margin-top: 28px;
      display: grid;
      gap: 24px;
    }}

    .feed-section {{
      padding: 28px;
      border-radius: 28px;
      border: 1px solid var(--line);
      background: rgba(255, 253, 248, 0.82);
      box-shadow: var(--shadow);
    }}

    .section-header {{
      display: grid;
      gap: 10px;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: end;
      margin-bottom: 20px;
    }}

    .section-header p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
      max-width: 58ch;
    }}

    .section-count {{
      padding: 9px 14px;
      border-radius: 999px;
      background: rgba(17, 100, 102, 0.08);
      color: var(--teal);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }}

    .feed-grid {{
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}

    .feed-card {{
      padding: 22px;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: var(--card);
      display: grid;
      gap: 16px;
      align-content: start;
    }}

    .feed-card h3 {{
      font-size: 1.35rem;
      line-height: 1.12;
    }}

    .feed-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }}

    .feed-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      font-size: 0.84rem;
      color: var(--muted);
    }}

    .feed-meta span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(23, 33, 29, 0.06);
    }}

    .feed-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}

    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      text-decoration: none;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.84);
    }}

    .chip-accent {{
      border-color: rgba(17, 100, 102, 0.18);
      background: rgba(17, 100, 102, 0.08);
      color: var(--teal);
    }}

    .chip-muted {{
      color: var(--muted);
      background: rgba(23, 33, 29, 0.05);
    }}

    .mono {{
      font-family: "SFMono-Regular", "JetBrains Mono", "Fira Code", monospace;
      font-size: 0.9rem;
    }}

    footer {{
      margin-top: 24px;
      padding: 18px 4px 0;
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.65;
    }}

    @media (max-width: 980px) {{
      .hero-grid,
      .feed-grid,
      .map-grid {{
        grid-template-columns: 1fr;
      }}

      .section-header {{
        grid-template-columns: 1fr;
        align-items: start;
      }}
    }}

    @media (max-width: 640px) {{
      .page {{
        width: min(100vw - 20px, 1180px);
        padding-top: 20px;
      }}

      .hero,
      .network-map,
      .feed-section {{
        padding: 22px;
      }}

      .hero-actions,
      .feed-actions {{
        flex-direction: column;
      }}

      .button,
      .chip {{
        width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="hero-grid">
        <div class="hero-copy">
          <p class="eyebrow">Deployed RSS Network</p>
          <h1>{title}</h1>
          <p><strong>{tagline}</strong></p>
          <p>{description}</p>
          <div class="hero-actions">
            <a class="button button-primary" href="{site_url}">Open deployed homepage</a>
            <a class="button button-secondary" href="#section-research">Browse feeds</a>
          </div>
        </div>
        <aside class="stats" aria-label="Network stats">
          <div class="stat">
            <div class="stat-label">Feeds</div>
            <div class="stat-value">{total_feeds}</div>
          </div>
          <div class="stat">
            <div class="stat-label">Sections</div>
            <div class="stat-value">{section_count}</div>
          </div>
          <div class="stat">
            <div class="stat-label">Latest build</div>
            <div class="stat-value">{latest_display}</div>
          </div>
        </aside>
      </div>
    </section>

    <section class="network-map" aria-labelledby="network-map-title">
      <p class="meta-kicker">Network map</p>
      <h2 id="network-map-title">A single entrypoint for AI research, blogs, and release streams</h2>
      <p>The landing page is generated from the repository configuration and feed metadata, so the deployed catalog stays aligned with the feeds published to GitHub Pages.</p>
      <div class="map-grid">
        {map_nodes}
      </div>
    </section>

    <div class="sections">
      {sections}
    </div>

    <footer>
      Generated from <span class="mono">config.yaml</span> and the current feed XML files in <span class="mono">feeds/</span>. Published at <a href="{site_url}">{site_url}</a>.
    </footer>
  </main>
</body>
</html>
""".format(
        title=escape(str(site.get("title") or DEFAULT_SITE["title"])),
        description=escape(str(site.get("description") or DEFAULT_SITE["description"])),
        tagline=escape(str(site.get("tagline") or DEFAULT_SITE["tagline"])),
        site_url=escape(str(site.get("url") or DEFAULT_SITE["url"])),
        total_feeds=total_feeds,
        section_count=section_count,
        latest_display=escape(latest_display),
        map_nodes=_render_map_nodes(grouped_cards),
        sections=_render_sections(grouped_cards),
    )


def _render_map_nodes(grouped_cards: dict[str, list[FeedCard]]) -> str:
    parts = []
    for section in SECTION_ORDER:
        meta = SECTION_META[section]
        parts.append(
            """
        <article class="map-node">
          <strong>{title}</strong>
          <span>{count} feed{suffix}</span>
          <span>{description}</span>
        </article>""".format(
                title=escape(meta["title"]),
                count=len(grouped_cards[section]),
                suffix="" if len(grouped_cards[section]) == 1 else "s",
                description=escape(meta["description"]),
            )
        )
    return "".join(parts)


def _render_sections(grouped_cards: dict[str, list[FeedCard]]) -> str:
    return "".join(_render_section(section, grouped_cards[section]) for section in SECTION_ORDER)


def _render_section(section: str, cards: list[FeedCard]) -> str:
    meta = SECTION_META[section]
    cards_html = "".join(_render_card(card) for card in cards) or """
        <article class="feed-card">
          <h3>No feed published yet</h3>
          <p>This section is configured, but no feed file has been generated yet.</p>
        </article>"""

    return """
    <section class="feed-section" id="section-{section}">
      <div class="section-header">
        <div>
          <p class="meta-kicker">{title}</p>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <div class="section-count">{count} feed{suffix}</div>
      </div>
      <div class="feed-grid">
        {cards}
      </div>
    </section>""".format(
        section=escape(section),
        title=escape(meta["title"]),
        description=escape(meta["description"]),
        count=len(cards),
        suffix="" if len(cards) == 1 else "s",
        cards=cards_html,
    )


def _render_card(card: FeedCard) -> str:
    rss_action = (
        '<a class="chip chip-accent" href="{rss_path}">Subscribe to RSS</a>'.format(
            rss_path=escape(card.rss_path)
        )
        if card.rss_available
        else '<span class="chip chip-muted">Feed file unavailable</span>'
    )

    source_action = (
        '<a class="chip" href="{source_url}">Visit source</a>'.format(
            source_url=escape(card.source_url)
        )
        if card.source_url
        else '<span class="chip chip-muted">Source unavailable</span>'
    )

    return """
        <article class="feed-card">
          <div>
            <h3>{title}</h3>
          </div>
          <p>{description}</p>
          <div class="feed-meta">
            <span>Source: <strong>{source_label}</strong></span>
            <span>Latest build: <strong>{last_build}</strong></span>
          </div>
          <div class="feed-actions">
            {rss_action}
            {source_action}
          </div>
        </article>""".format(
        title=escape(card.title),
        description=escape(card.description),
        source_label=escape(card.source_label),
        last_build=escape(card.last_build_display),
        rss_action=rss_action,
        source_action=source_action,
    )
