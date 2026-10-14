"""Privacy-aware admin data. Text is stored only after disclosure and permission."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import psycopg

from privacy_policy import NOTICE_VERSION, default_recording_ready


class AdminStore:
    def __init__(self, url: str):
        if not url:
            raise ValueError("DATABASE_URL is required")
        self.url = url
        self._last_purge = None

    def _connect(self):
        return psycopg.connect(self.url, connect_timeout=15)

    def setup(self):
        with self._connect() as con:
            # Transaction-scoped lock also works with Neon transaction pooling.
            con.execute("SELECT pg_advisory_xact_lock(724601)")
            con.execute("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    transcript_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    announcements_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    -- Existing users are "legacy"; their current transcript choice is preserved.
                    legacy_record BOOLEAN NOT NULL DEFAULT TRUE,
                    notice_shown_at TIMESTAMPTZ
                )
            """)
            # Non-destructive migration; existing rows default to legacy=true.
            con.execute("""
                ALTER TABLE admin_users
                ADD COLUMN IF NOT EXISTS legacy_record BOOLEAN NOT NULL DEFAULT TRUE
            """)
            con.execute("""
                ALTER TABLE admin_users
                ADD COLUMN IF NOT EXISTS notice_shown_at TIMESTAMPTZ
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
            con.execute(
                "CREATE TABLE IF NOT EXISTS admin_schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
            )
            for migration in sorted(
                (Path(__file__).parent / "migrations").glob("*.sql")
            ):
                if con.execute(
                    "SELECT 1 FROM admin_schema_migrations WHERE version=%s",
                    (migration.name,),
                ).fetchone():
                    continue
                con.execute(migration.read_text(encoding="utf-8"))
                # Historical users outside admin_users must not become new auto-optins.
                for table in ("users", "news_subscriptions"):
                    if con.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0]:
                        con.execute(
                            f"INSERT INTO admin_users(user_id, legacy_record) SELECT user_id, TRUE FROM {table} ON CONFLICT(user_id) DO NOTHING"
                        )
                con.execute(
                    "INSERT INTO admin_schema_migrations(version) VALUES (%s)",
                    (migration.name,),
                )

    def purge_if_due(self):
        """Sweep records past 30 days when the service receives activity."""
        now = time.monotonic()
        if self._last_purge is not None and now - self._last_purge < 3600:
            return
        with self._connect() as con:
            con.execute("""
                DELETE FROM admin_chat_messages
                WHERE created_at < NOW() - INTERVAL '30 days'
            """)
            for table in ("admin_sessions", "admin_login_challenges"):
                con.execute(f"DELETE FROM {table} WHERE expires_at < NOW()")
            con.execute(
                "DELETE FROM admin_login_attempts WHERE created_at < NOW() - INTERVAL '1 day'"
            )
            con.execute(
                "DELETE FROM admin_audit WHERE created_at < NOW() - INTERVAL '90 days'"
            )
            con.execute(
                "DELETE FROM admin_dispatches WHERE created_at < NOW() - INTERVAL '30 days' AND state IN ('draft','complete','cancelled')"
            )
            con.execute(
                "DELETE FROM admin_announcement_log WHERE created_at < NOW() - INTERVAL '30 days'"
            )
        self._last_purge = now

    def seen(self, user_id: int, username: str | None, first_name: str | None):
        """Store basic bot membership metadata; never record message text here."""
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO admin_users (user_id, username, first_name, legacy_record)
                VALUES (%s, %s, %s, FALSE)
                ON CONFLICT (user_id) DO UPDATE SET
                    username=EXCLUDED.username,
                    first_name=EXCLUDED.first_name,
                    last_seen_at=NOW()
            """,
                (user_id, (username or "")[:80], (first_name or "")[:100]),
            )
        self.purge_if_due()

    def notice_status(self, user_id: int) -> tuple[bool, bool, bool]:
        """(needs_notice, is_legacy, logging_enabled); no text is saved here."""
        with self._connect() as con:
            row = con.execute(
                """
                SELECT notice_shown_at, legacy_record, transcript_enabled
                FROM admin_users WHERE user_id=%s
            """,
                (user_id,),
            ).fetchone()
        if row is None:
            return True, True, False
        return row[0] is None, bool(row[1]), bool(row[2])

    def mark_notified(self, user_id: int) -> None:
        """Only turn on default logging for new users *after* notice was sent.

        Previously known users retain whichever privacy setting they had.
        """
        with self._connect() as con:
            con.execute(
                """
                UPDATE admin_users
                SET notice_shown_at=NOW(), notice_version=%s,
                    transcript_enabled=CASE
                        WHEN legacy_record=FALSE AND privacy_choice_at IS NULL THEN %s
                        ELSE transcript_enabled
                    END
                WHERE user_id=%s AND notice_shown_at IS NULL
            """,
                (NOTICE_VERSION, default_recording_ready(), user_id),
            )

    def set_consent(self, user_id: int, column: str, enabled: bool):
        if column not in ("transcript_enabled", "announcements_enabled"):
            raise ValueError("Invalid consent option")
        with self._connect() as con:
            if column == "transcript_enabled":
                con.execute(
                    "UPDATE admin_users SET transcript_enabled=%s, privacy_choice_at=NOW(), privacy_revision=privacy_revision+1 WHERE user_id=%s AND (NOT %s OR notice_shown_at IS NOT NULL)",
                    (enabled, user_id, enabled),
                )
            else:
                con.execute(
                    "UPDATE admin_users SET announcements_enabled=%s WHERE user_id=%s",
                    (enabled, user_id),
                )

    def consent(self, user_id: int) -> tuple[bool, bool]:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT transcript_enabled, announcements_enabled
                FROM admin_users WHERE user_id=%s
            """,
                (user_id,),
            ).fetchone()
        return (bool(row[0]), bool(row[1])) if row else (False, False)

    def store_text(
        self,
        user_id: int,
        direction: str,
        text: str,
        occurred_at: datetime | None = None,
        turn_id: str | None = None,
        revision: int | None = None,
    ):
        if direction not in ("user", "bot") or not text.strip():
            return
        with self._connect() as con:
            # Acquire row lock so opting out and logging cannot race.
            row = con.execute(
                "SELECT transcript_enabled, notice_shown_at, privacy_revision FROM admin_users WHERE user_id=%s FOR UPDATE",
                (user_id,),
            ).fetchone()
            if (
                row
                and row[0]
                and row[1] is not None
                and (occurred_at is None or occurred_at > row[1])
                and (revision is None or revision == row[2])
            ):
                con.execute(
                    """
                    INSERT INTO admin_chat_messages (user_id, direction, body, turn_id)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                """,
                    (user_id, direction, text[:12000], turn_id),
                )
            # Erase expired transcripts for this user on every write.
            con.execute(
                """
                DELETE FROM admin_chat_messages
                WHERE user_id=%s AND created_at < NOW() - INTERVAL '30 days'
            """,
                (user_id,),
            )

    def delete_transcripts(self, user_id: int):
        with self._connect() as con:
            con.execute(
                "UPDATE admin_users SET transcript_enabled=FALSE, privacy_choice_at=NOW(), privacy_revision=privacy_revision+1 WHERE user_id=%s",
                (user_id,),
            )
            con.execute("DELETE FROM admin_chat_messages WHERE user_id=%s", (user_id,))

    def stats(self) -> dict:
        self.purge_if_due()
        with self._connect() as con:
            users = con.execute("""
                SELECT COUNT(*)::int, COUNT(*) FILTER
                (WHERE last_seen_at >= NOW() - INTERVAL '7 days')::int,
                COUNT(*) FILTER (WHERE transcript_enabled)::int,
                COUNT(*) FILTER (WHERE announcements_enabled)::int,
                COUNT(*) FILTER (WHERE last_seen_at >= NOW() - INTERVAL '1 day')::int,
                COUNT(*) FILTER (WHERE NOT transcript_enabled)::int
                FROM admin_users
            """).fetchone()
            chats = con.execute("""
                SELECT COUNT(*)::int FROM admin_chat_messages
                WHERE created_at >= NOW() - INTERVAL '30 days'
            """).fetchone()[0]
        return {
            "users": users[0],
            "active_7d": users[1],
            "chat_optins": users[2],
            "announcement_optins": users[3],
            "messages_30d": chats,
            "active_1d": users[4],
            "chat_disabled": users[5],
        }

    def users(
        self, limit: int = 50, offset: int = 0, search: str = "", status: str = "all"
    ) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT user_id, username, first_name, joined_at, last_seen_at,
                       transcript_enabled, announcements_enabled
                FROM admin_users
                WHERE (%s='' OR user_id::text=%s OR username ILIKE %s OR first_name ILIKE %s)
                  AND (%s='all' OR transcript_enabled=%s)
                ORDER BY last_seen_at DESC, user_id
                LIMIT %s OFFSET %s
            """,
                (
                    search,
                    search,
                    "%" + search + "%",
                    "%" + search + "%",
                    status,
                    status == "on",
                    min(max(limit, 1), 100),
                    max(0, offset),
                ),
            ).fetchall()
        keys = (
            "user_id",
            "username",
            "first_name",
            "joined_at",
            "last_seen_at",
            "transcript_enabled",
            "announcements_enabled",
        )
        return [dict(zip(keys, r)) for r in rows]

    def user(self, user_id: int) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT user_id, username, first_name, joined_at, last_seen_at,
                       transcript_enabled, announcements_enabled
                FROM admin_users WHERE user_id=%s
            """,
                (user_id,),
            ).fetchone()
        if not row:
            return None
        keys = (
            "user_id",
            "username",
            "first_name",
            "joined_at",
            "last_seen_at",
            "transcript_enabled",
            "announcements_enabled",
        )
        return dict(zip(keys, row))

    def conversations(
        self, user_id: int, limit: int = 40, before: int = 0, after: int = 0
    ) -> list[dict]:
        self.purge_if_due()
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT direction, body, created_at, message_id, turn_id
                FROM (
                    SELECT direction, body, created_at, message_id, turn_id
                    FROM admin_chat_messages WHERE user_id=%s
                      AND (%s=0 OR message_id < %s) AND (%s=0 OR message_id > %s)
                      AND created_at >= NOW() - INTERVAL '30 days'
                    ORDER BY CASE WHEN %s > 0 THEN message_id END ASC, message_id DESC LIMIT %s
                ) recent ORDER BY message_id ASC
            """,
                (user_id, before, before, after, after, after, min(max(limit, 1), 100)),
            ).fetchall()
        return [
            dict(zip(("direction", "body", "created_at", "message_id", "turn_id"), r))
            for r in rows
        ]

    def recipients(self) -> list[int]:
        with self._connect() as con:
            return [
                int(row[0])
                for row in con.execute("""
                SELECT user_id FROM admin_users
                WHERE announcements_enabled=TRUE
                ORDER BY user_id
            """).fetchall()
            ]

    def save_announcement(self, body: str, count: int, sent: int, failed: int):
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO admin_announcement_log
                (content, recipients, successes, failures)
                VALUES (%s,%s,%s,%s)
            """,
                (body[:1500], count, sent, failed),
            )

    def recording_revision(self, user_id: int) -> int:
        with self._connect() as con:
            row = con.execute(
                "SELECT privacy_revision FROM admin_users WHERE user_id=%s", (user_id,)
            ).fetchone()
        return row[0] if row else -1

    def audit(self, actor_id: int, action: str, target_id: int | None = None):
        # No message bodies, passwords, session tokens, or API keys in the audit.
        with self._connect() as con:
            con.execute(
                "INSERT INTO admin_audit(actor_id, action, target_id) VALUES (%s,%s,%s)",
                (actor_id, action[:80], target_id),
            )

    def admit_login(self, bucket: str) -> bool:
        with self._connect() as con:
            con.execute("SELECT pg_advisory_xact_lock(724602)")
            count = con.execute(
                "SELECT COUNT(*) FROM admin_login_attempts WHERE (bucket=%s OR bucket='global') AND created_at > NOW()-INTERVAL '15 minutes'",
                (bucket,),
            ).fetchone()[0]
            if count >= 20:
                return False
            specific = con.execute(
                "SELECT COUNT(*) FROM admin_login_attempts WHERE bucket=%s AND created_at > NOW()-INTERVAL '15 minutes'",
                (bucket,),
            ).fetchone()[0]
            if specific >= 8:
                return False
            con.execute(
                "INSERT INTO admin_login_attempts(bucket) VALUES (%s),('global')",
                (bucket,),
            )
        return True

    def challenge(
        self, token_hash: str, code_hash: str, owner: int, credential_hash: str
    ):
        with self._connect() as con:
            con.execute(
                "INSERT INTO admin_login_challenges(token_hash,code_hash,owner_id,credential_hash,expires_at) VALUES (%s,%s,%s,%s,NOW()+INTERVAL '5 minutes')",
                (token_hash, code_hash, owner, credential_hash),
            )

    def verify_challenge(
        self, token_hash: str, code_hash: str, owner: int, credential_hash: str
    ) -> bool:
        import hmac

        with self._connect() as con:
            row = con.execute(
                "SELECT code_hash,attempts FROM admin_login_challenges WHERE token_hash=%s AND owner_id=%s AND credential_hash=%s AND expires_at>NOW() FOR UPDATE",
                (token_hash, owner, credential_hash),
            ).fetchone()
            if not row or row[1] >= 5:
                return False
            con.execute(
                "UPDATE admin_login_challenges SET attempts=attempts+1 WHERE token_hash=%s",
                (token_hash,),
            )
            if not hmac.compare_digest(row[0], code_hash):
                return False
            con.execute(
                "DELETE FROM admin_login_challenges WHERE token_hash=%s", (token_hash,)
            )
        return True

    def create_session(self, token_hash: str, owner: int, credential_hash: str):
        with self._connect() as con:
            con.execute(
                "INSERT INTO admin_sessions(token_hash,owner_id,credential_hash,expires_at) VALUES (%s,%s,%s,NOW()+INTERVAL '8 hours')",
                (token_hash, owner, credential_hash),
            )

    def session_valid(self, token_hash: str, owner: int, credential_hash: str) -> bool:
        with self._connect() as con:
            return bool(
                con.execute(
                    "SELECT 1 FROM admin_sessions WHERE token_hash=%s AND owner_id=%s AND credential_hash=%s AND expires_at>NOW()",
                    (token_hash, owner, credential_hash),
                ).fetchone()
            )

    def revoke_session(self, token_hash: str):
        with self._connect() as con:
            con.execute("DELETE FROM admin_sessions WHERE token_hash=%s", (token_hash,))

    def draft_dispatch(self, owner: int, body: str, target: int | None = None) -> int:
        body = body.strip()
        if not body or len(body) > 1500:
            raise ValueError("Mesaj 1-1500 karakter arasında olmalı")
        with self._connect() as con:
            if (
                target is not None
                and not con.execute(
                    "SELECT 1 FROM admin_users WHERE user_id=%s", (target,)
                ).fetchone()
            ):
                raise ValueError("Kullanıcı bulunamadı")
            dispatch_id = con.execute(
                "INSERT INTO admin_dispatches(owner_id,content,target_id) VALUES (%s,%s,%s) RETURNING id",
                (owner, body, target),
            ).fetchone()[0]
            con.execute(
                "INSERT INTO admin_audit(actor_id,action,target_id) VALUES (%s,'dispatch.preview',%s)",
                (owner, target),
            )
        return dispatch_id

    def dispatch(self, dispatch_id: int, owner: int) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT id,content,target_id,state FROM admin_dispatches WHERE id=%s AND owner_id=%s",
                (dispatch_id, owner),
            ).fetchone()
        return dict(zip(("id", "content", "target_id", "state"), row)) if row else None

    def confirm_dispatch(
        self, dispatch_id: int, owner: int, cancel: bool = False
    ) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT target_id FROM admin_dispatches WHERE id=%s AND owner_id=%s AND state='draft' AND created_at>NOW()-INTERVAL '5 minutes' FOR UPDATE",
                (dispatch_id, owner),
            ).fetchone()
            if not row:
                return False
            con.execute(
                "UPDATE admin_dispatches SET state=%s, confirmed_at=NOW() WHERE id=%s",
                ("cancelled" if cancel else "queued", dispatch_id),
            )
            if not cancel:
                if row[0] is None:
                    con.execute(
                        "INSERT INTO admin_deliveries(dispatch_id,user_id) SELECT %s,user_id FROM admin_users WHERE announcements_enabled=TRUE",
                        (dispatch_id,),
                    )
                else:
                    # Direct support message is not an announcement subscription.
                    con.execute(
                        "INSERT INTO admin_deliveries(dispatch_id,user_id) VALUES (%s,%s)",
                        (dispatch_id, row[0]),
                    )
            con.execute(
                "INSERT INTO admin_audit(actor_id,action,target_id) VALUES (%s,%s,%s)",
                (owner, "dispatch.cancel" if cancel else "dispatch.confirm", row[0]),
            )
        return True

    def claim_delivery(self) -> dict | None:
        with self._connect() as con:
            con.execute("SELECT pg_advisory_xact_lock(724603)")
            if not con.execute(
                "SELECT 1 FROM admin_dispatch_rate WHERE available_at<=NOW()"
            ).fetchone():
                return None
            # A send interrupted after contacting Telegram has unknown delivery;
            # don't resend automatically and risk duplicate announcements.
            con.execute(
                "UPDATE admin_deliveries SET state='unknown',error_code='interrupted' WHERE state='sending' AND claimed_at<NOW()-INTERVAL '2 minutes'"
            )
            con.execute(
                "UPDATE admin_dispatches d SET state='complete' WHERE state='queued' AND NOT EXISTS(SELECT 1 FROM admin_deliveries t WHERE t.dispatch_id=d.id AND t.state IN ('pending','sending'))"
            )
            row = con.execute("""
                SELECT t.dispatch_id,t.user_id,d.content,d.target_id,t.attempts
                FROM admin_deliveries t JOIN admin_dispatches d ON d.id=t.dispatch_id
                WHERE t.state='pending' AND t.available_at<=NOW() AND d.state='queued'
                ORDER BY t.available_at,t.dispatch_id,t.user_id
                LIMIT 1 FOR UPDATE OF t SKIP LOCKED
            """).fetchone()
            if not row:
                return None
            con.execute(
                "UPDATE admin_deliveries SET state='sending',claimed_at=NOW(),attempts=attempts+1 WHERE dispatch_id=%s AND user_id=%s",
                (row[0], row[1]),
            )
            con.execute(
                "UPDATE admin_dispatch_rate SET available_at=NOW()+INTERVAL '0.12 seconds'"
            )
        return dict(
            zip(("dispatch_id", "user_id", "content", "target_id", "attempts"), row)
        )

    def finish_delivery(
        self,
        dispatch_id: int,
        user_id: int,
        state: str,
        error: str | None = None,
        delay: float = 0,
    ):
        if state not in ("pending", "sent", "failed", "skipped", "unknown"):
            raise ValueError("Invalid delivery state")
        with self._connect() as con:
            if error == "rate_limit":
                con.execute(
                    "UPDATE admin_dispatch_rate SET available_at=GREATEST(available_at,NOW()+%s*INTERVAL '1 second')",
                    (max(delay, 0),),
                )
            con.execute(
                "UPDATE admin_deliveries SET state=%s,error_code=%s,available_at=NOW()+%s*INTERVAL '1 second' WHERE dispatch_id=%s AND user_id=%s",
                (state, error, delay, dispatch_id, user_id),
            )

    def dispatch_history(self, owner: int, limit: int = 25) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT d.id,d.created_at,d.content,d.target_id,d.state,
                COUNT(t.user_id)::int,
                COUNT(*) FILTER(WHERE t.state='sent')::int,
                COUNT(*) FILTER(WHERE t.state='failed')::int,
                COUNT(*) FILTER(WHERE t.state='skipped')::int,
                COUNT(*) FILTER(WHERE t.state='unknown')::int
                FROM admin_dispatches d LEFT JOIN admin_deliveries t ON t.dispatch_id=d.id
                WHERE d.owner_id=%s GROUP BY d.id ORDER BY d.id DESC LIMIT %s
            """,
                (owner, min(max(limit, 1), 100)),
            ).fetchall()
        return [
            dict(
                zip(
                    (
                        "id",
                        "created_at",
                        "content",
                        "target_id",
                        "state",
                        "recipients",
                        "sent",
                        "failed",
                        "skipped",
                        "unknown",
                    ),
                    r,
                )
            )
            for r in rows
        ]
