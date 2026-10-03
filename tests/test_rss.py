#!/usr/bin/env python3

# tests/test_rss.py: Python module.

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add workspace directory to path to allow importing utils

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))





class RssTests(unittest.TestCase):

    def setUp(self):

        self.tmpdir = tempfile.TemporaryDirectory()

        self.addCleanup(self.tmpdir.cleanup)

        self.config_path = os.path.join(self.tmpdir.name, "config.json")



        # Save original CONFIG_FILE_PATH

        self.old_config_path = os.environ.get("CONFIG_FILE_PATH")

        os.environ["CONFIG_FILE_PATH"] = self.config_path



        def restore_env():

            if self.old_config_path is None:

                os.environ.pop("CONFIG_FILE_PATH", None)

            else:

                os.environ["CONFIG_FILE_PATH"] = self.old_config_path



        self.addCleanup(restore_env)



        import utils.config as config_module
        import utils.rss as rss_module



        self.config_module = importlib.reload(config_module)

        self.rss_module = importlib.reload(rss_module)



    def test_strip_html(self):

        self.assertEqual(

            self.rss_module.strip_html("<p>Hello &amp; welcome!</p>"),

            "Hello & welcome!",

        )

        self.assertEqual(self.rss_module.strip_html(None), "")



    def test_normalize_date(self):

        self.assertEqual(

            self.rss_module.normalize_date("Sun, 24 May 2026 01:00:00 GMT"),

            "2026-05-24 01:00 UTC",

        )

        self.assertEqual(

            self.rss_module.normalize_date("invalid-date"), "invalid-date"

        )

        self.assertEqual(self.rss_module.normalize_date(None), "")



    def test_parse_feed_rss(self):

        sample_rss = """<?xml version="1.0"?>

        <rss>

            <channel>

                <item>

                    <title>Test Title</title>

                    <link>https://example.com/test</link>

                    <pubDate>Sun, 24 May 2026 01:00:00 GMT</pubDate>

                    <description>

                        &lt;p&gt;Test description&lt;/p&gt;

                    </description>

                </item>

            </channel>

        </rss>"""

        items = self.rss_module.parse_feed(sample_rss)

        self.assertEqual(len(items), 1)

        self.assertEqual(items[0].title, "Test Title")

        self.assertEqual(items[0].link, "https://example.com/test")

        self.assertEqual(items[0].summary, "Test description")



    def test_parse_feed_atom(self):

        sample_atom = """<?xml version="1.0"?>

        <feed xmlns="http://www.w3.org/2005/Atom">

            <entry>

                <title>Atom Title</title>

                <link href="https://example.com/atom"/>

                <published>2026-05-24T01:00:00Z</published>

                <summary>Atom summary</summary>

            </entry>

        </feed>"""

        items = self.rss_module.parse_feed(sample_atom)

        self.assertEqual(len(items), 1)

        self.assertEqual(items[0].title, "Atom Title")

        self.assertEqual(items[0].link, "https://example.com/atom")

        self.assertEqual(items[0].summary, "Atom summary")



    def test_seen_links_tracking(self):

        # Initial empty

        self.assertEqual(self.rss_module.load_seen_links(), set())



        # Mark seen

        self.rss_module.mark_links_seen(

            ["https://example.com/1", "https://example.com/2"]

        )

        seen = self.rss_module.load_seen_links()

        self.assertEqual(

            seen, {"https://example.com/1", "https://example.com/2"}

        )



    def test_feed_crud(self):

        # Initial feeds should include defaults

        feeds = self.rss_module.load_rss_feeds()

        self.assertIn("bbc-world", feeds)



        # Save a new custom feed

        self.rss_module.save_rss_feed(

            "my-custom-feed", "https://custom.com/rss"

        )

        feeds = self.rss_module.load_rss_feeds()

        self.assertIn("my-custom-feed", feeds)

        self.assertEqual(feeds["my-custom-feed"], "https://custom.com/rss")



        # Delete custom feed

        self.assertTrue(self.rss_module.delete_rss_feed("my-custom-feed"))

        feeds = self.rss_module.load_rss_feeds()

        self.assertNotIn("my-custom-feed", feeds)



        # Disable default feed

        self.assertTrue(self.rss_module.delete_rss_feed("bbc-world"))

        feeds = self.rss_module.load_rss_feeds()

        self.assertNotIn("bbc-world", feeds)





if __name__ == "__main__":

    unittest.main()

