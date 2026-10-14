"""Small security checks; full DB/web/privacy tests live in test_admin_integration."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

import admin_web
from admin_store import AdminStore
from admin_telegram import admin_announcement_callback, admin_menu_callback, is_owner
from webapp import app

CREDS = {
    "ADMIN_USER_ID": "42",
    "DATABASE_URL": "fake",
    "ADMIN_WEB_PASSWORD": "test-password-with-at-least-twenty-characters",
    "ADMIN_PANEL_ENABLED": "true",
}


class AdminTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_private_reads_and_writes_require_auth(self):
        db = MagicMock()
        with patch.dict(os.environ, CREDS), patch("admin_web.storage", return_value=db):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="https://testserver"
            ) as client:
                for path in (
                    "/admin",
                    "/admin/users",
                    "/admin/user/42",
                    "/admin/announcements",
                    "/admin/api/user/42/messages",
                ):
                    response = await client.get(path)
                    self.assertEqual(response.status_code, 401, path)
                    self.assertEqual(response.headers["cache-control"], "no-store")
                for path in (
                    "/admin/announcement/preview",
                    "/admin/announcement/1/confirm",
                    "/admin/user/42/privacy/erase",
                    "/admin/logout",
                ):
                    self.assertEqual(
                        (await client.post(path, data={"csrf": "wrong"})).status_code,
                        403,
                        path,
                    )
        db.user.assert_not_called()
        db.conversations.assert_not_called()
        db.draft_dispatch.assert_not_called()

    async def test_unauthorized_telegram_buttons_never_read_data(self):
        db = MagicMock()
        query = SimpleNamespace(
            data="admin:users", answer=AsyncMock(), edit_message_text=AsyncMock()
        )
        upd = SimpleNamespace(
            effective_user=SimpleNamespace(id=43),
            effective_chat=SimpleNamespace(type="private"),
            callback_query=query,
        )
        with (
            patch.dict(os.environ, CREDS),
            patch("admin_telegram.store", return_value=db),
        ):
            await admin_menu_callback(upd, SimpleNamespace(user_data={}))
            await admin_announcement_callback(upd, SimpleNamespace(user_data={}))
        db.users.assert_not_called()
        db.dispatch.assert_not_called()
        self.assertEqual(query.answer.await_count, 2)

    def test_telegram_owner_is_private_and_explicit(self):
        upd = SimpleNamespace(
            effective_user=SimpleNamespace(id=42),
            effective_chat=SimpleNamespace(type="private"),
        )
        for owner, expected in [
            ("0", False),
            ("bad", False),
            ("43", False),
            ("42", True),
        ]:
            with patch.dict(os.environ, {"ADMIN_USER_ID": owner}):
                self.assertEqual(is_owner(upd), expected)
        upd.effective_chat.type = "group"
        with patch.dict(os.environ, {"ADMIN_USER_ID": "42"}):
            self.assertFalse(is_owner(upd))

    def test_no_text_before_notice_even_when_enabled(self):
        db = AdminStore("fake")
        con = MagicMock()
        con.__enter__.return_value = con
        con.execute.return_value.fetchone.return_value = (True, None, 0)
        with patch.object(db, "_connect", return_value=con):
            db.store_text(42, "user", "Secret")
        self.assertFalse(
            any(
                "INSERT INTO admin_chat_messages" in c.args[0]
                for c in con.execute.call_args_list
            )
        )

    async def test_disabled_panel_and_public_home(self):
        with patch.dict(os.environ, {"ADMIN_PANEL_ENABLED": "false"}):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="https://testserver"
            ) as client:
                self.assertEqual((await client.get("/admin")).status_code, 503)
                home = await client.get("/")
                self.assertIn('href="/admin"', home.text)
                self.assertNotIn("ADMIN_WEB_PASSWORD", home.text)

    def test_security_headers_polling_and_escaping(self):
        response = admin_web.page("Test", "<p>Test</p>")
        self.assertNotIn('http-equiv="refresh"', response.body.decode())
        self.assertIn("nonce-", response.headers["content-security-policy"])
        self.assertEqual(admin_web.esc("<script>"), "&lt;script&gt;")
