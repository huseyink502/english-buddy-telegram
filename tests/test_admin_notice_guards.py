"""Safety regressions for automatic logging after a privacy notice."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.ext import ApplicationHandlerStop

from admin_telegram import observe, privacy_commands, privacy_callback


def update_for(text="/start", uid=42):
    msg = SimpleNamespace(text=text, reply_text=AsyncMock())
    user = SimpleNamespace(id=uid, username="tester", first_name="Tester", is_bot=False)
    chat = SimpleNamespace(type="private")
    return SimpleNamespace(
        effective_user=user, effective_chat=chat, effective_message=msg,
        message=msg, callback_query=None,
    )


class NoticeSafetyTests(unittest.TestCase):
    def test_new_user_gets_notice_and_first_message_stops(self):
        async def run():
            db = MagicMock()
            db.notice_status.return_value = (True, False, False)
            update = update_for("Bu özel bir mesaj")
            with patch.dict(__import__("os").environ, {"ALLOWED_USER_ID": "0"}), patch(
                "admin_telegram.store", return_value=db
            ):
                with self.assertRaises(ApplicationHandlerStop):
                    await observe(update, SimpleNamespace())
            update.message.reply_text.assert_awaited_once()
            db.mark_notified.assert_called_once_with(42)
            db.store_text.assert_not_called()
        asyncio.run(run())

    def test_after_notice_logged_only_when_store_allows(self):
        async def run():
            db = MagicMock()
            db.notice_status.return_value = (False, False, True)
            update = update_for("Merhaba")
            with patch.dict(__import__("os").environ, {"ALLOWED_USER_ID": "0"}), patch(
                "admin_telegram.store", return_value=db
            ):
                await observe(update, SimpleNamespace())
            db.store_text.assert_called_once_with(42, "user", "Merhaba")
        asyncio.run(run())

    def test_restricted_users_cannot_be_tracked(self):
        async def run():
            update = update_for("Başka kullanıcı", uid=42)
            db = MagicMock()
            with patch.dict(__import__("os").environ, {"ALLOWED_USER_ID": "41"}), patch(
                "admin_telegram.store", return_value=db
            ):
                await observe(update, SimpleNamespace())
                await privacy_commands(update_for("/gizlilik"), SimpleNamespace())
            db.seen.assert_not_called()
            db.store_text.assert_not_called()
        asyncio.run(run())

    def test_private_callback_rejects_unauthorized_users(self):
        async def run():
            update = update_for("ignored")
            update.callback_query = SimpleNamespace(data="privacy:resume", answer=AsyncMock())
            db = MagicMock()
            with patch.dict(__import__("os").environ, {"ALLOWED_USER_ID": "41"}), patch(
                "admin_telegram.store", return_value=db
            ):
                await privacy_callback(update, SimpleNamespace())
            db.set_consent.assert_not_called()
            update.callback_query.answer.assert_awaited_once()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
