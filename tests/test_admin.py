"""Admin access, CSRF, consent, and announcement safety regression tests."""
import asyncio
import os
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

import admin_web
from admin_store import AdminStore, send_announcement
from admin_telegram import is_owner
from webapp import app


class AdminAuthTests(unittest.TestCase):
    def test_admin_fails_closed_without_owner(self):
        fake = SimpleNamespace(
            effective_user=SimpleNamespace(id=42),
            effective_chat=SimpleNamespace(type="private"),
        )
        with patch.dict(os.environ, {"ADMIN_USER_ID": "0"}):
            self.assertFalse(is_owner(fake))
        with patch.dict(os.environ, {"ADMIN_USER_ID": "43"}):
            self.assertFalse(is_owner(fake))
        with patch.dict(os.environ, {"ADMIN_USER_ID": "42"}):
            self.assertTrue(is_owner(fake))
        fake.effective_chat.type = "group"
        with patch.dict(os.environ, {"ADMIN_USER_ID": "42"}):
            self.assertFalse(is_owner(fake))

    def test_session_signature_rejects_tampering(self):
        from starlette.requests import Request

        environ = {
            "DATABASE_URL": "fake", "ADMIN_USER_ID": "42",
            "ADMIN_WEB_PASSWORD": "this-is-a-strong-test-password-123456",
            "ADMIN_PANEL_ENABLED": "true",
        }
        with patch.dict(os.environ, environ):
            signed = admin_web.signed_session()
            def request(cookie):
                return Request({"type": "http", "method": "GET", "path": "/admin",
                                "headers": [(b"cookie", ("karamaz_admin=" + cookie).encode())],
                                "scheme": "https", "server": ("testserver", 443)})
            self.assertTrue(admin_web.is_admin(request(signed)))
            replacement = "0" if signed[-1] != "0" else "1"
            self.assertFalse(admin_web.is_admin(request(signed[:-1] + replacement)))


class AdminWebTests(unittest.TestCase):
    def test_admin_login_csrf_and_opted_in_broadcast(self):
        async def run():
            users = [{
                "user_id": 42, "username": "tester", "first_name": "Test",
                "joined_at": __import__("datetime").datetime.now(),
                "last_seen_at": __import__("datetime").datetime.now(),
                "transcript_enabled": False, "announcements_enabled": True,
            }]
            db = MagicMock()
            db.stats.return_value = {
                "users": 1, "active_7d": 1, "chat_optins": 0,
                "announcement_optins": 1, "messages_30d": 0,
            }
            db.users.return_value = users
            db.recipients.return_value = [42, 43]
            db.consent.side_effect = [(False, True), (False, False)]
            bot = SimpleNamespace(send_message=AsyncMock())
            app.state.telegram_application = SimpleNamespace(bot=bot)
            creds = {
                "ADMIN_USER_ID": "42", "DATABASE_URL": "fake",
                "ADMIN_WEB_PASSWORD": "not-a-real-secret-but-over-twenty-characters",
                "ADMIN_PANEL_ENABLED": "true",
            }
            with patch.dict(os.environ, creds), patch.object(admin_web, "storage", return_value=db), patch("asyncio.sleep", new_callable=AsyncMock):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="https://testserver") as client:
                    unauthorized = await client.get("/admin")
                    self.assertIn("Güvenli giriş", unauthorized.text)
                    self.assertNotIn("tester", unauthorized.text)

                    wrong = await client.post("/admin/login", data={"password": "wrong"})
                    self.assertIn("Parola geçersiz", wrong.text)

                    login = await client.post("/admin/login", data={"password": creds["ADMIN_WEB_PASSWORD"]})
                    self.assertEqual(login.status_code, 303)
                    self.assertIn("HttpOnly", login.headers.get("set-cookie", ""))
                    self.assertIn("Secure", login.headers.get("set-cookie", ""))
                    self.assertIn("SameSite=strict", login.headers.get("set-cookie", ""))

                    page = await client.get("/admin")
                    self.assertEqual(page.status_code, 200)
                    self.assertIn("tester", page.text)
                    match = re.search(r'name="csrf" value="([^"]+)"', page.text)
                    self.assertIsNotNone(match)
                    csrf = match.group(1)

                    blocked = await client.post("/admin/announcement", data={
                        "csrf": "wrong", "message": "Yeni özellik!"
                    })
                    self.assertEqual(blocked.status_code, 403)
                    bot.send_message.assert_not_awaited()

                    unconfirmed = await client.post("/admin/announcement", data={
                        "csrf": csrf, "message": "Yeni özellik!"
                    }, headers={"Origin": "https://testserver"})
                    self.assertEqual(unconfirmed.status_code, 400)
                    bot.send_message.assert_not_awaited()

                    sent = await client.post("/admin/announcement", data={
                        "csrf": csrf, "message": "Yeni özellik!", "confirm": "yes"
                    }, headers={"Origin": "https://testserver"})
                    self.assertEqual(sent.status_code, 200)
                    self.assertIn("Başarılı: 1", sent.text)
                    self.assertEqual(bot.send_message.await_count, 1)
                    self.assertEqual(bot.send_message.await_args.kwargs["chat_id"], 42)
        asyncio.run(run())

    def test_homepage_links_admin_without_exposing_private_data(self):
        async def run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="https://testserver"
            ) as client:
                response = await client.get("/")
                self.assertEqual(response.status_code, 200)
                self.assertIn("Karamaz Akademi", response.text)
                self.assertIn('href="/admin"', response.text)
                self.assertNotIn("ADMIN_WEB_PASSWORD", response.text)
                self.assertNotIn("Telegram ID", response.text)
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        asyncio.run(run())

    def test_web_is_disabled_when_not_configured(self):
        async def run():
            with patch.dict(os.environ, {"ADMIN_USER_ID": "0", "ADMIN_WEB_PASSWORD": "", "ADMIN_PANEL_ENABLED": "false"}):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as client:
                    response = await client.get("/admin")
                    self.assertIn("Panel henüz etkin değil", response.text)
                    self.assertNotIn('type="password"', response.text)
        asyncio.run(run())


