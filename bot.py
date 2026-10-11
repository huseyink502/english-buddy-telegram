"""Telegram entry point: menus, lessons, quizzes, spaced repetition and Gemini."""

import asyncio
import io
import logging
import os
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from ai import GeminiTeacher
from groq_ai import GroqNewsAssistant
from news_memory import NewsMemory, TOPICS
from curriculum import LESSONS, lesson_for, render_lesson
from db import ProgressDB
from news import CATEGORIES, FEEDS, find_article, load_category
from quiz import questions_for

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# httpx request URLs include Telegram bot tokens. Never log these requests.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
LOG = logging.getLogger("english-buddy")

MENU = ReplyKeyboardMarkup([
    ["📚 Ders", "🧠 Test"], ["🔁 Tekrar", "💬 Konuşma"],
    ["❓ AI Soru Sor", "📰 Haberler"], ["🎮 Oyun Gündemi", "🇹🇷 Türkiye"],
    ["🏛️ Siyaset"],
    ["📊 İlerleme", "🔊 Telaffuz"],
    ["➡️ Sonraki gün"],
], resize_keyboard=True)

if os.getenv("DATABASE_URL"):
    from postgres_db import PostgresProgressDB
    DB = PostgresProgressDB(os.environ["DATABASE_URL"])
else:
    DB = ProgressDB(os.getenv("DB_PATH", "english_buddy.sqlite3"))
TEACHER = None
GROQ_NEWS_AI = None


@lru_cache(maxsize=1)
def get_news_memory():
    """Initialize optional Neon archive on first use."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return None
    memory = NewsMemory(url)
    memory.setup()
    return memory


ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0") or 0)

BOT_COMMANDS = [
    BotCommand("start", "Ana menüyü aç"),
    BotCommand("haberler", "Türkiye ve dünya gündemi"),
    BotCommand("turkiye", "Türkiye'den güncel haberler"),
    BotCommand("siyaset", "Türkiye siyaseti ve partiler"),
    BotCommand("tbmm", "TBMM ve Meclis haberleri"),
    BotCommand("sondakika", "Türkiye son dakika haberleri"),
    BotCommand("oyun", "Genel oyun dünyasından haberler"),
    BotCommand("brawlstars", "Brawl Stars güncel haberleri"),
    BotCommand("gta6", "GTA 6 haberleri ve duyuruları"),
    BotCommand("ozet", "Günlük haber özetini göster"),
    BotCommand("ozet_ac", "Günlük haber bildirimlerini aç"),
    BotCommand("ozet_kapat", "Günlük haber bildirimlerini kapat"),
    BotCommand("takip", "Takip edilen haber kategorileri"),
    BotCommand("gelismeler", "Arşivdeki haber gelişmeleri"),
    BotCommand("lesson", "Günlük İngilizce dersi"),
    BotCommand("quiz", "Kelime testi"),
    BotCommand("review", "Kelime tekrarları"),
    BotCommand("chat", "İngilizce konuşma pratiği"),
    BotCommand("ask", "Gemini'ye serbest soru sor"),
    BotCommand("progress", "Öğrenme ilerlemesi"),
    BotCommand("speak", "İngilizce telaffuz dinle"),
    BotCommand("next", "Bir sonraki ders günü"),
    BotCommand("help", "Yardım ve komutlar"),
]


async def register_commands(application) -> None:
    """Register slash commands for Telegram's native '/' autocomplete menu."""
    await application.bot.set_my_commands(BOT_COMMANDS)
    LOG.info("Telegram slash command menu updated")



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
        "🔊 Telaffuz: Bir kelimenin sesini dinle\n"
        "📰 Haberler: Türkiye, siyaset ve son dakika haberleri; Gemini'ye sor\n"
        "🎮 Oyun Gündemi: Oyunlar, Brawl Stars ve GTA 6 haberleri\n\n"
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
        "/progress ilerleme\n/next sıradaki gün\n/haberler son haberler\n"
        "/sondakika Türkiye son dakika\n/siyaset siyasi haberler\n"
        "/turkiye Türkiye gündemi\n/tbmm Meclis haberleri\n"
        "/ozet günlük özet\n/ozet_ac günlük bildirimi aç\n"
        "/ozet_kapat bildirimi kapat\n/takip kategori seç\n"
        "/gelismeler gta6 arşivi aç\n"
        "/oyun oyun dünyası\n/brawlstars Brawl Stars\n/gta6 GTA 6\n"
        "/whoami ID öğren\n/help yardım\n\n"
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



