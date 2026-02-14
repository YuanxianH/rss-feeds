import unittest
from unittest.mock import patch

import main as app_main


class MainTests(unittest.TestCase):
    @patch("main.FeedCreator")
    def test_run_once_returns_false_when_any_feed_fails(self, creator_cls):
        creator_cls.return_value.create_all_feeds.return_value = {
            "feed_a": True,
            "feed_b": False,
        }

        ok = app_main.run_once({"feeds": [{"name": "feed_a"}, {"name": "feed_b"}]}, "feeds")
        self.assertFalse(ok)

    @patch("main.load_config", return_value={"feeds": [{"name": "feed_a", "url": "https://example.com"}]})
    @patch("main.run_once", return_value=False)
    def test_main_returns_1_when_run_once_failed(self, _, __):
        code = app_main.main(["-c", "config.yaml"])
        self.assertEqual(code, 1)

    def test_main_returns_2_when_config_not_found(self):
        code = app_main.main(["-c", "/tmp/does-not-exist-rss-creator.yaml"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