class AdminStorageTests(unittest.TestCase):
    def test_chat_text_requires_explicit_consent(self):
        db = AdminStore("a-nonexistent-connection-string")
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchone.return_value = (False,)
        with patch.object(db, "_connect", return_value=connection):
            db.store_text(42, "user", "Gizli mesaj")
        sqls = [call.args[0] for call in connection.execute.call_args_list]
        self.assertFalse(any("INSERT INTO admin_chat_messages" in q for q in sqls))

    def test_chat_enabled_saves_limited_text(self):
        db = AdminStore("a-nonexistent-connection-string")
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchone.return_value = (True,)
        with patch.object(db, "_connect", return_value=connection):
            db.store_text(42, "bot", "x" * 5000)
        sqls = [call.args[0] for call in connection.execute.call_args_list]
        self.assertTrue(any("INSERT INTO admin_chat_messages" in q for q in sqls))
        insert = next(call for call in connection.execute.call_args_list
                      if "INSERT INTO admin_chat_messages" in call.args[0])
        self.assertEqual(len(insert.args[1][2]), 3000)

    def test_admin_announcement_requires_owner_confirm_and_can_cancel(self):
        from admin_telegram import owner_commands, admin_announcement_callback

        async def run():
            uid = 42
            msg = SimpleNamespace(
                text="/admin_duyuru Yeni özellik!",
                reply_text=AsyncMock(),
            )
            upd = SimpleNamespace(
                effective_user=SimpleNamespace(id=uid, username="owner", first_name="Owner"),
                effective_chat=SimpleNamespace(type="private"),
                message=msg,
            )
            db = MagicMock()
            db.recipients.return_value = [51, 52]
            ctx = SimpleNamespace(
                args=["Yeni", "özellik!"],
                user_data={},
                bot=SimpleNamespace(send_message=AsyncMock()),
            )
            with patch.dict(os.environ, {"ADMIN_USER_ID": "42"}), patch("admin_telegram.store", return_value=db):
                await owner_commands(upd, ctx)
                ctx.bot.send_message.assert_not_awaited()
                sent_keyboard = msg.reply_text.call_args.kwargs["reply_markup"]
                confirm_data = sent_keyboard.inline_keyboard[0][0].callback_data
                token = confirm_data.split(":")[-1]
                self.assertEqual(ctx.user_data["admin_draft"]["token"], token)
                query = SimpleNamespace(
                    data=f"admin:cancel:{token}",
                    answer=AsyncMock(),
                    edit_message_text=AsyncMock(),
                )
                cb_update = SimpleNamespace(
                    effective_user=upd.effective_user,
                    effective_chat=upd.effective_chat,
                    callback_query=query,
                )
                await admin_announcement_callback(cb_update, ctx)
                ctx.bot.send_message.assert_not_awaited()
                self.assertNotIn("admin_draft", ctx.user_data)
                self.assertIn("iptal", query.edit_message_text.call_args.args[0])

        asyncio.run(run())

    def test_non_owner_cannot_approve_broadcast(self):
        from admin_telegram import admin_announcement_callback

        async def run():
            query = SimpleNamespace(
                data="admin:confirm:012345abcdef",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
            )
            cb_update = SimpleNamespace(
                effective_user=SimpleNamespace(id=24),
                effective_chat=SimpleNamespace(type="private"),
                callback_query=query,
            )
            ctx = SimpleNamespace(
                user_data={"admin_draft": {
                    "token": "012345abcdef", "message": "Unauthorized",
                    "created": __import__("time").monotonic()
                }},
                bot=SimpleNamespace(send_message=AsyncMock()),
            )
            with patch.dict(os.environ, {"ADMIN_USER_ID": "42"}):
                await admin_announcement_callback(cb_update, ctx)
            query.answer.assert_awaited_once()
            query.edit_message_text.assert_not_awaited()
            ctx.bot.send_message.assert_not_awaited()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
