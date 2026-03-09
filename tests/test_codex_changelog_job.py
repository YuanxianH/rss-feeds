import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.jobs.base import JobContext
from src.jobs.codex_changelog import (
    CodexChangelogJob,
    extract_codex_changelog_items,
    extract_github_release_atom_items,
)


SAMPLE_CHANGELOG_HTML = """
<main>
  <section>
    <ul>
      <li class="scroll-mt-28">
        <div>
          <time datetime="2026-03-08">2026-03-08</time>
          <h3>
            Codex CLI 0.112.0
            <button data-anchor-id="github-release-294459110" aria-label="Copy link to Codex CLI Release: 0.112.0"></button>
          </h3>
        </div>
        <article>
          <pre><code>$ npm install -g @openai/codex@0.112.0</code></pre>
          <details>
            <summary>View details</summary>
            <h4>New Features</h4>
            <ul>
              <li>
                Added @plugin mentions so users can reference plugins directly in chat.
                <a href="https://github.com/openai/codex/pull/13510">#13510</a>
              </li>
            </ul>
            <p>
              <a href="https://github.com/openai/codex/releases/tag/rust-v0.112.0">Full release on Github</a>
            </p>
          </details>
        </article>
      </li>
      <li class="scroll-mt-28">
        <div>
          <time datetime="2026-03-05">2026-03-05</time>
          <h3>
            Introducing GPT-5.4 in Codex
            <button data-anchor-id="codex-2026-03-05-mdx" aria-label="Copy link to Introducing GPT-5.4 in Codex"></button>
          </h3>
        </div>
        <article>
          <p>General product update.</p>
        </article>
      </li>
    </ul>
  </section>
</main>
"""

SAMPLE_GITHUB_RELEASES_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:github.com,2008:Repository/123456789/rust-v0.112.0</id>
    <title>Codex CLI 0.112.0</title>
    <updated>2026-03-08T12:00:00Z</updated>
    <link rel="alternate" type="text/html" href="https://github.com/openai/codex/releases/tag/rust-v0.112.0" />
    <content type="html">&lt;h1&gt;New Features&lt;/h1&gt;&lt;ul&gt;&lt;li&gt;Added @plugin mentions&lt;/li&gt;&lt;/ul&gt;</content>
  </entry>
</feed>
"""


class CodexChangelogJobTests(unittest.TestCase):
    def test_extract_codex_changelog_items_filters_to_github_release_entries(self):
        items = extract_codex_changelog_items(
            SAMPLE_CHANGELOG_HTML,
            "https://developers.openai.com/codex/changelog",
            anchor_prefixes=["github-release-"],
            max_items=10,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Codex CLI 0.112.0")
        self.assertEqual(
            items[0]["link"],
            "https://github.com/openai/codex/releases/tag/rust-v0.112.0",
        )
        self.assertEqual(
            items[0]["guid"],
            "https://developers.openai.com/codex/changelog#github-release-294459110",
        )
        self.assertEqual(items[0]["pubDate"], "2026-03-08")
        self.assertIn("New Features", items[0]["description"])
        self.assertIn("Added @plugin mentions", items[0]["description"])
        self.assertIn("#13510", items[0]["description"])
        self.assertNotIn("View details", items[0]["description"])
        self.assertNotIn("Full release on Github", items[0]["description"])

    def test_extract_github_release_atom_items(self):
        items = extract_github_release_atom_items(SAMPLE_GITHUB_RELEASES_ATOM, max_items=10)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Codex CLI 0.112.0")
        self.assertEqual(
            items[0]["link"],
            "https://github.com/openai/codex/releases/tag/rust-v0.112.0",
        )
        self.assertEqual(
            items[0]["guid"],
            "tag:github.com,2008:Repository/123456789/rust-v0.112.0",
        )
        self.assertEqual(items[0]["pubDate"], "2026-03-08T12:00:00Z")
        self.assertIn("New Features", items[0]["description"])
        self.assertIn("Added @plugin mentions", items[0]["description"])

    @patch("src.jobs.codex_changelog.WebScraper.fetch", return_value=SAMPLE_CHANGELOG_HTML)
    def test_codex_changelog_job_generates_rss(self, _fetch):
        config = {
            "type": "codex_changelog",
            "name": "Codex GitHub Releases",
            "url": "https://developers.openai.com/codex/changelog",
            "link": "https://developers.openai.com/codex/changelog#github-release",
            "output": "codex_github_releases.xml",
            "anchor_prefixes": ["github-release-"],
            "options": {"max_items": 10},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CodexChangelogJob(config).run(JobContext(feeds_dir=Path(temp_dir)))
            output_path = Path(temp_dir) / "codex_github_releases.xml"

            self.assertTrue(result.success)
            self.assertTrue(output_path.exists())
            xml = output_path.read_text(encoding="utf-8")

        self.assertIn("Codex CLI 0.112.0", xml)
        self.assertIn("rust-v0.112.0", xml)
        self.assertIn("github-release-294459110", xml)

    @patch(
        "src.jobs.codex_changelog.WebScraper.fetch",
        side_effect=[None, SAMPLE_GITHUB_RELEASES_ATOM],
    )
    def test_codex_changelog_job_falls_back_to_github_atom_when_changelog_unavailable(self, _fetch):
        config = {
            "type": "codex_changelog",
            "name": "Codex GitHub Releases",
            "url": "https://developers.openai.com/codex/changelog",
            "fallback_atom_url": "https://github.com/openai/codex/releases.atom",
            "link": "https://developers.openai.com/codex/changelog#github-release",
            "output": "codex_github_releases.xml",
            "anchor_prefixes": ["github-release-"],
            "options": {"max_items": 10},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CodexChangelogJob(config).run(JobContext(feeds_dir=Path(temp_dir)))
            output_path = Path(temp_dir) / "codex_github_releases.xml"

            self.assertTrue(result.success)
            self.assertTrue(output_path.exists())
            xml = output_path.read_text(encoding="utf-8")

        self.assertIn("Codex CLI 0.112.0", xml)
        self.assertIn("rust-v0.112.0", xml)

    @patch("src.jobs.codex_changelog.WebScraper.fetch", side_effect=[None, "<feed></feed>"])
    def test_codex_changelog_job_fails_when_both_sources_have_no_entries(self, _fetch):
        config = {
            "type": "codex_changelog",
            "name": "Codex GitHub Releases",
            "url": "https://developers.openai.com/codex/changelog",
            "fallback_atom_url": "https://github.com/openai/codex/releases.atom",
            "output": "codex_github_releases.xml",
            "anchor_prefixes": ["github-release-"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            result = CodexChangelogJob(config).run(JobContext(feeds_dir=Path(temp_dir)))

        self.assertFalse(result.success)
        self.assertIn("抓取 changelog 页面和 GitHub Releases Atom feed 均失败", result.details)


if __name__ == "__main__":
    unittest.main()