NEWS_CATEGORY_KEYBOARD = [
    [InlineKeyboardButton("🇹🇷 Türkiye", callback_data="news:turkiye"),
     InlineKeyboardButton("🏛️ Siyaset", callback_data="news:siyaset")],
    [InlineKeyboardButton("🚨 TR Son Dakika", callback_data="news:trson"),
     InlineKeyboardButton("🏢 TBMM", callback_data="news:tbmm")],
    [InlineKeyboardButton("📰 TRT Son Dakika", callback_data="news:son"),
     InlineKeyboardButton("🗞️ Gündem", callback_data="news:gundem")],
    [InlineKeyboardButton("🌍 Dünya", callback_data="news:dunya"),
     InlineKeyboardButton("💰 Ekonomi", callback_data="news:ekonomi")],
    [InlineKeyboardButton("💻 Teknoloji", callback_data="news:teknoloji"),
     InlineKeyboardButton("🌐 BBC Türkçe", callback_data="news:bbc")],
    [InlineKeyboardButton("🎮 Oyun Gündemi", callback_data="news:oyun")],
    [InlineKeyboardButton("⭐ Brawl Stars", callback_data="news:brawlstars"),
     InlineKeyboardButton("🚗 GTA 6", callback_data="news:gta6")],
]


async def show_news(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    category: str = "turkiye", query=None) -> None:
    """List source headlines, publish dates and selectable article buttons."""
    try:
        articles = await load_category(category)
    except Exception:
        LOG.exception("RSS feed fetch or parsing failed for %s", category)
        retry_command = "/oyun" if category in ("oyun", "brawlstars", "gta6") else "/haberler"
        msg = f"⚠️ Haber kaynağına şu an erişilemiyor. Biraz sonra {retry_command} ile tekrar dene."
        if query:
            await query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return
    context.user_data["current_news_category"] = category
    label, source, _url = FEEDS[category]
    emoji = "🎮" if category in ("oyun", "brawlstars", "gta6") else "📰"
    header = f"{emoji} {label} — {source}\n\n"
    lines = [
        f"{n}. {article.title}\n   🗞️ {article.source} · 🕒 {article.published_label}"
        for n, article in enumerate(articles[:8], 1)
    ]
    text = header + "\n\n".join(lines) + (
        "\n\nBir haberi seç; Gemini veya Groq'ya o haber hakkında soru sorabilirsin. "
        "Başlık ve özet haber kaynağından gelir."
    )
    buttons = [
        [InlineKeyboardButton(
            f"{number}. {article.title[:45]}" + ("…" if len(article.title) > 45 else ""),
            callback_data=f"article:{article.key}",
        )]
        for number, article in enumerate(articles[:8], 1)
    ]
    buttons.extend(NEWS_CATEGORY_KEYBOARD)
    markup = InlineKeyboardMarkup(buttons)
    if query:
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except BadRequest as exc:
            # Tapping the currently selected category is a harmless no-op.
            if "Message is not modified" not in str(exc):
                raise
    else:
        await update.message.reply_text(text, reply_markup=markup)


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    command = ((update.message.text or "").split()[0].split("@")[0]).lower()
    category_by_command = {
        "/haberler": "turkiye", "/news": "turkiye", "/turkiye": "turkiye",
        "/sondakika": "trson", "/siyaset": "siyaset", "/tbmm": "tbmm",
        "/oyun": "oyun", "/brawlstars": "brawlstars", "/gta6": "gta6",
    }
    await show_news(update, context, category=category_by_command.get(command, "turkiye"))


async def news_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not authorized(update):
        await query.answer("Erişim yok.", show_alert=True)
        return
    category = query.data.split(":", 1)[1]
    if category not in CATEGORIES:
        await query.answer("Geçersiz haber kategorisi.", show_alert=True)
        return
    await query.answer()
    await show_news(update, context, category=category, query=query)


async def article_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not authorized(update):
        await query.answer("Erişim yok.", show_alert=True)
        return
    await query.answer()
    article_key = query.data.split(":", 1)[1]
    article = None
    if os.getenv("DATABASE_URL"):
        try:
            memory = await asyncio.to_thread(get_news_memory)
            article = await asyncio.to_thread(memory.get_article, article_key) if memory else None
        except Exception:
            LOG.warning("Archived news lookup unavailable")
    if article is None:
        article = await find_article(article_key)
    if article is None:
        await query.message.reply_text(
            "⚠️ Bu haber artık güncel listede bulunamadı. /haberler ile yeniden seç."
        )
        return
    # Per-user, in-memory selection: prevents another user's questions mixing in.
    context.user_data["selected_news"] = article
    context.user_data["selected_news_category"] = context.user_data.get("current_news_category")
    context.user_data["mode"] = "news"
    context.user_data["news_history"] = []
    await query.message.reply_text(
        f"📰 {article.title}\n\n"
        f"🗞️ Kaynak: {article.source}\n"
        f"🕒 Yayın: {article.published_label} (Türkiye saati)\n\n"
        f"{article.summary or 'Bu kaynak haber özeti paylaşmamış.'}\n\n"
        f"🔗 Haberin tamamı: {article.url}\n\n"
        "💬 Bu haber hakkında sorun varsa doğrudan yazabilirsin. "
        "Yapay zekâ yalnızca RSS bilgilerini ve kayıtlı haber başlıklarını gördüğü için "
        "haberin tam metnini okumuş gibi yanıt vermez.\n"
        "Genel yapay zekâ sohbetine dönmek için /ask yaz."
    )


