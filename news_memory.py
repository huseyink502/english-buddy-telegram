"""Persistent, shared news archive and opt-in daily digest subscriptions.

No user conversation history is stored here. News and user subscriptions are separate.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta, timezone

import psycopg

TOPICS = {
    "gta6": "🎮 GTA 6",
    "brawlstars": "⭐ Brawl Stars",
    "siyaset": "🏛️ Türkiye siyaseti",
    "teknoloji": "💻 Teknoloji",
    "dunya": "🌍 Dünya gündemi",
}
TOPIC_IDS = tuple(TOPICS)


def story_fingerprint(title: str) -> str:
    """Conservatively group identical normalized headlines, not speculative events."""
    cleaned = re.sub(r"[^\w\s]", " ", title.casefold(), flags=re.UNICODE)
    cleaned = " ".join(cleaned.split())
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:20]


def unique_stories(rows: list[dict], limit: int = 7) -> list[dict]:
    seen = set()
    result = []
    for row in rows:
        fingerprint = row["event_key"]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(row)
        if len(result) >= limit:
            break
    return result


class NewsMemory:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required for news memory")
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, connect_timeout=15)

    def setup(self) -> None:
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS news_archive (
                    category TEXT NOT NULL,
                    article_key TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    published_at TIMESTAMPTZ,
                    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (category, article_key)
                )
            """)
            con.execute("""
                CREATE INDEX IF NOT EXISTS ix_news_archive_recent
                ON news_archive (category, published_at DESC)
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS news_subscriptions (
                    user_id BIGINT PRIMARY KEY,
                    enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    topics TEXT[] NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS news_summaries (
                    digest_day DATE NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    PRIMARY KEY (digest_day, category)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS news_deliveries (
                    user_id BIGINT NOT NULL,
                    digest_day DATE NOT NULL,
                    state TEXT NOT NULL DEFAULT 'processing',
                    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    sent_at TIMESTAMPTZ,
                    PRIMARY KEY (user_id, digest_day)
                )
            """)

    def archive(self, category: str, articles: list) -> int:
        if category not in TOPICS:
            raise ValueError("Unsupported topic")
        records = [
            (category, a.key, story_fingerprint(a.title), a.title,
             a.summary, a.url, a.source, a.published)
            for a in articles
        ]
        if not records:
            return 0
        with self._connect() as con:
            with con.cursor() as cur:
                cur.executemany("""
                    INSERT INTO news_archive
                    (category, article_key, event_key, title, summary, url, source, published_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (category, article_key) DO UPDATE SET
                        title=EXCLUDED.title, summary=EXCLUDED.summary,
                        published_at=COALESCE(EXCLUDED.published_at, news_archive.published_at)
                """, records)
        return len(records)

    def recent(self, category: str, since: datetime, limit: int = 30) -> list[dict]:
        if category not in TOPICS:
            raise ValueError("Unsupported topic")
        with self._connect() as con:
            rows = con.execute("""
                SELECT article_key, event_key, title, summary, url, source, published_at
                FROM news_archive
                WHERE category=%s AND published_at >= %s
                ORDER BY published_at DESC NULLS LAST LIMIT %s
            """, (category, since, limit)).fetchall()
        names = ("article_key", "event_key", "title", "summary", "url", "source", "published_at")
        return [dict(zip(names, row)) for row in rows]

    def get_article(self, key: str):
        from news import Article
        with self._connect() as con:
            row = con.execute("""
                SELECT article_key, title, summary, url, source, published_at
                FROM news_archive WHERE article_key=%s
                ORDER BY published_at DESC NULLS LAST LIMIT 1
            """, (key,)).fetchone()
        return Article(*row) if row else None

    def subscribe(self, user_id: int) -> None:
        with self._connect() as con:
            con.execute("""
                INSERT INTO news_subscriptions (user_id, enabled, topics)
                VALUES (%s, TRUE, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET enabled=TRUE, updated_at=NOW()
            """, (user_id, list(TOPIC_IDS)))

    def unsubscribe(self, user_id: int) -> None:
        with self._connect() as con:
            con.execute("""
                UPDATE news_subscriptions SET enabled=FALSE, updated_at=NOW()
                WHERE user_id=%s
            """, (user_id,))

    def preferences(self, user_id: int) -> tuple[bool, list[str]]:
        with self._connect() as con:
            row = con.execute("""
                SELECT enabled, topics FROM news_subscriptions WHERE user_id=%s
            """, (user_id,)).fetchone()
        return (bool(row[0]), list(row[1])) if row else (False, list(TOPIC_IDS))

    def toggle_topic(self, user_id: int, category: str) -> list[str]:
        if category not in TOPICS:
            raise ValueError("Unsupported topic")
        with self._connect() as con:
            row = con.execute("""
                SELECT topics FROM news_subscriptions
                WHERE user_id=%s FOR UPDATE
            """, (user_id,)).fetchone()
            if row is None:
                con.execute("""
                    INSERT INTO news_subscriptions (user_id, enabled, topics)
                    VALUES (%s, FALSE, %s)
                """, (user_id, list(TOPIC_IDS)))
                current = list(TOPIC_IDS)
            else:
                current = list(row[0])
            selected = [t for t in current if t != category] if category in current else current + [category]
            if not selected:
                raise ValueError("En az bir kategori seçilmeli")
            con.execute("""
                UPDATE news_subscriptions SET topics=%s, updated_at=NOW()
                WHERE user_id=%s
            """, (selected, user_id))
            return selected

    def subscribers(self) -> list[tuple[int, list[str]]]:
        with self._connect() as con:
            return [(int(uid), list(topics)) for uid, topics in con.execute(
                "SELECT user_id, topics FROM news_subscriptions WHERE enabled=TRUE"
            ).fetchall()]

    def summary(self, digest_day: date, category: str) -> str | None:
        with self._connect() as con:
            row = con.execute("""
                SELECT content FROM news_summaries
                WHERE digest_day=%s AND category=%s
            """, (digest_day, category)).fetchone()
            return row[0] if row else None

    def store_summary(self, digest_day: date, category: str, content: str) -> None:
        with self._connect() as con:
            con.execute("""
                INSERT INTO news_summaries (digest_day, category, content)
                VALUES (%s,%s,%s)
                ON CONFLICT (digest_day, category) DO NOTHING
            """, (digest_day, category, content))

    def latest_summary_day(self) -> date | None:
        with self._connect() as con:
            row = con.execute("SELECT MAX(digest_day) FROM news_summaries").fetchone()
            return row[0]

    def formatted_digest(self, digest_day: date, topics: list[str]) -> str:
        sections = [f"📰 Karamaz Akademi | {digest_day.strftime('%d.%m.%Y')} günlük gündem"]
        for category in topics:
            if category not in TOPICS:
                continue
            content = self.summary(digest_day, category)
            if content:
                sections.append(f"{TOPICS[category]}\n{content[:640]}")
        if len(sections) == 1:
            return "Henüz kayıtlı haber özeti bulunmuyor. /ozet komutunu daha sonra dene."
        return "\n\n".join(sections)[:3900]

    def claim_delivery(self, user_id: int, day: date) -> bool:
        """Lease a delivery; do not re-send a successfully delivered digest."""
        with self._connect() as con:
            row = con.execute("""
                INSERT INTO news_deliveries (user_id, digest_day, state, claimed_at)
                VALUES (%s,%s,'processing',NOW())
                ON CONFLICT (user_id, digest_day) DO UPDATE
                SET state='processing', claimed_at=NOW()
                WHERE news_deliveries.state<>'sent'
                  AND news_deliveries.claimed_at < NOW() - INTERVAL '45 minutes'
                RETURNING user_id
            """, (user_id, day)).fetchone()
            return row is not None

    def delivered(self, user_id: int, day: date) -> None:
        with self._connect() as con:
            con.execute("""
                UPDATE news_deliveries SET state='sent', sent_at=NOW()
                WHERE user_id=%s AND digest_day=%s
            """, (user_id, day))
