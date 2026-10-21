"""Regression tests for Telegram's English learning flow (no live API keys)."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot
from curriculum import LESSONS, LESSON_GUIDANCE, render_lesson
from db import ProgressDB
from learning_time import TURKEY_TZ
from quiz import questions_for


class EnglishLessonsTests(unittest.TestCase):
    def test_every_beginner_dialogue_has_a_translation_and_a_task(self):
        for day, lesson in enumerate(LESSONS, 1):
            guide = LESSON_GUIDANCE[day]
            self.assertEqual(len(lesson["dialogue"]), len(guide["dialogue_tr"]))
            text = render_lesson(day)
            self.assertIn("Mini alıştırma", text)
            self.assertIn("Mini diyalog (çevirili)", text)
            self.assertIn(guide["tip"], text)
            self.assertIn("\n", text)
            self.assertNotIn("\\n", text)

    def test_questions_reproducible_with_seed(self):
        import random
        words = LESSONS[0]["words"]
        self.assertEqual(
            questions_for(words, random.Random(27)),
            questions_for(words, random.Random(27)),
        )

    def test_turkey_timezone_is_explicit(self):
        self.assertEqual(TURKEY_TZ.key, "Europe/Istanbul")


class EnglishBotFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.progress = ProgressDB(str(Path(self.tmp.name) / "test.sqlite3"))
        self.patches = [
            patch.object(bot, "DB", self.progress),
            patch.object(bot, "check_access", new_callable=AsyncMock, return_value=True),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def make_update(self, message_text="hello"):
        message = SimpleNamespace(
            text=message_text,
            reply_text=AsyncMock(return_value=SimpleNamespace(message_id=73)),
            reply_audio=AsyncMock(),
        )
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=812),
            effective_chat=SimpleNamespace(id=812),
            message=message,
        )

    def test_quiz_first_visit_shows_lesson_and_saves_words(self):
        async def run():
            update = self.make_update()
            context = SimpleNamespace(user_data={}, bot=SimpleNamespace())
            await bot.begin_quiz(update, context)
            self.assertEqual(update.message.reply_text.await_count, 2)
            self.assertIn("Teste geçmeden", update.message.reply_text.await_args_list[0].args[0])
            self.assertEqual(self.progress.stats(812)["words"], 5)
            self.assertEqual(context.user_data["quiz_state"]["message_id"], 73)

            # Reopening the quiz must not repeat the introductory lesson.
            update.message.reply_text.reset_mock()
            await bot.begin_quiz(update, context)
            self.assertEqual(update.message.reply_text.await_count, 1)
        asyncio.run(run())

    def test_chat_mode_remembers_the_first_question(self):
        async def run():
            update = self.make_update()
            context = SimpleNamespace(user_data={})
            await bot.chat_mode(update, context)
            self.assertEqual(context.user_data["mode"], "chat")
            self.assertEqual(
                context.user_data["chat_history"],
                [("model", "Hello! What's your name?")],
            )
        asyncio.run(run())

    def test_pronunciation_button_accepts_followup_text(self):
        async def run():
            update = self.make_update("🔊 Telaffuz")
            context = SimpleNamespace(user_data={}, args=None)
            await bot.speak(update, context)
            self.assertEqual(context.user_data["mode"], "speak")
            update.message.text = "Good morning!"
            with patch.object(bot, "admin_input", new_callable=AsyncMock, return_value=False), \
                    patch.object(bot, "send_pronunciation", new_callable=AsyncMock) as spoken:
                await bot.on_text(update, context)
                spoken.assert_awaited_once_with(update, context, "Good morning!")
        asyncio.run(run())

    def test_fallback_label_does_not_pollute_teacher_history(self):
        async def run():
            update = self.make_update()
            context = SimpleNamespace(
                user_data={"mode": "chat", "chat_history": []},
                bot=SimpleNamespace(send_chat_action=AsyncMock()),
            )
            with patch.object(bot, "generate_with_fallback", new_callable=AsyncMock,
                              return_value=("Hello! How are you?", "groq")), \
                    patch.object(bot, "note_reply", new_callable=AsyncMock):
                await bot.ask_ai(update, context, "Hello")
            self.assertEqual(
                context.user_data["chat_history"][-1],
                ("model", "Hello! How are you?"),
            )
            self.assertIn("Groq", update.message.reply_text.await_args.args[0])
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
