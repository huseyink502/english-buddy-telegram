import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from news_memory import TOPICS, NewsMemory, story_fingerprint, unique_stories
from news_monitor import summarize


class NewsMonitorTests(unittest.TestCase):
    def test_topics(self):
        self.assertEqual(set(TOPICS), {"gta6", "brawlstars", "siyaset", "teknoloji", "dunya"})

    def test_fingerprint(self):
        self.assertEqual(story_fingerprint("GTA 6: Yeni Haber!"),
                         story_fingerprint("gta 6 yeni haber"))

    def test_duplicates(self):
        rows = [{"event_key": "a", "title": "A"},
                {"event_key": "a", "title": "A2"},
                {"event_key": "b", "title": "B"}]
        self.assertEqual([r["title"] for r in unique_stories(rows)], ["A", "B"])

    def test_no_database_url(self):
        with self.assertRaises(ValueError):
            NewsMemory("")

    def test_headline_fallback(self):
        import asyncio
        rows = [{"event_key": "a", "title": "GTA 6 test haberi",
                 "source": "Örnek", "url": "https://example.com/a",
                 "summary": "Özet", "published_at": datetime.now(timezone.utc)}]
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}):
            summary = asyncio.run(summarize("gta6", rows))
        self.assertIn("GTA 6", summary)
        self.assertIn("https://example.com/a", summary)