async def ask_news_ai(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> None:
    if len(question) > 1500:
        await update.message.reply_text("Lütfen haber sorun 1500 karakterden kısa olsun.")
        return
    article = context.user_data.get("selected_news")
    if article is None:
        await update.message.reply_text("Önce /haberler ile bir haber seçmelisin.")
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    history = context.user_data.setdefault("news_history", [])
    try:
        if GROQ_NEWS_AI is not None:
            related = []
            category = context.user_data.get("selected_news_category")
            if category in TOPICS and os.getenv("DATABASE_URL"):
                try:
                    memory = await asyncio.to_thread(get_news_memory)
                    related = await asyncio.to_thread(
                        memory.recent, category,
                        datetime.now(ZoneInfo("Europe/Istanbul")) - timedelta(days=14), 6
                    ) if memory else []
                except Exception:
                    LOG.warning("Archived context unavailable; selected article still available")
            try:
                answer = await GROQ_NEWS_AI.answer_news_question(article, question, history, related)
            except Exception:
                LOG.exception("Groq news AI failed; falling back to Gemini")
                answer = await TEACHER.answer_news_question(article, question, history)
        else:
            answer = await TEACHER.answer_news_question(article, question, history)
    except Exception:
        LOG.exception("News Gemini request failed")
        await update.message.reply_text(
            "⚠️ Gemini habere yanıt veremedi. API kotasını ve bağlantıyı kontrol et."
        )
        return
    history.extend([("user", question), ("model", answer)])
    context.user_data["news_history"] = history[-6:]
    for offset in range(0, len(answer), 3900):
        await update.message.reply_text(answer[offset:offset + 3900])


def topics_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            ("✅ " if category in selected else "⬜ ") + label,
            callback_data=f"topic:{category}"
        )]
        for category, label in TOPICS.items()
    ]
    return InlineKeyboardMarkup(rows)


