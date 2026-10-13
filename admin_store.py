"""Privacy-aware admin data, informed chat logging and announcement audiences.

New users receive an explicit one-time disclosure before recording starts.
Legacy users retain earlier opt-in or opt-out status. Records older than
30 days are purged during active use; reads always filter old records.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time

import psycopg


class AdminStore:
    def __init__(self, url: str):
        if not url:
            raise ValueError("DATABASE_URL is required")
        self.url = url
        self._last_purge = 0.0

    def _connect(self):
        return psycopg.connect(self.url, connect_timeout=15)

    def setup(self):
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    transcript_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    announcements_enabled BOOLEAN NOT NULL DEFAULT FALSE
                )
            """)
            # -1 identifies accounts created before this policy. Their existing
            # transcript preference must never silently change on migration.
            # Newly inserted accounts start at 0 and are notified first.
            con.execute("""
                ALTER TABLE admin_users
                ADD COLUMN IF NOT EXISTS privacy_notice_version
                INTEGER NOT NULL DEFAULT -1
            """)
            con.execute("""
                ALTER TABLE admin_users ALTER COLUMN privacy_notice_version SET DEFAULT 0
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS admin_chat_messages (
                    message_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES admin_users(user_id) ON DELETE CASCADE,
                    direction TEXT NOT NULL CHECK (direction IN ('user', 'bot')),
                    body TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            con.execute("""
                CREATE INDEX IF NOT EXISTS ix_admin_chat_created_at
                ON admin_chat_messages (created_at)
            """)
            con.execute("""
                CREATE INDEX IF NOT EXISTS ix_admin_chat_recent
                ON admin_chat_messages (user_id, created_at DESC)
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS admin_announcement_log (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    content TEXT NOT NULL,
                    recipients INTEGER NOT NULL,
                    successes INTEGER NOT NULL,
                    failures INTEGER NOT NULL
                )
            """)

    def purge_if_due(self):
        """Sweep records past 30 days when the service receives activity."""
        now = time.monotonic()
        if now - self._last_purge < 3600:
            return
        with self._connect() as con:
            con.execute("""
                DELETE FROM admin_chat_messages
                WHERE created_at < NOW() - INTERVAL '30 days'
            """)
        self._last_purge = now

    def seen(self, user_id: int, username: str | None, first_name: str | None):
        """Store basic bot membership metadata; never record message text here."""
        with self._connect() as con:
            con.execute("""
                INSERT INTO admin_users (user_id, username, first_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username=EXCLUDED.username,
                    first_name=EXCLUDED.first_name,
                    last_seen_at=NOW()
            """, (user_id, (username or "")[:80], (first_name or "")[:100]))
        self.purge_if_due()

    def notice_version(self, user_id: int) -> int:
        """1: notice delivered; 0: new user; -1: pre-policy legacy user."""
        with self._connect() as con:
            row = con.execute("""
                SELECT privacy_notice_version
                FROM admin_users WHERE user_id=%s
            """, (user_id,)).fetchone()
        return int(row[0]) if row else -1

    def mark_notice(self, user_id: int):
        """Enable logging for new users only after notice was sent.

        Existing users keep their stored consent/opt-out preference.
        """
        with self._connect() as con:
            con.execute("""
                UPDATE admin_users SET
                    transcript_enabled =
                        CASE WHEN privacy_notice_version=0
                             THEN TRUE ELSE transcript_enabled END,
                    privacy_notice_version=1
                WHERE user_id=%s AND privacy_notice_version<>1
            """, (user_id,))

    def set_consent(self, user_id: int, column: str, enabled: bool):
        if column not in ("transcript_enabled", "announcements_enabled"):
            raise ValueError("Invalid consent option")
        with self._connect() as con:
            if column == "transcript_enabled":
                con.execute("""
                    UPDATE admin_users
                    SET transcript_enabled=%s, privacy_notice_version=1
                    WHERE user_id=%s
                """, (enabled, user_id))
            else:
                con.execute("""
                    UPDATE admin_users SET announcements_enabled=%s WHERE user_id=%s
                """, (enabled, user_id))

    def consent(self, user_id: int) -> tuple[bool, bool]:
        with self._connect() as con:
            row = con.execute("""
                SELECT transcript_enabled, announcements_enabled
                FROM admin_users WHERE user_id=%s
            """, (user_id,)).fetchone()
        return (bool(row[0]), bool(row[1])) if row else (False, False)

    def store_text(self, user_id: int, direction: str, text: str):
        if direction not in ("user", "bot") or not text.strip():
            return
        with self._connect() as con:
            # Acquire row lock so opting out and logging cannot race.
            row = con.execute(
                "SELECT transcript_enabled FROM admin_users WHERE user_id=%s FOR UPDATE",
                (user_id,),
            ).fetchone()
            if row and row[0]:
                con.execute("""
                    INSERT INTO admin_chat_messages (user_id, direction, body)
                    VALUES (%s,%s,%s)
                """, (user_id, direction, text[:3000]))
            # Erase expired transcripts for this user on every write.
            con.execute("""
                DELETE FROM admin_chat_messages
                WHERE user_id=%s AND created_at < NOW() - INTERVAL '30 days'
            """, (user_id,))

    def delete_transcripts(self, user_id: int):
        with self._connect() as con:
            con.execute(
                "UPDATE admin_users SET transcript_enabled=FALSE, privacy_notice_version=1 WHERE user_id=%s",
                (user_id,),
            )
            con.execute("DELETE FROM admin_chat_messages WHERE user_id=%s", (user_id,))

    def stats(self) -> dict:
        with self._connect() as con:
            users = con.execute("""
                SELECT COUNT(*)::int, COUNT(*) FILTER
                (WHERE last_seen_at >= NOW() - INTERVAL '7 days')::int,
                COUNT(*) FILTER (WHERE transcript_enabled)::int,
                COUNT(*) FILTER (WHERE announcements_enabled)::int
                FROM admin_users
            """).fetchone()
            chats = con.execute("""
                SELECT COUNT(*)::int FROM admin_chat_messages
                WHERE created_at >= NOW() - INTERVAL '30 days'
            """).fetchone()[0]
        return {
            "users": users[0], "active_7d": users[1],
            "chat_optins": users[2], "announcement_optins": users[3],
            "messages_30d": chats,
        }

    def users(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("""
                SELECT user_id, username, first_name, joined_at, last_seen_at,
                       transcript_enabled, announcements_enabled
                FROM admin_users ORDER BY last_seen_at DESC
                LIMIT %s OFFSET %s
            """, (min(max(limit, 1), 100), max(0, offset))).fetchall()
        keys = ("user_id", "username", "first_name", "joined_at", "last_seen_at",
                "transcript_enabled", "announcements_enabled")
        return [dict(zip(keys, r)) for r in rows]

    def user(self, user_id: int) -> dict | None:
        with self._connect() as con:
            row = con.execute("""
                SELECT user_id, username, first_name, joined_at, last_seen_at,
                       transcript_enabled, announcements_enabled
                FROM admin_users WHERE user_id=%s
            """, (user_id,)).fetchone()
        if not row:
            return None
        keys = ("user_id", "username", "first_name", "joined_at", "last_seen_at",
                "transcript_enabled", "announcements_enabled")
        return dict(zip(keys, row))

    def conversations(self, user_id: int, limit: int = 40) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("""
                SELECT direction, body, created_at
                FROM (
                    SELECT direction, body, created_at, message_id
                    FROM admin_chat_messages WHERE user_id=%s
                      AND created_at >= NOW() - INTERVAL '30 days'
                    ORDER BY message_id DESC LIMIT %s
                ) recent ORDER BY message_id ASC
            """, (user_id, min(max(limit, 1), 100))).fetchall()
        return [{"direction": a, "body": b, "created_at": c} for a, b, c in rows]

    def recipients(self) -> list[int]:
        with self._connect() as con:
            return [int(row[0]) for row in con.execute("""
                SELECT user_id FROM admin_users
                WHERE announcements_enabled=TRUE
                ORDER BY user_id
            """).fetchall()]

    def save_announcement(self, body: str, count: int, sent: int, failed: int):
        with self._connect() as con:
            con.execute("""
                INSERT INTO admin_announcement_log
                (content, recipients, successes, failures)
                VALUES (%s,%s,%s,%s)
            """, (body[:1500], count, sent, failed))


async def send_announcement(bot, store: AdminStore, text: str) -> dict:
    """Send only to opted-in recipients; small delay mitigates Telegram rate limits."""
    import asyncio

    body = text.strip()
    if not body or len(body) > 1500:
        raise ValueError("Duyuru 1-1500 karakter arasında olmalı")
    ids = await asyncio.to_thread(store.recipients)
    successes = 0
    failures = 0
    for uid in ids:
        # Re-check consent at delivery time to respect an opt-out during a send.
        enabled = await asyncio.to_thread(store.consent, uid)
        if not enabled[1]:
            continue
        try:
            await bot.send_message(
                chat_id=uid,
                text="📣 Karamaz Akademi duyurusu\n\n" + body
                + "\n\nDuyuruları kapatmak için /duyuru_kapat",
                disable_web_page_preview=True,
            )
            successes += 1
        except Exception:
            failures += 1
        await asyncio.sleep(0.10)
    await asyncio.to_thread(store.save_announcement, body, len(ids), successes, failures)
    return {"recipients": len(ids), "sent": successes, "failed": failures}
