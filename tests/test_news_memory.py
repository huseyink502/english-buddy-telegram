import asyncio
import os
import unittest
from unittest.mock import patch

from news_memory import TOPICS, story_fingerprint, unique_stories
from news_monitor import summarize


class NewsMemoryTests(unittest.TestCase):
    def test_all_requested_categories(self):
        self.assertEqual(
            set(TOPICS),
            {"gta6", "brawlstars", "siyaset", "teknoloji", "dunya"},
        )

    def test_normalized_story_identity(self):
        self.assertEqual(
            story_fingerprint("GTA 6: Yeni Fragman!"),
            story_fingerprint("gta 6 yeni fragman"),
        )
        self.assertNotEqual(
            story_fingerprint("GTA 6 yeni fragman"),
            story_fingerprint("GTA 6 çıkış tarihi"),
        )

    def test_duplicate_headlines_are_grouped(self):
        rows = [
            {"event_key": "one", "title": "A"},
            {"event_key": "one", "title": "A"},
            {"event_key": "two", "title": "B"},
        ]
        self.assertEqual(len(unique_stories(rows)), 2)
        self.assertEqual(len(unique_stories(rows, limit=1)), 1)

    def test_digest_without_groq_is_source_backed(self):
        article = {
            "event_key": "one", "title": "Brawl Stars test haberi",
            "source": "Örnek Kaynak", "summary": "Özet",
            "url": "https://example.com/article",
        }
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            answer = asyncio.run(summarize("brawlstars", [article]))
        self.assertIn("Brawl Stars test haberi", answer)
        self.assertIn("https://example.com/article", answer)

    def test_empty_digest_uses_no_model(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "not-a-real-key"}):
            answer = asyncio.run(summarize("dunya", []))
        self.assertIn("yeni tarihli haber bulunamadı", answer)


if __name__ == "__main__":
    unittest.main()
