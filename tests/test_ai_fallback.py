"""Unit tests for resilience when Gemini responds with HTTP 503."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from ai_fallback import generate_with_fallback, is_retryable_gemini_error


class APIError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


class AIFallbackTests(unittest.TestCase):
    def test_detect_temporary_errors_only(self):
        for code in (429, 500, 502, 503, 504):
            self.assertTrue(is_retryable_gemini_error(APIError(code)))
        for code in (400, 401, 403, 404):
            self.assertFalse(is_retryable_gemini_error(APIError(code)))

    def test_gemini_success_does_not_touch_groq(self):
        async def run():
            teacher = type("Teacher", (), {"reply": AsyncMock(return_value="Gemini ok")})()
            groq = type("Groq", (), {"answer_general": AsyncMock()})()
            result = await generate_with_fallback(teacher, groq, "Merhaba", [])
            self.assertEqual(result, ("Gemini ok", "gemini"))
            groq.answer_general.assert_not_awaited()
        asyncio.run(run())

    def test_retry_then_recover_with_gemini(self):
        async def run():
            teacher = type("Teacher", (), {
                "reply": AsyncMock(side_effect=[APIError(503), "Tekrar çalıştı"])
            })()
            groq = type("Groq", (), {"answer_general": AsyncMock()})()
            with patch("ai_fallback.asyncio.sleep", new_callable=AsyncMock):
                result = await generate_with_fallback(teacher, groq, "Merhaba", [])
            self.assertEqual(result, ("Tekrar çalıştı", "gemini"))
            self.assertEqual(teacher.reply.await_count, 2)
            groq.answer_general.assert_not_awaited()
        asyncio.run(run())

    def test_groq_after_two_transient_errors(self):
        async def run():
            teacher = type("Teacher", (), {
                "reply": AsyncMock(side_effect=[APIError(503), APIError(503)])
            })()
            groq = type("Groq", (), {
                "answer_general": AsyncMock(return_value="Groq ok")
            })()
            with patch("ai_fallback.asyncio.sleep", new_callable=AsyncMock):
                result = await generate_with_fallback(
                    teacher, groq, "Python nedir?", [("user", "Selam")], practice=False
                )
            self.assertEqual(result, ("Groq ok", "groq"))
            groq.answer_general.assert_awaited_once()
        asyncio.run(run())

    def test_bad_api_key_does_not_use_groq(self):
        async def run():
            teacher = type("Teacher", (), {"reply": AsyncMock(side_effect=APIError(401))})()
            groq = type("Groq", (), {"answer_general": AsyncMock()})()
            with self.assertRaises(APIError):
                await generate_with_fallback(teacher, groq, "Hello", [])
            groq.answer_general.assert_not_awaited()
        asyncio.run(run())

    def test_no_groq_available_raises(self):
        async def run():
            teacher = type("Teacher", (), {
                "reply": AsyncMock(side_effect=[APIError(503), APIError(503)])
            })()
            with patch("ai_fallback.asyncio.sleep", new_callable=AsyncMock):
                with self.assertRaises(APIError):
                    await generate_with_fallback(teacher, None, "Hello", [])
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
