"""Notification-first transcript recording and privacy menu tests."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from admin_store import AdminStore
from admin_telegram import observe, privacy_callback
from bot import BOT_COMMANDS


class TranscriptPolicyTests(unittest.TestCase):
    def make_update(self, text="Merhaba", uid=42):
        message = SimpleNamespace(text=text, reply_text=AsyncMock())
        return SimpleNamespace(
            effective_user=SimpleNamespace(
                id=uid, username="example", first_name="Example", is_bot=False
            ),
            effective_chat=SimpleNamespace(type="private"),
            effective_message=message,
            message=message,
        )

    def test_new_user_is_not_recorded_before_notice(self):
        async def run():
            update = self.make_update("Gizli ilk mesaj")
            db = MagicMock()
            db.notice_status.return_value = (True, False, False)
            with patch("admin_telegram.store", return_value=db):
                await observe(update, SimpleNamespace())
            update.message.reply_text.assert_awaited_once()
            text = update.message.reply_text.call_args.args[0]
            self.assertIn("bot sahibi", text)
            self.assertIn("/gizlilik", text)
            db.mark_notified.assert_called_once_with(42)
            db.store_text.assert_not_called()
        asyncio.run(run())

    def test_previous_user_off_stays_off_in_notice(self):
        async def run():
            update = self.make_update("Kayıt öncesi")
            db = MagicMock()
            db.notice_status.return_value = (True, True, False)
            with patch("admin_telegram.store", return_value=db):
                await observe(update, SimpleNamespace())
            text = update.message.reply_text.call_args.args[0]
            self.assertIn("önceki gizlilik tercihin korunuyor", text.lower())
            db.store_text.assert_not_called()
        asyncio.run(run())

    def test_after_notice_records_subsequent_message_only(self):
        async def run():
            update = self.make_update("İkinci mesaj")
            db = MagicMock()
            db.notice_status.return_value = (False, False, True)
            with patch("admin_telegram.store", return_value=db):
                await observe(update, SimpleNamespace())
            update.message.reply_text.assert_not_awaited()
            db.store_text.assert_called_once_with(42, "user", "İkinci mesaj")
        asyncio.run(run())

    def test_slash_commands_never_archived(self):
        async def run():
            update = self.make_update("/gizlilik")
            db = MagicMock()
            db.notice_status.return_value = (False, False, True)
            with patch("admin_telegram.store", return_value=db):
                await observe(update, SimpleNamespace())
            db.store_text.assert_not_called()
        asyncio.run(run())

    def test_policy_migration_preserves_prior_settings(self):
        db = AdminStore("fake-connection-string")
        connection = MagicMock()
        connection.__enter__.return_value = connection
        with patch.object(db, "_connect", return_value=connection):
            db.setup()
            db.mark_notified(42)
        queries = [call.args[0] for call in connection.execute.call_args_list]
        self.assertTrue(any("ADD COLUMN IF NOT EXISTS legacy_record" in q for q in queries))
        self.assertTrue(any("ADD COLUMN IF NOT EXISTS notice_shown_at" in q for q in queries))
        mutation = next(q for q in queries if "SET notice_shown_at=NOW()" in q)
        self.assertIn("WHEN legacy_record=FALSE THEN TRUE", mutation)
        self.assertIn("ELSE transcript_enabled", mutation)

    def test_user_can_disable_and_erase_records(self):
        async def run():
            query = SimpleNamespace(
                data="privacy:stop",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
            )
            upd = SimpleNamespace(
                effective_chat=SimpleNamespace(type="private"),
                effective_user=SimpleNamespace(id=42),
                callback_query=query,
            )
            db = MagicMock()
            db.consent.return_value = (False, False)
            with patch("admin_telegram.store", return_value=db):
                await privacy_callback(upd, SimpleNamespace())
            db.delete_transcripts.assert_called_once_with(42)
            query.answer.assert_awaited_once()
            self.assertIn("KAPALI", query.edit_message_text.call_args.args[0])
        asyncio.run(run())

    def test_registration_menu_is_not_cluttered(self):
        names = {command.command for command in BOT_COMMANDS}
        self.assertIn("gizlilik", names)
        for old in ("kayit_ac", "kayit_kapat", "kayit_sil"):
            self.assertNotIn(old, names)


if __name__ == "__main__":
    unittest.main()
