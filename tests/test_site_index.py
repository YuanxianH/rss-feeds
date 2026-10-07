import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

from src.site_index import SECTION_META, generate_site_index

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SITE = "https://yuanxianh.github.io/rss-feeds/"
OPML_FILENAME = "subscriptions.opml"
VISIBLE_OPML_LINK = (
    '<p class="subscribe-all">'
    f'<a href="{OPML_FILENAME}" download="{OPML_FILENAME}">'
    "Download all subscriptions (OPML)</a></p>"
)


def _write_feed(
    path: Path,
    title: str,
    description: str,
    last_build: str | None = None,
) -> None:
    last_build_xml = (
        f"    <lastBuildDate>{last_build}</lastBuildDate>\n" if last_build else ""
    )
    path.write_text(
        f"""<?xml version='1.0' encoding='UTF-8'?>
<rss version="2.0">
  <channel>
    <title>{title}</title>
    <link>https://example.com/{path.stem}</link>
    <description>{description}</description>
{last_build_xml}  </channel>
</rss>
""",
        encoding="utf-8",
    )


class SiteIndexTests(unittest.TestCase):
    def test_generates_simple_static_directory_and_stylesheet(self):
        now = datetime.now(timezone.utc)
        config = {
            "site": {
                "title": "AI RSS Network",
                "url": "https://example.com/feeds/",
                "tagline": "A small feed directory.",
                "description": "Curated AI feeds.",
            },
            "jobs": [
                {
                    "name": "Older Research",
                    "title": "Older Research",
                    "description": "Older research stream.",
                    "output": "older_research.xml",
                    "catalog": {"section": "research"},
                },
                {
                    "name": "Newest Research",
                    "title": "Newest Research",
                    "description": "Newest research stream.",
                    "output": "newest_research.xml",
                    "catalog": {"section": "research"},
                },
                {
                    "name": "Unavailable Research",
                    "title": "Unavailable Research",
                    "description": "Unavailable research stream.",
                    "output": "missing_research.xml",
                    "link": "https://example.com/missing",
                    "catalog": {"section": "research"},
                },
                {
                    "name": "DeepMind Blog",
                    "title": "DeepMind Blog",
                    "description": "Latest posts from DeepMind.",
                    "output": "deepmind_blog.xml",
                    "link": "https://deepmind.google/blog/",
                    "catalog": {"section": "blogs"},
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            feeds_dir = Path(temp_dir)
            _write_feed(
                feeds_dir / "older_research.xml",
                "Older Research",
                "Older research stream.",
                format_datetime(now - timedelta(hours=2)),
            )
            _write_feed(
                feeds_dir / "newest_research.xml",
                "Newest Research",
                "Newest research stream.",
                format_datetime(now - timedelta(hours=1)),
            )
            _write_feed(
                feeds_dir / "deepmind_blog.xml",
                "DeepMind Blog",
                "Latest posts from DeepMind.",
                format_datetime(now),
            )

            output_path = generate_site_index(config, str(feeds_dir))
            html = output_path.read_text(encoding="utf-8")
            stylesheet = feeds_dir / "assets" / "site.css"
            stylesheet_exists = stylesheet.exists()

        research = html.split('id="section-research"', 1)[1].split(
            'id="section-blogs"', 1
        )[0]
        self.assertTrue(stylesheet_exists)
        self.assertIn('href="assets/site.css"', html)
        self.assertIn('class="skip-link" href="#main-content"', html)
        self.assertIn('aria-label="Feed categories"', html)
        self.assertIn('href="#section-research">Research<span>3</span>', html)
        self.assertNotIn("<script", html)
        self.assertNotIn("sidebar", html)
        self.assertNotIn("hero", html)
        self.assertIn("Live", research)
        self.assertIn("Unavailable", research)
        self.assertIn("RSS unavailable", research)
        self.assertIn('href="newest_research.xml"', html)
        self.assertIn('rel="noopener"', html)
        self.assertIn("<time datetime=", html)
        self.assertLess(
            research.index("Newest Research"),
            research.index("Older Research"),
        )
        self.assertLess(
            research.index("Older Research"),
            research.index("Unavailable Research"),
        )

    def test_marks_old_restored_feed_as_stale(self):
        config = {
            "jobs": [
                {
                    "name": "Current Blog",
                    "output": "current.xml",
                    "catalog": {"section": "blogs"},
                },
                {
                    "name": "Restored Blog",
                    "output": "restored.xml",
                    "catalog": {"section": "blogs"},
                },
            ]
        }
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            feeds_dir = Path(temp_dir)
            _write_feed(
                feeds_dir / "current.xml",
                "Current Blog",
                "Current.",
                format_datetime(now),
            )
            _write_feed(
                feeds_dir / "restored.xml",
                "Restored Blog",
                "Old but retained.",
                format_datetime(now - timedelta(days=4)),
            )

            html = generate_site_index(config, str(feeds_dir)).read_text(
                encoding="utf-8"
            )

        restored = html.split('id="feed-blogs-restored"', 1)[1].split(
            "</article>", 1
        )[0]
        self.assertIn("is-stale", html)
        self.assertIn("Stale", restored)
        self.assertIn('href="restored.xml"', restored)
        self.assertLess(html.index("Current Blog"), html.index("Restored Blog"))

    def test_escapes_configured_content_and_keeps_missing_source_disabled(self):
        config = {
            "site": {
                "title": "Feeds <script>",
                "description": 'Quotes " and <tags>',
            },
            "jobs": [
                {
                    "name": "Unsafe <Feed>",
                    "description": "<b>not markup</b>",
                    "output": "missing.xml",
                    "catalog": {"section": "releases"},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            html = generate_site_index(config, temp_dir).read_text(encoding="utf-8")

        self.assertIn("Feeds &lt;script&gt;", html)
        self.assertIn("&lt;b&gt;not markup&lt;/b&gt;", html)
        self.assertNotIn("<b>not markup</b>", html)
        self.assertIn("Source unavailable", html)

    def test_opml_lists_every_configured_feed_and_homepage_links_it(self):
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(config["site"]["url"], PUBLIC_SITE)
        expected = _expected_subscriptions(config)
        self.assertGreaterEqual(len(expected), 1)

        with tempfile.TemporaryDirectory() as temp_dir:
            feeds_dir = Path(temp_dir)
            html = generate_site_index(config, str(feeds_dir)).read_text(encoding="utf-8")
            opml_path = feeds_dir / OPML_FILENAME
            self.assertTrue(opml_path.is_file())
            actual = _parse_subscriptions(opml_path)

        self.assertEqual(actual, expected)
        self.assertIn(VISIBLE_OPML_LINK, html)
        self.assertIn('type="text/x-opml"', html)
        self.assertIn("RSS unavailable", html)

    def test_adding_a_job_shows_up_without_a_separate_list(self):
        config = {
            "site": {"url": PUBLIC_SITE.rstrip("/"), "title": "AI RSS Network"},
            "jobs": [
                {
                    "name": "Alpha",
                    "title": "A & B Research",
                    "description": "Papers <and> notes",
                    "output": "alpha.xml",
                    "link": "https://alpha.example/research",
                    "catalog": {"section": "research"},
                },
                {
                    "name": "Disabled",
                    "title": "Disabled Feed",
                    "output": "disabled.xml",
                    "link": "https://disabled.example/",
                    "enabled": False,
                    "catalog": {"section": "blogs"},
                },
                {
                    "name": "No output",
                    "title": "Missing filename",
                    "catalog": {"section": "blogs"},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            feeds_dir = Path(temp_dir)
            _write_feed(feeds_dir / "alpha.xml", "Alpha", "Present.")
            html = generate_site_index(config, str(feeds_dir)).read_text(encoding="utf-8")
            actual = _parse_subscriptions(feeds_dir / OPML_FILENAME)
            self.assertEqual(actual, _expected_subscriptions(config))
            self.assertIn(VISIBLE_OPML_LINK, html)
            self.assertNotIn("disabled.xml", (feeds_dir / OPML_FILENAME).read_text(encoding="utf-8"))
            self.assertIn("&amp;", (feeds_dir / OPML_FILENAME).read_text(encoding="utf-8"))

            config["jobs"].append(
                {
                    "name": "Gamma",
                    "title": "Gamma Releases",
                    "description": "New models.",
                    "output": "gamma.xml",
                    "link": "https://gamma.example/releases",
                    "catalog": {"section": "releases"},
                }
            )
            generate_site_index(config, str(feeds_dir))
            actual = _parse_subscriptions(feeds_dir / OPML_FILENAME)

        expected = _expected_subscriptions(config)
        self.assertEqual(actual, expected)
        self.assertIn(PUBLIC_SITE + "gamma.xml", actual)
        self.assertIn(PUBLIC_SITE + "alpha.xml", actual)
        self.assertEqual(
            [item["section"] for item in actual.values()],
            ["Research", "Releases"],
        )

    def test_empty_and_partial_configs_keep_opml_file_and_link(self):
        configs = (
            {},
            {"jobs": []},
            {
                "jobs": [
                    {
                        "name": "Off",
                        "title": "Off",
                        "output": "off.xml",
                        "enabled": False,
                    }
                ]
            },
            {
                "jobs": [
                    {
                        "name": "Missing XML",
                        "title": "Missing XML",
                        "description": "Not built yet.",
                        "output": "missing.xml",
                        "link": "https://example.com/missing",
                        "catalog": {"section": "blogs"},
                    }
                ]
            },
        )
        for config in configs:
            with self.subTest(config=config), tempfile.TemporaryDirectory() as temp_dir:
                feeds_dir = Path(temp_dir)
                html = generate_site_index(config, str(feeds_dir)).read_text(encoding="utf-8")
                opml_path = feeds_dir / OPML_FILENAME
                self.assertTrue(opml_path.is_file())
                self.assertIn(VISIBLE_OPML_LINK, html)
                root = ET.parse(opml_path).getroot()
                self.assertEqual(root.tag, "opml")
                self.assertEqual(root.get("version"), "2.0")
                actual = _parse_subscriptions(opml_path)
                self.assertEqual(actual, _expected_subscriptions(config))


def _expected_subscriptions(config: dict) -> dict[str, dict[str, str]]:
    site_url = str((config.get("site") or {}).get("url") or PUBLIC_SITE).strip()
    if not site_url.endswith("/"):
        site_url += "/"
    expected: dict[str, dict[str, str]] = {}
    for job in config.get("jobs") or []:
        if not job.get("enabled", True):
            continue
        output = str(job.get("output") or "").strip()
        if not output:
            continue
        section = (job.get("catalog") or {}).get("section")
        if section not in SECTION_META:
            section = "blogs"
        title = " ".join(str(job.get("title") or job.get("name") or output).split())
        expected[site_url + output.lstrip("/")] = {
            "section": SECTION_META[section][0],
            "title": title,
            "text": title,
            "type": "rss",
            "htmlUrl": _job_html_url(job),
            "description": " ".join(str(job.get("description") or "").split()),
        }
    return expected


def _job_html_url(job: dict) -> str:
    for key in ("link", "url", "source_url", "base_url", "api_url"):
        if value := str(job.get(key) or "").strip():
            return value
    return ""


def _parse_subscriptions(path: Path) -> dict[str, dict[str, str]]:
    root = ET.parse(path).getroot()
    if root.tag != "opml" or root.get("version") != "2.0":
        raise AssertionError(f"unexpected OPML root: {root.tag} {root.attrib}")
    body = root.find("body")
    if body is None:
        raise AssertionError("OPML body is missing")
    found: dict[str, dict[str, str]] = {}
    for group in list(body):
        if group.get("xmlUrl"):
            raise AssertionError("feed outline is not grouped under a catalog section")
        for outline in list(group):
            xml_url = outline.get("xmlUrl") or ""
            if not xml_url or xml_url in found:
                raise AssertionError(f"invalid OPML outline: {outline.attrib}")
            found[xml_url] = {
                "section": group.get("text") or "",
                "title": outline.get("title") or "",
                "text": outline.get("text") or "",
                "type": outline.get("type") or "",
                "htmlUrl": outline.get("htmlUrl") or "",
                "description": outline.get("description") or "",
            }
    return found


if __name__ == "__main__":
    unittest.main()
