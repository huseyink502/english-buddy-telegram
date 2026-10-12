"""Ensure free-form AI chat is not forced into the English-teacher persona."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from ai import CHAT_PROMPT, GENERAL_ASSISTANT_PROMPT, GeminiTeacher
from bot import ask_mode


class GeneralAIQuestionsTests(unittest.TestCase):
    def make_teacher(self):
        model = SimpleNamespace(generate_content=AsyncMock(return_value=SimpleNamespace(text="Yanıt")))
        teacher = GeminiTeacher.__new__(GeminiTeacher)
        teacher.client = SimpleNamespace(aio=SimpleNamespace(models=model))
        return teacher, model

    def test_general_question_uses_broad_assistant(self):
        async def run():
            teacher, model = self.make_teacher()
            reply = await teacher.reply("Bana Python ile bir örnek göster", [])
            self.assertEqual(reply, "Yanıt")
            kwargs = model.generate_content.call_args.kwargs
            prompt = kwargs["config"].system_instruction
            self.assertEqual(prompt, GENERAL_ASSISTANT_PROMPT)
            self.assertIn("yazılım", prompt)
            self.assertIn("gündelik yaşam", prompt)
            self.assertNotIn("Sen English Buddy adlı", prompt)
            self.assertGreaterEqual(kwargs["config"].max_output_tokens, 1200)
        asyncio.run(run())

    def test_english_practice_keeps_teacher(self):
        async def run():
            teacher, model = self.make_teacher()
            await teacher.reply("Hello", [], practice=True)
            kwargs = model.generate_content.call_args.kwargs
            self.assertEqual(kwargs["config"].system_instruction, CHAT_PROMPT)
            self.assertIn("İngilizce öğretmeni", kwargs["config"].system_instruction)
        asyncio.run(run())

    def test_chat_history_is_forwarded_in_general_mode(self):
        async def run():
            teacher, model = self.make_teacher()
            await teacher.reply("Peki neden?", [("user", "Pil nasıl çalışır?"), ("model", "Kimyasal enerjiyle.")])
            contents = model.generate_content.call_args.kwargs["contents"]
            self.assertEqual([c.role for c in contents], ["user", "model", "user"])
            self.assertEqual(contents[-1].parts[0].text, "Peki neden?")
        asyncio.run(run())

    def test_ask_menu_mentions_non_english_topics(self):
        async def run():
            msg = SimpleNamespace(reply_text=AsyncMock())
            update = SimpleNamespace(message=msg)
            context = SimpleNamespace(user_data={"mode": "chat", "chat_history": [("user", "old")]})
            import bot
            old_check = bot.check_access
            bot.check_access = AsyncMock(return_value=True)
            try:
                await ask_mode(update, context)
            finally:
                bot.check_access = old_check
            self.assertEqual(context.user_data["mode"], "ask")
            self.assertEqual(context.user_data["chat_history"], [])
            text = msg.reply_text.call_args.args[0]
            self.assertIn("Python", text)
            self.assertIn("matematik", text)
            self.assertIn("\n\n", text)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
