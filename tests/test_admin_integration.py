"""Real Postgres integration in an isolated, disposable schema; no live APIs."""

import asyncio
import os
import re
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import psycopg
from httpx import ASGITransport, AsyncClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from telegram.error import Forbidden, RetryAfter, TimedOut
from telegram.ext import ApplicationHandlerStop

import admin_web
from admin_delivery import deliver_one
from admin_store import AdminStore
from admin_telegram import (
    admin_announcement_callback,
    note_reply,
    observe,
    owner_commands,
    privacy_callback,
)
from webapp import app

TEST_URL = os.getenv("TEST_DATABASE_URL", "")
ENV = {
    "ADMIN_USER_ID": "42",
    "ADMIN_PANEL_ENABLED": "true",
    "ADMIN_WEB_PASSWORD": "test-admin-password-long-enough-12345",
    "TRANSCRIPT_DEFAULT_ENABLED": "true",
    "PRIVACY_CONTROLLER": "Test controller",
    "PRIVACY_CONTACT": "test@example.invalid",
    "PRIVACY_LEGAL_BASIS": "Test legitimate interest assessment",
    "ALLOWED_USER_ID": "0",
}


def update(text="Hello", uid=51):
    message = SimpleNamespace(
        text=text,
        reply_text=AsyncMock(),
        message_id=123,
        date=datetime.now(timezone.utc),
    )
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=uid, username="tester", first_name="Test", is_bot=False
        ),
        effective_chat=SimpleNamespace(type="private"),
        effective_message=message,
        message=message,
    )


