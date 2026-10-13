"""Regressions for transparent, first-use chat-recording choice."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.ext import ApplicationHandlerStop

from admin_store import AdminStore
from admin_telegram import privacy_gate, privacy_notice, observe


def text_update(message="/start", uid=45):
    msg = SimpleNamespace(text=message, reply_text=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=uid, username="demo", first_name="Demo", is_bot=False
        ),
        effective_chat=SimpleNamespace(type="private"),
        effective_message=msg, message=msg, callback_query=None,
    )


class PrivacyGateTests(unittest.TestCase):
    def test_first_message_shows_two_choices_no_transcript(self):
        async def run():
            db = MagicMock()
            db.privacy_status.return_value = (0, False)
            update = text_update()
            with patch("admin_telegram.store", return_value=db):
                with self.assertRaises(ApplicationHandlerStop):
                    await privacy_gate(update, SimpleNamespace())
            msg = update.message.reply_text.call_args.args[0]
            keyboard = update.message.reply_text.call_args.kwargs["reply_markup"]
            self.assertIn("Kayıtlı kullan", msg)
            self.assertIn("Kayıtsız devam et", msg)
            self.assertEqual(
                keyboard.inline_keyboard[1][0].callback_data, "privacy:decline"
            )
            db.acknowledge_privacy.assert_not_called()
            db.store_text.assert_not_called()
        asyncio.run(run())

    def test_accepted_user_not_prompted_again(self):
        async def run():
            db = MagicMock()
            db.privacy_status.return_value = (1, True)
            update = text_update("Python nedir?")
            with patch("admin_telegram.store", return_value=db):
                await privacy_gate(update, SimpleNamespace())
            update.message.reply_text.assert_not_awaited()
        asyncio.run(run())

    def test_declined_user_can_keep_using_bot(self):
        async def run():
            db = MagicMock()
            db.privacy_status.return_value = (1, False)
            update = text_update("Ben de bot kullanacağım")
            with patch("admin_telegram.store", return_value=db):
                await privacy_gate(update, SimpleNamespace())
            update.message.reply_text.assert_not_awaited()
        asyncio.run(run())

    def test_privacy_and_delete_commands_always_accessible(self):
        async def run():
            db = MagicMock()
            db.privacy_status.return_value = (0, False)
            with patch("admin_telegram.store", return_value=db):
                for cmd in ("/gizlilik", "/kayit_sil"):
                    update = text_update(cmd)
                    await privacy_gate(update, SimpleNamespace())
                    update.message.reply_text.assert_not_awaited()
            db.store_text.assert_not_called()
        asyncio.run(run())

    def test_privacy_callback_explicitly_registers_decision(self):
        async def run():
            for option, value in (("privacy:accept", True), ("privacy:decline", False)):
                db = MagicMock()
                callback = SimpleNamespace(
                    data=option,
                    answer=AsyncMock(),
                    edit_message_text=AsyncMock(),
                )
                update = text_update()
                update.callback_query = callback
                update.message = None
                with patch("admin_telegram.store", return_value=db):
                    with self.assertRaises(ApplicationHandlerStop):
                        await privacy_gate(update, SimpleNamespace())
                db.acknowledge_privacy.assert_called_once_with(45, value)
                callback.answer.assert_awaited_once()
                callback.edit_message_text.assert_awaited_once()
                db.store_text.assert_not_called()
        asyncio.run(run())

    def test_declining_deletes_existing_transcripts_atomically(self):
        db = AdminStore("fake")
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(db, "_connect", return_value=conn):
            db.acknowledge_privacy(45, False)
        statements = [call.args[0] for call in conn.execute.call_args_list]
        self.assertTrue(any("privacy_notice_version" in s for s in statements))
        self.assertTrue(any("DELETE FROM admin_chat_messages" in s for s in statements))

    def test_accepting_does_not_delete_existing_messages(self):
        db = AdminStore("fake")
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(db, "_connect", return_value=conn):
            db.acknowledge_privacy(45, True)
        statements = [call.args[0] for call in conn.execute.call_args_list]
        self.assertFalse(any("DELETE FROM admin_chat_messages" in s for s in statements))

    def test_no_default_recording_for_declined_user(self):
        db = AdminStore("fake")
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.fetchone.return_value = (False,)
        with patch.object(db, "_connect", return_value=conn):
            db.store_text(45, "user", "Özel soru")
        self.assertFalse(any(
            "INSERT INTO admin_chat_messages" in call.args[0]
            for call in conn.execute.call_args_list
        ))


if __name__ == "__main__":
    unittest.main()
