"""Telegram entry point: menus, lessons, quizzes, spaced repetition and Gemini."""

import asyncio
import io
import logging
import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from ai import GeminiTeacher
from curriculum import LESSONS, lesson_for, render_lesson
from db import ProgressDB
from quiz import questions_for

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# httpx request URLs include Telegram bot tokens. Never log these requests.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
LOG = logging.getLogger("english-buddy")

MENU = ReplyKeyboardMarkup([
    ["📚 Ders", "🧠 Test"], ["🔁 Tekrar", "💬 Konuşma"],
    ["❓ AI Soru Sor", "📊 İlerleme"], ["🔊 Telaffuz", "➡️ Sonraki gün"],
], resize_keyboard=True)

if os.getenv("DATABASE_URL"):
    from postgres_db import PostgresProgressDB
    DB = PostgresProgressDB(os.environ["DATABASE_URL"])
else:
    DB = ProgressDB(os.getenv("DB_PATH", "english_buddy.sqlite3"))
TEACHER = None
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0") or 0)


def authorized(update: Update) -> bool:
    if update.effective_user is None or update.effective_chat is None:
        return False
    if update.effective_chat.type != "private":
        return False
    return not ALLOWED_USER_ID or update.effective_user.id == ALLOWED_USER_ID


async def check_access(update: Update) -> bool:
    if authorized(update):
        return True
    if update.effective_message:
        await update.effective_message.reply_text("Bu bot özel kullanım içindir veya yalnızca özel sohbetlerde çalışır.")
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    user_id = update.effective_user.id
    DB.ensure_user(user_id)
    context.user_data["mode"] = "ask"
    await update.message.reply_text(
        "👋 English Buddy'ye hoş geldin! Sıfırdan günlük İngilizce öğreneceğiz.\n\n"
        "📚 Ders: Bugünün 5 kelimesi ve 3 cümlesi\n"
        "🧠 Test: Kısa çoktan seçmeli sınav\n"
        "🔁 Tekrar: Zamanı gelen kelimeler\n"
        "💬 Konuşma: Gemini ile İngilizce pratik\n"
        "❓ AI Soru Sor: Aklına geleni sor\n"
        "🔊 Telaffuz: Bir kelimenin sesini dinle\n\n"
        "İlk ders için 📚 Ders'e dokun. Bana doğrudan mesaj da yazabilirsin.",
        reply_markup=MENU,
    )


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show your Telegram ID so you can secure ALLOWED_USER_ID (even before access is set)."""
    if update.effective_chat and update.effective_chat.type == "private" and update.effective_user:
        await update.message.reply_text(
            f"🪪 Telegram kullanıcı ID'n: {update.effective_user.id}\n"
            "Bunu .env dosyasında ALLOWED_USER_ID alanına yazabilirsin."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    await update.message.reply_text(
        "/start başlangıç menüsü\n/lesson ders\n/quiz mini test\n/review tekrar\n"
        "/chat İngilizce konuşma\n/ask serbest soru\n/speak hello telaffuz\n"
        "/progress ilerleme\n/next sıradaki gün\n/whoami ID öğren\n/help yardım\n\n"
        "Sesli mesaj gönderirsen Gemini konuşmanı çözümleyip geri bildirim verir.",
        reply_markup=MENU,
    )


async def lesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    user_id = update.effective_user.id
    day = DB.day(user_id)
    DB.learn_words(user_id, lesson_for(day)["words"])
    await update.message.reply_text(render_lesson(day), reply_markup=MENU)


async def next_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    old = DB.day(update.effective_user.id)
    new = DB.next_day(update.effective_user.id, len(LESSONS))
    if new == old:
        await update.message.reply_text("🎉 İlk 7 günlük programı tamamladın! Dersleri ve tekrarları sürdürebilirsin.")
    else:
        await update.message.reply_text(f"🎯 Artık {new}. gündesin. /lesson yazıp yeni derse geç!")


def quiz_keyboard(question: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{i+1}. {option}", callback_data=f"quiz:{i}")]
        for i, option in enumerate(question["options"])
    ])


def quiz_text(state: dict) -> str:
    i = state["index"]
    question = state["questions"][i]
    return (f"🧠 {state['mode'].upper()} — Soru {i + 1}/{len(state['questions'])}\n\n"
            f"'{question['english']}' Türkçede ne demek?")


async def begin_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE, review: bool = False) -> None:
    if not await check_access(update):
        return
    user_id = update.effective_user.id
    if review:
        words = DB.due_words(user_id, limit=5)
        if not words:
            await update.message.reply_text(
                "✅ Bugün için tekrar bekleyen kelimen yok. /lesson ile dersine devam et."
            )
            return
    else:
        words = lesson_for(DB.day(user_id))["words"]
    questions = questions_for(words)
    context.user_data["quiz_state"] = {
        "mode": "tekrar" if review else "test", "questions": questions,
        "index": 0, "score": 0, "message_id": None,
    }
    state = context.user_data["quiz_state"]
    message = await update.message.reply_text(quiz_text(state), reply_markup=quiz_keyboard(questions[0]))
    state["message_id"] = message.message_id


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await begin_quiz(update, context)


async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await begin_quiz(update, context, review=True)


async def quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not authorized(update):
        await query.answer("Erişim yok.", show_alert=True)
        return
    state = context.user_data.get("quiz_state")
    if not state or query.message.message_id != state.get("message_id"):
        await query.answer("Bu test artık geçerli değil. /quiz ile yenisini başlat.", show_alert=True)
        return
    try:
        selected = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await query.answer("Geçersiz cevap.")
        return
    await query.answer()
    index = state["index"]
    question = state["questions"][index]
    correct = selected == question["correct_index"]
    state["score"] += int(correct)
    if state["mode"] == "tekrar":
        DB.review_result(update.effective_user.id, question["english"], correct)
    state["index"] += 1
    feedback = ("✅ Doğru!" if correct else f"❌ Doğru yanıt: {question['turkish']}")
    if state["index"] == len(state["questions"]):
        DB.log_quiz(update.effective_user.id, state["score"], len(state["questions"]))
        await query.edit_message_text(
            f"{feedback}\n\n🎉 Bitti! Sonuç: {state['score']}/{len(state['questions'])}\n"
            "Kelimelerini /review ile tekrar edebilirsin."
        )
        context.user_data.pop("quiz_state", None)
    else:
        new_question = state["questions"][state["index"]]
        await query.edit_message_text(
            f"{feedback}\n\n{quiz_text(state)}", reply_markup=quiz_keyboard(new_question)
        )


async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    user_id = update.effective_user.id
    stat = DB.stats(user_id)
    percent = round(stat["correct"] / stat["total"] * 100) if stat["total"] else 0
    due = len(DB.due_words(user_id, limit=100))
    await update.message.reply_text(
        f"📊 İlerlemen\n\n📅 Ders: {stat['day']}/7\n"
        f"🗂️ Görülen kelime: {stat['words']}\n🧠 Bitirilen test: {stat['quizzes']}\n"
        f"🎯 Doğru cevap: {stat['correct']}/{stat['total']} (%{percent})\n"
        f"🔁 Tekrar bekleyen: {due}", reply_markup=MENU,
    )


async def chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    context.user_data["mode"] = "chat"
    context.user_data["chat_history"] = []
    await update.message.reply_text(
        "💬 Konuşma pratiğine geçtik! Benimle çok basit İngilizce konuş.\n"
        "İlk soru: Hello! What's your name? (Merhaba, adın ne?)\n\n"
        "Tekrar soru-cevap moduna dönmek için /ask yaz.", reply_markup=MENU,
    )


async def ask_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    context.user_data["mode"] = "ask"
    context.user_data["chat_history"] = []
    await update.message.reply_text(
        "❓ Gemini'ye dilediğini sor. Örnek: 'I want ile I need arasında ne fark var?'",
        reply_markup=MENU,
    )


async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    if len(message) > 3000:
        await update.message.reply_text("Bir seferde en fazla 3000 karakter gönderebilirsin.")
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    history = context.user_data.setdefault("chat_history", [])
    practice = context.user_data.get("mode", "ask") == "chat"
    try:
        answer = await TEACHER.reply(message, history, practice=practice)
    except Exception:
        LOG.exception("Gemini text request failed")
        await update.message.reply_text(
            "⚠️ Gemini'den yanıt alamadım. API anahtarını, model erişimini ve kotanı kontrol et."
        )
        return
    history.extend([("user", message), ("model", answer)])
    context.user_data["chat_history"] = history[-10:]
    # Telegram messages are limited in size. Split long responses safely.
    for chunk_start in range(0, len(answer), 3900):
        await update.message.reply_text(answer[chunk_start:chunk_start + 3900])


def make_mp3(phrase: str) -> bytes:
    """gTTS requires an internet connection; it is independent of Gemini API."""
    from gtts import gTTS
    out = io.BytesIO()
    gTTS(text=phrase, lang="en", slow=True).write_to_fp(out)
    return out.getvalue()


async def speak(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    phrase = " ".join(context.args).strip() if context.args else ""
    if not phrase:
        await update.message.reply_text("🔊 Örnek: /speak Good morning, how are you?")
        return
    if len(phrase) > 150:
        await update.message.reply_text("En fazla 150 karakterlik bir İngilizce cümle gönder.")
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_VOICE)
    try:
        mp3 = await asyncio.to_thread(make_mp3, phrase)
        audio = io.BytesIO(mp3)
        audio.name = "pronunciation.mp3"
        await update.message.reply_audio(audio=audio, title=f"Telaffuz: {phrase[:50]}")
    except Exception:
        LOG.exception("TTS error")
        await update.message.reply_text("⚠️ Ses şu an oluşturulamadı; internet erişimini kontrol et.")


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    voice = update.message.voice
    if voice.duration > 40 or (voice.file_size and voice.file_size > 5_000_000):
        await update.message.reply_text("Ses kaydını 40 saniyeden kısa tutabilir misin?")
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        telegram_file = await voice.get_file()
        audio = io.BytesIO()
        await telegram_file.download_to_memory(out=audio)
        reply = await TEACHER.analyse_voice(audio.getvalue())
    except Exception:
        LOG.exception("Gemini voice request failed")
        await update.message.reply_text("⚠️ Ses analiz edilemedi. API kotasını ve modelini kontrol et.")
        return
    await update.message.reply_text(reply[:4000])


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    text = update.message.text.strip()
    button_map = {
        "📚 Ders": lesson,
        "🧠 Test": quiz_command,
        "🔁 Tekrar": review_command,
        "💬 Konuşma": chat_mode,
        "❓ AI Soru Sor": ask_mode,
        "📊 İlerleme": progress,
        "➡️ Sonraki gün": next_day,
    }
    if text in button_map:
        await button_map[text](update, context)
    elif text == "🔊 Telaffuz":
        await update.message.reply_text("🔊 Dinlemek için /speak Hello yaz.")
    else:
        await ask_ai(update, context, text)


def build_application():
    """Configure Telegram handlers without starting polling or a server."""
    global TEACHER
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not token or not api_key:
        raise SystemExit(".env dosyasında TELEGRAM_BOT_TOKEN ve GEMINI_API_KEY ayarlanmalı.")
    TEACHER = GeminiTeacher(api_key)
    app = ApplicationBuilder().token(token).build()
    for command, handler in [
        ("start", start), ("whoami", whoami), ("help", help_command), ("lesson", lesson),
        ("next", next_day), ("quiz", quiz_command), ("review", review_command),
        ("progress", progress), ("chat", chat_mode), ("ask", ask_mode),
        ("speak", speak),
    ]:
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(quiz_answer, pattern=r"^quiz:\d+$"))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    LOG.info("English Buddy initialized (Gemini model: %s)", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
    return app


def main() -> None:
    """Local development: long polling. Production: webapp.py webhook."""
    app = build_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
