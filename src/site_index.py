"""Static landing page generator for the deployed RSS network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape
import logging
from pathlib import Path
import re
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

    anchor_id: str
    title: str
    description: str
    section: str
    source_url: str
    rss_path: str
    updated_display: str
    updated_sort: datetime | None
    rss_available: bool
    is_live: bool
    status_label: str
    status_class: str
    sort_rank: int


def generate_site_index(config: dict, feeds_dir: str) -> Path:
    """Generate the subscriber-facing landing page inside feeds/."""
    feeds_path = Path(feeds_dir)
    feeds_path.mkdir(parents=True, exist_ok=True)

    site = {**DEFAULT_SITE, **(config.get("site") or {})}
    jobs = [job for job in config.get("jobs", []) if job.get("enabled", True)]

    grouped_cards = {section: [] for section in SECTION_ORDER}
    all_cards: list[FeedCard] = []

    for job in jobs:
        card = _build_feed_card(job, feeds_path)
        grouped_cards[card.section].append(card)
        all_cards.append(card)

    sorted_groups = {
        section: _sort_cards(grouped_cards[section]) for section in SECTION_ORDER
    }
    latest_build = max(
        (card.updated_sort for card in all_cards if card.updated_sort is not None),
        default=None,
    )
    live_feed_count = sum(1 for card in all_cards if card.is_live)

    output_path = feeds_path / "index.html"
    output_path.write_text(
        _render_page(
            site=site,
            grouped_cards=sorted_groups,
            latest_build=latest_build,
            live_feed_count=live_feed_count,
            total_feeds=len(all_cards),
        ),
        encoding="utf-8",
    )
    logger.info("Generated landing page: %s", output_path)
    return output_path


def _build_feed_card(job: dict, feeds_path: Path) -> FeedCard:
    output_name = str(job.get("output") or "").strip()
    xml_path = feeds_path / output_name if output_name else None
    channel_meta = _read_channel_metadata(xml_path) if xml_path else {}
    source_url = _resolve_source_url(job, channel_meta)
    section = _normalize_section((job.get("catalog") or {}).get("section"))

    rss_available = bool(output_name and xml_path and xml_path.exists())
    updated_sort = _parse_datetime(channel_meta.get("lastBuildDate") or "")
    status_label, status_class, sort_rank, is_live, updated_display = _status_metadata(
        rss_available=rss_available,
        updated_sort=updated_sort,
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
        source_url=source_url,
        rss_path=output_name,
        updated_display=updated_display,
        updated_sort=updated_sort,
        rss_available=rss_available,
        is_live=is_live,
        status_label=status_label,
        status_class=status_class,
        sort_rank=sort_rank,
    )


def _status_metadata(
    *, rss_available: bool, updated_sort: datetime | None
) -> tuple[str, str, int, bool, str]:
    if not rss_available:
        return ("Unavailable", "is-unavailable", 2, False, "Awaiting build")
    if updated_sort is None:
        return ("Live", "is-live", 1, True, "Unknown")
    return ("Live", "is-live", 0, True, _format_datetime(updated_sort))


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
    if value in SECTION_META:
        return value
    return "blogs"


def _feed_anchor_id(*, output_name: str, title: str | None, section: str) -> str:
    base = Path(output_name).stem if output_name else str(title or "feed")
    slug = re.sub(r"[^a-z0-9]+", "-", str(base).lower()).strip("-") or "feed"
    return f"feed-{section}-{slug}"


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
def _normalize_text(value: str) -> str:
    return " ".join(value.split())


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
    *,
    site: dict,
    grouped_cards: dict[str, list[FeedCard]],
    latest_build: datetime | None,
    live_feed_count: int,
    total_feeds: int,
) -> str:
    latest_display = _format_datetime(latest_build) if latest_build else "Awaiting build"

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <style>
    :root {{
      --bg: #f4f4ef;
      --surface: #fcfcf8;
      --surface-muted: #f1f1eb;
      --text: #161616;
      --muted: #66675f;
      --line: #d8d8cf;
      --line-strong: #bfc1b6;
      --accent: #16584d;
      --accent-soft: rgba(22, 88, 77, 0.08);
      --danger: #8b6a34;
      --danger-soft: rgba(139, 106, 52, 0.1);
      --sidebar-width: 276px;
      --sidebar-collapsed-width: 64px;
    }}

    * {{
      box-sizing: border-box;
    }}

    html {{
      scroll-behavior: smooth;
    }}

    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Avenir Next", "Helvetica Neue", "Segoe UI", sans-serif;
    }}

    body.sidebar-open-mobile {{
      overflow: hidden;
    }}

    a {{
      color: inherit;
    }}

    .page {{
      width: min(1240px, calc(100vw - 24px));
      margin: 0 auto;
      padding: 18px 0 36px;
    }}

    .layout {{
      display: grid;
      grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
      gap: 28px;
      align-items: start;
    }}

    .sidebar {{
      position: sticky;
      top: 18px;
      max-height: calc(100vh - 36px);
      overflow: hidden auto;
      padding: 14px 14px 16px;
      border: 1px solid var(--line-strong);
      background: var(--surface);
      transition: width 180ms ease, padding 180ms ease, transform 180ms ease;
    }}

    body.sidebar-collapsed .layout {{
      grid-template-columns: var(--sidebar-collapsed-width) minmax(0, 1fr);
    }}

    body.sidebar-collapsed .sidebar {{
      padding-left: 10px;
      padding-right: 10px;
    }}

    .sidebar-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
    }}

    .sidebar-title,
    .hero-kicker,
    .section-kicker,
    .meta-key {{
      font-family: "SFMono-Regular", "JetBrains Mono", "Menlo", monospace;
      font-size: 0.74rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
    }}

    .directory-toggle {{
      appearance: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 34px;
      padding: 0 11px;
      border: 1px solid var(--line-strong);
      background: rgba(255, 255, 255, 0.72);
      color: var(--text);
      cursor: pointer;
      font: inherit;
      font-size: 0.82rem;
      font-weight: 600;
      line-height: 1;
      letter-spacing: 0.01em;
      white-space: nowrap;
      transition: border-color 160ms ease, background 160ms ease, color 160ms ease;
    }}

    .directory-toggle:hover {{
      border-color: var(--accent);
      color: var(--accent);
      background: rgba(255, 255, 255, 0.92);
    }}

    .directory-toggle__icon {{
      display: inline-grid;
      gap: 3px;
      width: 12px;
      flex: 0 0 auto;
    }}

    .directory-toggle__icon span {{
      display: block;
      width: 12px;
      height: 1.5px;
      background: currentColor;
    }}

    .directory-toggle--sidebar {{
      min-width: 34px;
      padding-left: 10px;
      padding-right: 10px;
    }}

    .sidebar-body {{
      display: grid;
      gap: 14px;
    }}

    body.sidebar-collapsed .sidebar-header {{
      justify-content: center;
      margin-bottom: 0;
    }}

    body.sidebar-collapsed .sidebar-title,
    body.sidebar-collapsed .sidebar-body {{
      display: none;
    }}

    body.sidebar-collapsed .sidebar .directory-toggle {{
      width: 42px;
      min-width: 42px;
      padding-left: 0;
      padding-right: 0;
    }}

    body.sidebar-collapsed .sidebar .directory-toggle__label {{
      display: none;
    }}

    .sidebar-group {{
      display: grid;
      gap: 8px;
    }}

    .sidebar-group h2 {{
      margin: 0;
      font-size: 0.88rem;
      font-weight: 700;
    }}

    .sidebar-group ul {{
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 6px;
    }}

    .sidebar-group a {{
      display: block;
      color: var(--muted);
      font-size: 0.86rem;
      text-decoration: none;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .sidebar-group a:hover {{
      color: var(--accent);
    }}

    .sidebar-overlay {{
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.22);
      opacity: 0;
      pointer-events: none;
      transition: opacity 180ms ease;
      z-index: 30;
    }}

    body.sidebar-open-mobile .sidebar-overlay {{
      opacity: 1;
      pointer-events: auto;
    }}

    .main {{
      min-width: 0;
    }}

    .hero {{
      display: grid;
      gap: 18px;
      grid-template-columns: minmax(0, 1fr) minmax(250px, 320px);
      align-items: start;
      padding: 18px 0 20px;
      border-bottom: 1px solid var(--line-strong);
    }}

    .hero-kicker,
    .section-kicker {{
      margin: 0 0 8px;
    }}

    .hero h1 {{
      margin: 0;
      font-size: clamp(1.9rem, 3.4vw, 2.8rem);
      line-height: 1.02;
      letter-spacing: -0.04em;
      font-weight: 700;
    }}

    .hero-tagline {{
      margin: 10px 0 0;
      max-width: 58ch;
      color: var(--muted);
      font-size: 0.98rem;
      line-height: 1.55;
    }}

    .hero-url {{
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 0.92rem;
    }}

    .hero-url a {{
      text-decoration: none;
      border-bottom: 1px solid var(--line-strong);
    }}

    .hero-actions {{
      margin-top: 14px;
    }}

    .directory-toggle--hero {{
      color: var(--accent);
      border-color: rgba(22, 88, 77, 0.28);
      background: rgba(22, 88, 77, 0.05);
    }}

    .hero-stats {{
      margin: 0;
      display: grid;
      gap: 8px;
    }}

    .stat-row {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 8px 0;
      border-bottom: 1px solid var(--line);
    }}

    .stat-row:last-child {{
      border-bottom: 0;
    }}

    .stat-row dt {{
      color: var(--muted);
      font-size: 0.84rem;
    }}

    .stat-row dd {{
      margin: 0;
      text-align: right;
      font-size: 0.95rem;
      font-weight: 600;
    }}

    .sections {{
      display: grid;
      gap: 18px;
      margin-top: 20px;
    }}

    .directory-section {{
      padding: 16px 0 0;
      border-top: 1px solid var(--line);
    }}

    .directory-section:first-child {{
      border-top: 0;
      padding-top: 0;
    }}

    .section-header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: end;
      margin-bottom: 8px;
    }}

    .section-header h2 {{
      margin: 0;
      font-size: 1.15rem;
      line-height: 1.15;
      font-weight: 700;
    }}

    .section-header p {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.5;
    }}

    .section-count {{
      color: var(--muted);
      font-size: 0.84rem;
      white-space: nowrap;
    }}

    .directory-list {{
      background: var(--surface);
      border: 1px solid var(--line);
    }}

    .directory-row {{
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(300px, 0.95fr);
      gap: 18px;
      padding: 12px 16px;
      border-top: 1px solid var(--line);
    }}

    .directory-row:first-child {{
      border-top: 0;
    }}

    .directory-row.is-unavailable {{
      background: rgba(0, 0, 0, 0.012);
    }}

    .row-main {{
      min-width: 0;
    }}

    .row-main h3 {{
      margin: 0;
      font-size: 1rem;
      line-height: 1.2;
      font-weight: 650;
    }}

    .row-description {{
      margin: 4px 0 0;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
      color: var(--muted);
      font-size: 0.9rem;
    }}

    .row-side {{
      display: grid;
      gap: 6px;
      align-content: start;
      justify-items: end;
      min-width: 0;
    }}

    .row-meta {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
    }}

    .meta-item {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 28px;
      padding: 4px 8px;
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.82rem;
      background: #fff;
    }}

    .meta-item strong {{
      color: var(--text);
      font-weight: 600;
    }}

    .meta-item.status-live {{
      color: var(--accent);
      border-color: rgba(22, 88, 77, 0.2);
      background: var(--accent-soft);
    }}

    .meta-item.status-unavailable {{
      color: var(--danger);
      border-color: rgba(139, 106, 52, 0.25);
      background: var(--danger-soft);
    }}

    .row-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      justify-content: flex-end;
      font-size: 0.85rem;
    }}

    .row-actions a {{
      color: var(--accent);
      text-decoration: none;
      border-bottom: 1px solid rgba(22, 88, 77, 0.28);
    }}

    .row-actions span {{
      color: var(--muted);
    }}

    .empty-row {{
      padding: 12px 16px;
      color: var(--muted);
      font-size: 0.9rem;
    }}

    footer {{
      margin-top: 18px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.5;
    }}

    @media (max-width: 960px) {{
      .page {{
        width: min(100vw - 16px, 1240px);
      }}

      .layout {{
        grid-template-columns: 1fr;
      }}

      .sidebar {{
        position: fixed;
        top: 0;
        left: 0;
        width: min(88vw, 320px);
        max-height: 100vh;
        height: 100vh;
        padding: 18px 14px;
        transform: translateX(-100%);
        z-index: 40;
      }}

      body.sidebar-open-mobile .sidebar {{
        transform: translateX(0);
      }}

      body.sidebar-collapsed .layout {{
        grid-template-columns: 1fr;
      }}

      body.sidebar-collapsed .sidebar {{
        padding: 18px 14px;
      }}

      body.sidebar-collapsed .sidebar-title,
      body.sidebar-collapsed .sidebar-body {{
        display: grid;
      }}

      .hero,
      .directory-row,
      .section-header {{
        grid-template-columns: 1fr;
      }}

      .row-side {{
        justify-items: start;
      }}

      .row-meta,
      .row-actions {{
        justify-content: flex-start;
      }}
    }}

    @media (max-width: 640px) {{
      .directory-list {{
        border-left: 0;
        border-right: 0;
      }}

      .directory-row,
      .empty-row {{
        padding-left: 0;
        padding-right: 0;
      }}
    }}
  </style>
</head>
<body class="sidebar-expanded">
  <div class="sidebar-overlay" data-sidebar-overlay hidden></div>
  <main class="page">
    <div class="layout">
      <aside class="sidebar" id="feed-sidebar" aria-label="Feed directory navigation">
        <div class="sidebar-header">
          <span class="sidebar-title">Feed directory</span>
          <button
            class="directory-toggle directory-toggle--sidebar"
            type="button"
            data-sidebar-toggle
            aria-controls="feed-sidebar"
            aria-expanded="true"
            aria-label="Hide directory"
          >
            <span class="directory-toggle__icon" aria-hidden="true"><span></span><span></span><span></span></span>
            <span class="directory-toggle__label" data-toggle-label>Hide directory</span>
          </button>
        </div>
        <nav class="sidebar-body">
          {sidebar_nav}
        </nav>
      </aside>

      <div class="main">
        <header class="hero">
          <div class="hero-main">
            <p class="hero-kicker">AI feed directory</p>
            <h1>{title}</h1>
            <p class="hero-tagline">{tagline}</p>
            <p class="hero-url">Published at <a href="{site_url}">{site_url}</a></p>
            <div class="hero-actions">
              <button
                class="directory-toggle directory-toggle--hero"
                type="button"
                data-sidebar-toggle
                aria-controls="feed-sidebar"
                aria-expanded="true"
                aria-label="Hide directory"
              >
                <span class="directory-toggle__icon" aria-hidden="true"><span></span><span></span><span></span></span>
                <span class="directory-toggle__label" data-toggle-label>Hide directory</span>
              </button>
            </div>
          </div>
          <dl class="hero-stats" aria-label="Feed directory statistics">
            <div class="stat-row">
              <dt>Live feeds</dt>
              <dd>{live_feed_count} live feeds</dd>
            </div>
            <div class="stat-row">
              <dt>Configured</dt>
              <dd>{total_feeds} configured</dd>
            </div>
            <div class="stat-row">
              <dt>Latest build</dt>
              <dd>{latest_display}</dd>
            </div>
          </dl>
        </header>

        <div class="sections">
          {sections}
        </div>

        <footer>
          Generated from <span class="meta-key">config.yaml</span> and the current XML files in <span class="meta-key">feeds/</span>.
        </footer>
      </div>
    </div>
  </main>
  <script>
    (() => {{
      const body = document.body;
      const sidebar = document.getElementById("feed-sidebar");
      const overlay = document.querySelector("[data-sidebar-overlay]");
      const toggles = Array.from(document.querySelectorAll("[data-sidebar-toggle]"));
      const navLinks = Array.from(document.querySelectorAll(".sidebar a"));
      const mobileQuery = window.matchMedia("(max-width: 960px)");
      const labels = {{
        "desktop-expanded": "Hide directory",
        "desktop-collapsed": "Show directory",
        "mobile-closed": "Open directory",
        "mobile-open": "Close directory",
      }};

      const currentState = () => {{
        if (mobileQuery.matches) {{
          return body.classList.contains("sidebar-open-mobile") ? "mobile-open" : "mobile-closed";
        }}
        return body.classList.contains("sidebar-collapsed") ? "desktop-collapsed" : "desktop-expanded";
      }};

      const syncToggleState = () => {{
        const state = currentState();
        const expanded = state === "desktop-expanded" || state === "mobile-open";
        const label = labels[state];
        body.dataset.directoryState = state;
        toggles.forEach((toggle) => {{
          toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
          toggle.setAttribute("aria-label", label);
          toggle.dataset.directoryState = state;
          const labelNode = toggle.querySelector("[data-toggle-label]");
          if (labelNode) {{
            labelNode.textContent = label;
          }}
        }});
      }};

      const closeMobileSidebar = () => {{
        body.classList.remove("sidebar-open-mobile");
        overlay.hidden = true;
        syncToggleState();
      }};

      const openMobileSidebar = () => {{
        body.classList.add("sidebar-open-mobile");
        overlay.hidden = false;
        syncToggleState();
      }};

      const toggleDesktopSidebar = () => {{
        const collapsed = body.classList.toggle("sidebar-collapsed");
        body.classList.toggle("sidebar-expanded", !collapsed);
        syncToggleState();
      }};

      toggles.forEach((toggle) => {{
        toggle.addEventListener("click", () => {{
          if (mobileQuery.matches) {{
            if (body.classList.contains("sidebar-open-mobile")) {{
              closeMobileSidebar();
            }} else {{
              openMobileSidebar();
            }}
            return;
          }}
          toggleDesktopSidebar();
        }});
      }});

      overlay.addEventListener("click", closeMobileSidebar);

      document.addEventListener("keydown", (event) => {{
        if (event.key === "Escape" && body.classList.contains("sidebar-open-mobile")) {{
          closeMobileSidebar();
        }}
      }});

      navLinks.forEach((link) => {{
        link.addEventListener("click", () => {{
          if (mobileQuery.matches) {{
            closeMobileSidebar();
          }}
        }});
      }});

      mobileQuery.addEventListener("change", (event) => {{
        if (event.matches) {{
          body.classList.remove("sidebar-expanded", "sidebar-collapsed");
          body.classList.remove("sidebar-open-mobile");
          overlay.hidden = true;
        }} else {{
          overlay.hidden = true;
          body.classList.remove("sidebar-open-mobile");
          body.classList.add("sidebar-expanded");
          body.classList.remove("sidebar-collapsed");
        }}
        syncToggleState();
      }});

      if (mobileQuery.matches) {{
        body.classList.remove("sidebar-expanded", "sidebar-collapsed", "sidebar-open-mobile");
        overlay.hidden = true;
      }} else {{
        body.classList.add("sidebar-expanded");
        body.classList.remove("sidebar-collapsed", "sidebar-open-mobile");
        overlay.hidden = true;
      }}
      syncToggleState();
    }})();
  </script>
</body>
</html>
""".format(
        title=escape(str(site.get("title") or DEFAULT_SITE["title"])),
        description=escape(str(site.get("description") or DEFAULT_SITE["description"])),
        tagline=escape(str(site.get("tagline") or DEFAULT_SITE["tagline"])),
        site_url=escape(str(site.get("url") or DEFAULT_SITE["url"])),
        sidebar_nav=_render_sidebar_nav(grouped_cards),
        live_feed_count=live_feed_count,
        total_feeds=total_feeds,
        latest_display=escape(latest_display),
        sections=_render_sections(grouped_cards),
    )


