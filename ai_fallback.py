"""Handle temporary Gemini overload without masking permanent configuration errors."""
from __future__ import annotations

import asyncio


RETRYABLE_CODES = {429, 500, 502, 503, 504}


def is_retryable_gemini_error(exc: Exception) -> bool:
    """Only switch providers for temporary failures, never for bad credentials."""
    code = getattr(exc, "code", None)
    try:
        return int(code) in RETRYABLE_CODES
    except (ValueError, TypeError):
        return False


async def generate_with_fallback(teacher, groq, message: str,
                                 history: list[tuple[str, str]],
                                 practice: bool = False) -> tuple[str, str]:
    """Try Gemini, retry once on temporary failure, then try Groq if configured.

    Returns the assistant answer and the provider name. Never loses the user text
    or edits conversation history; caller stores the successful answer only.
    """
    try:
        return await teacher.reply(message, history, practice=practice), "gemini"
    except Exception as original:
        if not is_retryable_gemini_error(original):
            raise

    await asyncio.sleep(1.0)
    try:
        return await teacher.reply(message, history, practice=practice), "gemini"
    except Exception as retry_error:
        if not is_retryable_gemini_error(retry_error):
            raise
        if groq is None:
            raise
    return await groq.answer_general(message, history, practice=practice), "groq"
