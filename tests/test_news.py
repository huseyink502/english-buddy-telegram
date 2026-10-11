import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from news import Article, CATEGORIES, clean_text, parse_date, parse_rss, load_category
from bot import BOT_COMMANDS


class NewsParserTests(unittest.TestCase):
    def test_parse_rss_and_sanitize(self):
        feed = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>Ilk haber</title>
            <description><![CDATA[<b>Ozet</b> ve detay.]]></description>
            <link>https://example.org/haber-1</link>
            <pubDate>Sun, 11 Oct 2026 09:30:00 +0300</pubDate>
          </item>
          <item>
            <title>Ikinci haber</title>
            <description>Yeni haber</description>
            <link>https://example.org/haber-2</link>
            <pubDate>Sun, 11 Oct 2026 10:30:00 +0300</pubDate>
          </item>
        </channel></rss>"""
        results = parse_rss(feed, "Test gazetesi")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "Ikinci haber")
        self.assertEqual(results[1].summary, "Ozet ve detay.")
        self.assertEqual(results[0].published_label, "11.10.2026 10:30")
        self.assertEqual(len(results[0].key), 16)

    def test_sanitize_trusted_feed_html(self):
        value = clean_text("<script>IGNORE</script><b>Merhaba</b> &amp; dunya", 200)
        self.assertEqual(value, "Merhaba & dunya")
        self.assertIsNone(parse_date("not a date"))

    def test_invalid_category_is_rejected_before_fetch(self):
        async def runner():
            with self.assertRaises(ValueError):
                await load_category("https://private.host")
        import asyncio
        asyncio.run(runner())

    def test_supported_categories(self):
        self.assertIn("son", CATEGORIES)
        self.assertIn("bbc", CATEGORIES)

    def test_command_names_for_slash_menu(self):
        names = [command.command for command in BOT_COMMANDS]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("haberler", names)
        self.assertIn("sondakika", names)
        self.assertTrue(all(name.isascii() and name.islower() for name in names))


if __name__ == "__main__":
    unittest.main()