def _render_sidebar_nav(grouped_cards: dict[str, list[FeedCard]]) -> str:
    groups = []
    for section in SECTION_ORDER:
        cards = grouped_cards[section]
        meta = SECTION_META[section]
        links = [
            '<li><a href="#{anchor_id}">{title}</a></li>'.format(
                anchor_id=escape(card.anchor_id),
                title=escape(card.title),
            )
            for card in cards
        ]
        groups.append(
            """
          <section class="sidebar-group">
            <h2>{title}</h2>
            <ul>
              {links}
            </ul>
          </section>""".format(
                title=escape(meta["title"]),
                links="".join(links),
            )
        )
    return "".join(groups)


def _render_sections(grouped_cards: dict[str, list[FeedCard]]) -> str:
    return "".join(_render_section(section, grouped_cards[section]) for section in SECTION_ORDER)


def _render_section(section: str, cards: list[FeedCard]) -> str:
    meta = SECTION_META[section]
    live_count = sum(1 for card in cards if card.is_live)
    cards_html = "".join(_render_row(card) for card in cards) or (
        '<div class="empty-row">No feeds configured in this section.</div>'
    )

    return """
    <section class="directory-section" id="section-{section}">
      <div class="section-header">
        <div>
          <p class="section-kicker">{title}</p>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <div class="section-count">{live_count} live</div>
      </div>
      <div class="directory-list">
        {cards}
      </div>
    </section>""".format(
        section=escape(section),
        title=escape(meta["title"]),
        description=escape(meta["description"]),
        live_count=live_count,
        cards=cards_html,
    )