async def news_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_access(update):
        return
    try:
        memory = await asyncio.to_thread(get_news_memory)
        if memory is None:
            await update.message.reply_text(
                "⚠️ Günlük haber takibi için Neon DATABASE_URL bağlantısı gerekli."
            )
            return
        command = update.message.text.split()[0].split("@")[0].lower()
        user_id = update.effective_user.id
        if command == "/ozet_ac":
            await asyncio.to_thread(memory.subscribe, user_id)
            await update.message.reply_text(
                "✅ Günlük haber özeti açıldı. Türkiye saatiyle 09.00 sonrası gönderilecek. "
                "Kategorileri /takip ile düzenleyebilir, /ozet_kapat ile kapatabilirsin."
            )
        elif command == "/ozet_kapat":
            await asyncio.to_thread(memory.unsubscribe, user_id)
            await update.message.reply_text("🔕 Günlük özet bildirimleri kapatıldı.")
        elif command == "/takip":
            enabled, topics = await asyncio.to_thread(memory.preferences, user_id)
            await update.message.reply_text(
                "📰 Takip edeceğin kategorileri seç:\n"
                + ("Bildirimler açık ✅" if enabled else "Bildirimler kapalı 🔕 /ozet_ac ile aç."),
                reply_markup=topics_keyboard(topics)
            )
        elif command == "/gelismeler":
            category = context.args[0].lower() if context.args else "gta6"
            if category not in TOPICS:
                await update.message.reply_text(
                    "Kullanım: /gelismeler gta6\nKategoriler: "
                    + ", ".join(TOPICS)
                )
                return
            context.user_data["current_news_category"] = category
            recent = await asyncio.to_thread(
                memory.recent, category,
                datetime.now(ZoneInfo("Europe/Istanbul")) - timedelta(days=14), 12
            )
            if not recent:
                await update.message.reply_text(
                    f"{TOPICS[category]} için arşivde henüz haber yok."
                )
                return
            lines = [
                f"{i}. {entry['title'][:140]}\n   {entry['source']} "
                for i, entry in enumerate(recent[:8], 1)
            ]
            buttons = [
                [InlineKeyboardButton(
                    f"{i}. {entry['title'][:48]}",
                    callback_data=f"article:{entry['article_key']}"
                )] for i, entry in enumerate(recent[:8], 1)
            ]
            await update.message.reply_text(
                f"{TOPICS[category]} — son gelişmeler\n\n" + "\n\n".join(lines),
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        elif command == "/ozet":
            _, topics = await asyncio.to_thread(memory.preferences, user_id)
            day = await asyncio.to_thread(memory.latest_summary_day)
            if day is None:
                await update.message.reply_text(
                    "📭 Henüz günlük özet hazırlanmadı. Arka plan taraması çalışınca burada görünecek."
                )
                return
            message = await asyncio.to_thread(memory.formatted_digest, day, topics)
            await update.message.reply_text(message, disable_web_page_preview=True)
    except Exception:
        LOG.exception("News subscription or archive request failed")
        await update.message.reply_text(
            "⚠️ Haber hafızasına erişilemedi. Neon bağlantısını kontrol et."
        )


async def topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not authorized(update):
        await query.answer("Erişim yok.", show_alert=True)
        return
    category = query.data.split(":", 1)[1]
    try:
        memory = await asyncio.to_thread(get_news_memory)
        if memory is None:
            await query.answer("Neon bağlantısı gerekli.", show_alert=True)
            return
        topics = await asyncio.to_thread(memory.toggle_topic, update.effective_user.id, category)
        enabled, _ = await asyncio.to_thread(memory.preferences, update.effective_user.id)
        await query.answer("Takip listesi güncellendi.")
        await query.edit_message_text(
            "📰 Takip edeceğin kategoriler:\n"
            + ("Bildirimler açık ✅" if enabled else "Bildirimler kapalı 🔕 /ozet_ac ile aç."),
            reply_markup=topics_keyboard(topics),
        )
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
    except Exception:
        LOG.exception("Topic update failed")
        await query.answer("Güncellenemedi, Neon bağlantısını kontrol et.", show_alert=True)


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
        "📰 Haberler": news_command,
        "🇹🇷 Türkiye": news_command,
        "🏛️ Siyaset": news_command,
        "📊 İlerleme": progress,
        "➡️ Sonraki gün": next_day,
    }
    if text == "🏛️ Siyaset":
        await show_news(update, context, category="siyaset")
    elif text == "🎮 Oyun Gündemi":
        await show_news(update, context, category="oyun")
    elif text in button_map:
        await button_map[text](update, context)
    elif text == "🔊 Telaffuz":
        await update.message.reply_text("🔊 Dinlemek için /speak Hello yaz.")
    elif context.user_data.get("mode") == "news":
        await ask_news_ai(update, context, text)
    else:
        await ask_ai(update, context, text)


def build_application():
    """Configure Telegram handlers without starting polling or a server."""
    global TEACHER, GROQ_NEWS_AI
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not token or not api_key:
        raise SystemExit(".env dosyasında TELEGRAM_BOT_TOKEN ve GEMINI_API_KEY ayarlanmalı.")
    TEACHER = GeminiTeacher(api_key)
    GROQ_NEWS_AI = GroqNewsAssistant(os.environ["GROQ_API_KEY"].strip()) if os.getenv("GROQ_API_KEY", "").strip() else None
    app = ApplicationBuilder().token(token).post_init(register_commands).build()
    for command, handler in [
        ("start", start), ("whoami", whoami), ("help", help_command), ("lesson", lesson),
        ("next", next_day), ("quiz", quiz_command), ("review", review_command),
        ("progress", progress), ("chat", chat_mode), ("ask", ask_mode),
        ("speak", speak), ("haberler", news_command), ("sondakika", news_command),
        ("turkiye", news_command), ("siyaset", news_command), ("tbmm", news_command),
        ("news", news_command), ("oyun", news_command),
        ("brawlstars", news_command), ("gta6", news_command),
        ("ozet", news_settings), ("ozet_ac", news_settings),
        ("ozet_kapat", news_settings), ("takip", news_settings),
        ("gelismeler", news_settings),
    ]:
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(quiz_answer, pattern=r"^quiz:\d+$"))
    app.add_handler(CallbackQueryHandler(news_category_callback, pattern=r"^news:(turkiye|trson|siyaset|tbmm|son|gundem|dunya|ekonomi|teknoloji|bbc|oyun|brawlstars|gta6)$"))
    app.add_handler(CallbackQueryHandler(article_callback, pattern=r"^article:[a-f0-9]{16}$"))
    app.add_handler(CallbackQueryHandler(topic_callback, pattern=r"^topic:(gta6|brawlstars|siyaset|teknoloji|dunya)$"))
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