@unittest.skipUnless(TEST_URL, "Set TEST_DATABASE_URL to an isolated test database")
class PostgresAdminTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.schema = "karamaz_test_" + uuid.uuid4().hex
        with psycopg.connect(TEST_URL, autocommit=True) as con:
            con.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.url = make_conninfo(TEST_URL, options="-csearch_path=" + self.schema)
        self.db = AdminStore(self.url)
        self.env = patch.dict(os.environ, {**ENV, "DATABASE_URL": self.url})
        self.env.start()
        self.db.setup()
        self.bot = SimpleNamespace(send_message=AsyncMock())
        app.state.telegram_application = SimpleNamespace(bot=self.bot)
        self.patches = [
            patch("admin_web.storage", return_value=self.db),
            patch("admin_telegram.store", return_value=self.db),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()
        with psycopg.connect(TEST_URL, autocommit=True) as con:
            con.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

    def person(self, uid=51, enabled=True):
        self.db.seen(uid, "tester", "Tester")
        self.db.mark_notified(uid)
        self.db.set_consent(uid, "transcript_enabled", enabled)

    def records(self, uid=51):
        return self.db.conversations(uid, 100)

    async def login(self, client):
        first = await client.get("/admin")
        token = re.search('name="csrf" value="([^"]+)"', first.text)[1]
        response = await client.post(
            "/admin/login", data={"csrf": token, "password": ENV["ADMIN_WEB_PASSWORD"]}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.bot.send_message.await_args.kwargs["chat_id"], 42)
        code = re.search(
            r"\b(\d{6})\b", self.bot.send_message.await_args.kwargs["text"]
        )[1]
        verify_csrf = re.search('name="csrf" value="([^"]+)"', response.text)[1]
        self.assertNotIn(admin_web.COOKIE, client.cookies)
        response = await client.post(
            "/admin/verify", data={"csrf": verify_csrf, "code": code}
        )
        self.assertEqual(response.status_code, 303, response.text)
        self.assertIn("Secure", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])
        page = await client.get("/admin")
        return re.search('name="csrf" value="([^"]+)"', page.text)[1]

    async def test_notice_first_message_then_pair_and_delayed_pre_notice(self):
        ctx = SimpleNamespace(user_data={})
        first = update("Do not save this")
        with self.assertRaises(ApplicationHandlerStop):
            await observe(first, ctx)
        self.assertEqual(self.records(), [])
        self.assertTrue(self.db.consent(51)[0])
        second = update("Hello again")
        second.message.message_id = 124
        await observe(second, ctx)
        await note_reply(second, "Hello!", ctx)
        self.assertEqual([m["direction"] for m in self.records()], ["user", "bot"])
        self.assertEqual(self.records()[0]["turn_id"], self.records()[1]["turn_id"])
        old = update("Queued before disclosure")
        old.message.date = first.message.date - timedelta(seconds=10)
        await observe(old, ctx)
        await note_reply(old, "Old reply", ctx)
        self.assertEqual(len(self.records()), 2)

    async def test_stop_delete_resume_does_not_restore_inflight_response(self):
        self.person()
        ctx = SimpleNamespace(user_data={})
        upd = update()
        await observe(upd, ctx)
        self.db.delete_transcripts(51)
        self.db.set_consent(51, "transcript_enabled", True)
        await note_reply(upd, "Delayed response", ctx)
        self.assertEqual(self.records(), [])
        self.db.mark_notified(51)
        self.db.set_consent(51, "transcript_enabled", False)
        self.db.mark_notified(51)
        self.assertFalse(self.db.consent(51)[0])

    def test_default_recording_can_be_disabled_by_owner(self):
        with patch.dict(os.environ, {"TRANSCRIPT_DEFAULT_ENABLED": "false"}):
            self.db.seen(51, None, None)
            self.db.mark_notified(51)
        self.assertFalse(self.db.consent(51)[0])

    def test_classroom_default_still_requires_disclosure(self):
        with patch.dict(os.environ, {"PRIVACY_LEGAL_BASIS": ""}):
            self.db.seen(51, None, None)
            self.assertFalse(self.db.consent(51)[0])
            self.db.store_text(51, "user", "Before disclosure")
            self.assertEqual(self.records(), [])
            self.db.mark_notified(51)
            self.assertTrue(self.db.consent(51)[0])

    def test_legacy_migration_and_explicit_choice_preserve_data(self):
        with self.db._connect() as con:
            con.execute("CREATE TABLE users(user_id BIGINT PRIMARY KEY, day INT)")
            con.execute("INSERT INTO users VALUES (61,4)")
            con.execute(
                "CREATE TABLE news_subscriptions(user_id BIGINT PRIMARY KEY,enabled BOOL)"
            )
            con.execute("INSERT INTO news_subscriptions VALUES (62,TRUE)")
            con.execute("DELETE FROM admin_schema_migrations")
            con.execute(
                "INSERT INTO admin_users(user_id,legacy_record,transcript_enabled) VALUES (63,TRUE,FALSE),(64,TRUE,TRUE)"
            )
        self.db.setup()
        self.db.setup()
        for uid in (61, 62, 63, 64):
            self.db.mark_notified(uid)
        self.assertFalse(self.db.consent(61)[0])
        self.assertFalse(self.db.consent(62)[0])
        self.assertFalse(self.db.consent(63)[0])
        self.assertTrue(self.db.consent(64)[0])
        self.db.seen(65, None, None)
        self.db.set_consent(65, "transcript_enabled", False)
        self.db.mark_notified(65)
        self.assertFalse(self.db.consent(65)[0])
        with self.db._connect() as con:
            self.assertEqual(
                con.execute("SELECT day FROM users WHERE user_id=61").fetchone()[0], 4
            )
            self.assertTrue(
                con.execute(
                    "SELECT enabled FROM news_subscriptions WHERE user_id=62"
                ).fetchone()[0]
            )

    def test_retention_order_and_cursor_pagination(self):
        self.person()
        for n in range(45):
            self.db.store_text(51, "user", str(n))
        newest = self.db.conversations(51, 40)
        previous = self.db.conversations(51, 40, before=newest[0]["message_id"])
        self.assertEqual(len(previous), 5)
        self.assertEqual([int(m["body"]) for m in previous + newest], list(range(45)))
        with self.db._connect() as con:
            con.execute(
                "UPDATE admin_chat_messages SET created_at=NOW()-INTERVAL '31 days' WHERE body='0'"
            )
        self.db._last_purge = None
        self.db.purge_if_due()
        self.assertEqual(len(self.records()), 44)
        with self.db._connect() as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM admin_chat_messages").fetchone()[0],
                44,
            )
        self.assertEqual(self.db.users(search="'; DROP TABLE admin_users; --"), [])
        self.assertEqual(len(self.db.users(status="on")), 1)

    async def test_web_2fa_csrf_logout_rotation_and_xss(self):
        self.person()
        self.db.seen(51, "<script>alert(1)</script>", "Tester")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://testserver"
        ) as client:
            csrf = await self.login(client)
            users = await client.get("/admin/users")
            self.assertIn("&lt;script&gt;", users.text)
            self.assertNotIn("<script>alert(1)</script>", users.text)
            self.assertEqual(
                (
                    await client.post(
                        "/admin/user/51/privacy/erase", data={"csrf": "wrong"}
                    )
                ).status_code,
                403,
            )
            self.assertEqual(
                (
                    await client.post(
                        "/admin/user/51/privacy/erase",
                        data={"csrf": csrf},
                        headers={"Origin": "https://evil.invalid"},
                    )
                ).status_code,
                403,
            )
            saved = client.cookies.get(admin_web.COOKIE)
            self.assertEqual(
                (await client.post("/admin/logout", data={"csrf": csrf})).status_code,
                303,
            )
            client.cookies.set(
                admin_web.COOKIE, saved, domain="testserver.local", path="/admin"
            )
            self.assertEqual(
                (await client.get("/admin/api/user/51/messages")).status_code, 401
            )
            client.cookies.clear()
            await self.login(client)
            with patch.dict(
                os.environ,
                {"ADMIN_WEB_PASSWORD": "another-long-password-with-twenty-characters"},
            ):
                self.assertEqual(
                    (await client.get("/admin/api/user/51/messages")).status_code, 401
                )

    async def test_web_chat_live_status_and_user_controls(self):
        self.person()
        self.db.store_text(51, "user", "<img src=x onerror=alert(1)>")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://testserver"
        ) as client:
            csrf = await self.login(client)
            result = await client.get("/admin/api/user/51/messages")
            self.assertTrue(result.json()["enabled"])
            self.assertEqual(len(result.json()["messages"]), 1)
            self.db.store_text(51, "bot", "New answer")
            self.assertEqual(
                len(
                    (await client.get("/admin/api/user/51/messages")).json()["messages"]
                ),
                2,
            )
            await client.post("/admin/user/51/privacy/stop", data={"csrf": csrf})
            data = (await client.get("/admin/api/user/51/messages")).json()
            self.assertFalse(data["enabled"])
            self.assertEqual(data["messages"], [])
            await client.post("/admin/user/51/privacy/erase", data={"csrf": csrf})
            self.assertEqual(self.records(), [])

    async def test_web_preview_confirmation_idempotency_and_permission_recheck(self):
        self.person()
        self.person(52)
        self.person(53)
        for uid in (51, 52):
            self.db.set_consent(uid, "announcements_enabled", True)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://testserver"
        ) as client:
            csrf = await self.login(client)
            self.bot.send_message.reset_mock()
            preview = await client.post(
                "/admin/announcement/preview",
                data={"csrf": csrf, "message": "New feature"},
            )
            self.assertEqual(preview.status_code, 200)
            self.bot.send_message.assert_not_awaited()
            did = int(re.search(r"/announcement/(\d+)/confirm", preview.text)[1])
            response = await client.post(
                f"/admin/announcement/{did}/confirm", data={"csrf": csrf}
            )
            self.assertEqual(response.status_code, 303)
            self.assertEqual(
                (
                    await client.post(
                        f"/admin/announcement/{did}/confirm", data={"csrf": csrf}
                    )
                ).status_code,
                409,
            )
            self.db.set_consent(52, "announcements_enabled", False)
            await deliver_one(self.bot, self.db)
            await asyncio.sleep(0.14)
            await deliver_one(self.bot, self.db)
            self.assertEqual(self.bot.send_message.await_count, 1)
            self.assertEqual(self.bot.send_message.await_args.kwargs["chat_id"], 51)
            hist = self.db.dispatch_history(42)[0]
            self.assertEqual((hist["sent"], hist["skipped"]), (1, 1))

    async def test_telegram_privacy_and_owner_confirmation(self):
        self.person()
        query = SimpleNamespace(
            data="privacy:stop", answer=AsyncMock(), edit_message_text=AsyncMock()
        )
        upd = update()
        upd.callback_query = query
        await privacy_callback(upd, SimpleNamespace(user_data={}))
        self.assertFalse(self.db.consent(51)[0])
        query.data = "privacy:announcements_on"
        await privacy_callback(upd, SimpleNamespace(user_data={}))
        self.assertTrue(self.db.consent(51)[1])
        owner = update("/admin_duyuru Notice", uid=42)
        ctx = SimpleNamespace(args=["Notice"], user_data={}, bot=self.bot)
        await owner_commands(owner, ctx)
        did = ctx.user_data["admin_draft"]["token"]
        # Persisted draft survives a bot restart (no context user_data needed).
        owner.callback_query = SimpleNamespace(
            data="admin:confirm:" + did,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        await admin_announcement_callback(
            owner, SimpleNamespace(user_data={}, bot=self.bot)
        )
        self.assertEqual(self.db.dispatch(int(did), 42)["state"], "queued")

    async def test_delivery_rate_limit_blocked_and_uncertain_handling(self):
        self.person()
        self.db.set_consent(51, "announcements_enabled", True)
        for exc, expected in (
            (RetryAfter(1), "pending"),
            (Forbidden("blocked"), "failed"),
            (TimedOut(), "unknown"),
        ):
            did = self.db.draft_dispatch(42, "Message")
            self.db.confirm_dispatch(did, 42)
            self.bot.send_message.side_effect = exc
            with patch("admin_delivery.asyncio.sleep", new_callable=AsyncMock):
                await deliver_one(self.bot, self.db)
            with self.db._connect() as con:
                self.assertEqual(
                    con.execute(
                        "SELECT state FROM admin_deliveries WHERE dispatch_id=%s",
                        (did,),
                    ).fetchone()[0],
                    expected,
                )
                if expected == "pending":
                    con.execute(
                        "UPDATE admin_deliveries SET state='failed' WHERE dispatch_id=%s",
                        (did,),
                    )
                con.execute("UPDATE admin_dispatch_rate SET available_at=NOW()")

    async def test_direct_support_message_does_not_require_broadcast_optin(self):
        self.person()
        did = self.db.draft_dispatch(42, "Requested support", 51)
        self.assertTrue(self.db.confirm_dispatch(did, 42))
        await deliver_one(self.bot, self.db)
        self.assertEqual(self.bot.send_message.await_args.kwargs["chat_id"], 51)

    def test_persistent_rate_limits_otp_attempts_and_expiry(self):
        for _ in range(8):
            self.assertTrue(self.db.admit_login("ip"))
        self.assertFalse(AdminStore(self.url).admit_login("ip"))
        self.db.challenge("token", "hash", 42, "credential")
        for _ in range(5):
            self.assertFalse(
                self.db.verify_challenge("token", "wrong", 42, "credential")
            )
        self.assertFalse(self.db.verify_challenge("token", "hash", 42, "credential"))
        self.db.challenge("other", "hash", 42, "credential")
        self.assertTrue(self.db.verify_challenge("other", "hash", 42, "credential"))
        self.assertFalse(self.db.verify_challenge("other", "hash", 42, "credential"))