def _render_row(card: FeedCard) -> str:
    rss_action = (
        '<a href="{rss_path}">RSS</a>'.format(rss_path=escape(card.rss_path))
        if card.rss_available
        else "<span>RSS unavailable</span>"
    )
    source_action = (
        '<a href="{source_url}">Source</a>'.format(source_url=escape(card.source_url))
        if card.source_url
        else "<span>Source unavailable</span>"
    )
    status_class = "status-live" if card.is_live else "status-unavailable"

    return """
        <article class="directory-row {row_class}" id="{anchor_id}">
          <div class="row-main">
            <h3>{title}</h3>
            <p class="row-description">{description}</p>
          </div>
          <div class="row-side">
            <div class="row-meta">
              <span class="meta-item"><span class="meta-key">Updated</span><strong>{updated_display}</strong></span>
              <span class="meta-item {status_class}"><span class="meta-key">Status</span><strong>{status_label}</strong></span>
            </div>
            <div class="row-actions">
              {rss_action}
              {source_action}
            </div>
          </div>
        </article>""".format(
        row_class=escape(card.status_class),
        anchor_id=escape(card.anchor_id),
        title=escape(card.title),
        description=escape(card.description),
        updated_display=escape(card.updated_display),
        status_class=status_class,
        status_label=escape(card.status_label),
        rss_action=rss_action,
        source_action=source_action,
    )
