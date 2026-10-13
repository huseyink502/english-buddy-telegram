"""Private Telegram owner commands and transparent, user-controlled message logging."""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from functools import lru_cache

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop

from admin_store import AdminStore, send_announcement

LOG = logging.getLogger("karamaz-admin")


@lru_cache(maxsize=1)
def store() -> AdminStore | None:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return None
    db = AdminStore(url)
    db.setup()
    return db


def owner_id() -> int:
    try:
        return int(os.getenv("ADMIN_USER_ID", "0") or 0)
    except ValueError:
        return 0


def bot_access_allowed(user_id: int) -> bool:
    """Do not process or store private metadata for excluded users."""
    try:
        allowed_id = int(os.getenv("ALLOWED_USER_ID", "0") or "0")
    except ValueError:
        return False
    return not allowed_id or user_id == allowed_id


def is_owner(update) -> bool:
    uid = owner_id()
    return (
        uid > 0 and update.effective_user is not None
        and update.effective_user.id == uid
        and update.effective_chat is not None
        and update.effective_chat.type == "private"
    )


NOTICE_COMMON = (
    "🔐 Karamaz Akademi · Gizlilik bildirimi\n\n"
    "Bot, güvenlik ve destek için Telegram ID'ni, kullanıcı adını ve son etkinlik "
    "tarihini saklar. Botla bundan sonra yapacağın metin sohbetleri ve AI yanıtları "
    "en fazla 30 gün saklanabilir ve yalnızca bot sahibi tarafından incelenebilir. "
    "Ses dosyaları ve API anahtarları bu kayıt sistemine alınmaz. "
    "Geçmiş mesajlar geriye dönük alınamaz.\n\n"
    "Kayıt durumunu görüp kaydı durdurmak veya kayıtlarını silmek için "
    "/gizlilik yazabilirsin. Duyurular ve günlük haber özetleri ayrı izin gerektirir. "
    "Özel şifre veya hassas bilgi paylaşma."
)


async def observe(update, context) -> None:
    """Explain default logging BEFORE new users' chat text can be persisted."""
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None or chat.type != "private" or user.is_bot:
        return
    if not bot_access_allowed(user.id):
        return
    try:
        db = await asyncio.to_thread(store)
        if db is None:
            return
        await asyncio.to_thread(db.seen, user.id, user.username, user.first_name)
        needs_notice, is_legacy, was_enabled = await asyncio.to_thread(
            db.notice_status, user.id
        )
        if needs_notice:
            message = update.effective_message
            if message is None:
                return
            additional = (
                "\n\nDaha önceki gizlilik tercihin korunuyor: kayıt şu anda kapalı. "
                "/gizlilik içinden istersen açabilirsin."
                if is_legacy and not was_enabled else ""
            )
            # Nothing is recorded until Telegram has accepted this notice.
            await message.reply_text(NOTICE_COMMON + additional)
            await asyncio.to_thread(db.mark_notified, user.id)
            # Never process the triggering message or archive an AI response
            # before the user has had a chance to read the notice.
            raise ApplicationHandlerStop
        incoming = update.message
        # Never archive slash commands, which may carry credentials or arguments.
        if incoming and incoming.text and not incoming.text.lstrip().startswith("/"):
            await asyncio.to_thread(db.store_text, user.id, "user", incoming.text)
    except ApplicationHandlerStop:
        raise
    except Exception:
        LOG.warning("Admin privacy notice or optional transcript storage unavailable")


async def note_reply(update, answer: str) -> None:
    """Save AI response only when logging is enabled for that user."""
    user = update.effective_user
    if not user:
        return
    try:
        db = await asyncio.to_thread(store)
        if db is not None:
            await asyncio.to_thread(db.store_text, user.id, "bot", answer)
    except Exception:
        LOG.warning("Optional opted-in chat transcript storage unavailable")


def privacy_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⏸️ Kaydı durdur ve geçmişi sil" if enabled else "▶️ Kaydı aç",
            callback_data="privacy:stop" if enabled else "privacy:resume",
        )],
        [InlineKeyboardButton("🗑️ Kayıtlarımı sil", callback_data="privacy:erase")],
    ])


async def privacy_summary(db: AdminStore, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    logging_enabled, announcements_enabled = await asyncio.to_thread(db.consent, user_id)
    body = (
        NOTICE_COMMON + "\n\n"
        + ("🟢 Metin sohbet kaydı: AÇIK" if logging_enabled
           else "🔴 Metin sohbet kaydı: KAPALI")
        + "\n"
        + ("📣 Yönetici duyuruları: AÇIK" if announcements_enabled
           else "🔕 Yönetici duyuruları: KAPALI")
        + "\n\nKayıt kontrolünü aşağıdaki butonlardan yapabilirsin. "
          "Botun İngilizce dersleri ve haber özellikleri kayıt kapalıyken de çalışır."
    )
    return body, privacy_keyboard(logging_enabled)


async def privacy_commands(update, context) -> None:
    if update.effective_chat.type != "private":
        return
    if not bot_access_allowed(update.effective_user.id):
        await update.message.reply_text("Bu bot özel kullanım içindir.")
        return
    command = update.message.text.split()[0].split("@")[0].lower()
    user_id = update.effective_user.id
    db = await asyncio.to_thread(store)
    if db is None:
        await update.message.reply_text("Neon bağlantısı olmadan bu özellik kullanılamıyor.")
        return
    await asyncio.to_thread(
        db.seen, user_id, update.effective_user.username, update.effective_user.first_name
    )
    if command == "/gizlilik":
        body, keyboard = await privacy_summary(db, user_id)
        await update.message.reply_text(body, reply_markup=keyboard)
    elif command == "/kayit_ac":
        # Compatibility alias: intentionally omitted from visible / menu.
        await asyncio.to_thread(db.set_consent, user_id, "transcript_enabled", True)
        await update.message.reply_text(
            "✅ Metin sohbet kaydı açıldı. Durdurmak veya silmek için /gizlilik yaz."
        )
    elif command in ("/kayit_kapat", "/kayit_sil"):
        await asyncio.to_thread(db.delete_transcripts, user_id)
        await update.message.reply_text(
            "🔒 Metin sohbet kaydı durduruldu ve mevcut kayıtların silindi."
        )
    elif command in ("/duyuru_ac", "/duyuru_kapat"):
        enabled = command == "/duyuru_ac"
        await asyncio.to_thread(db.set_consent, user_id, "announcements_enabled", enabled)
        await update.message.reply_text(
            "📣 Yönetici duyurularını almaya izin verdin." if enabled else
            "🔕 Yönetici duyuruları kapatıldı."
        )


async def privacy_callback(update, context) -> None:
    """Changes only the current user's privacy preference."""
    query = update.callback_query
    if update.effective_chat is None or update.effective_chat.type != "private":
        await query.answer("Yalnızca özel sohbette.", show_alert=True)
        return
    if not bot_access_allowed(update.effective_user.id):
        await query.answer("Erişim yok.", show_alert=True)
        return
    db = await asyncio.to_thread(store)
    if db is None:
        await query.answer("Şu anda kullanılamıyor.", show_alert=True)
        return
    user_id = update.effective_user.id
    action = (query.data or "").split(":")[-1]
    if action == "resume":
        await asyncio.to_thread(db.set_consent, user_id, "transcript_enabled", True)
    elif action in ("stop", "erase"):
        await asyncio.to_thread(db.delete_transcripts, user_id)
    else:
        await query.answer("Geçersiz işlem.", show_alert=True)
        return
    await query.answer("Gizlilik tercihin güncellendi.")
    body, keyboard = await privacy_summary(db, user_id)
    await query.edit_message_text(body, reply_markup=keyboard)


async def owner_commands(update, context) -> None:
    if not is_owner(update):
        await update.message.reply_text("⛔ Bu komut yalnızca bot yöneticisi içindir.")
        return
    db = await asyncio.to_thread(store)
    if db is None:
        await update.message.reply_text("Neon DATABASE_URL ayarlı değil.")
        return
    command = update.message.text.split()[0].split("@")[0].lower()
    if command == "/admin":
        stats = await asyncio.to_thread(db.stats)
        url = os.getenv("WEBHOOK_BASE_URL", "").strip().rstrip("/")
        if not url:
            hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
            url = "https://" + hostname if hostname else ""
        await update.message.reply_text(
            "🛡️ Karamaz Akademi — Admin\n\n"
            f"👥 Kullanıcı: {stats['users']}\n"
            f"🟢 Son 7 gün aktif: {stats['active_7d']}\n"
            f"🗨️ Sohbet kaydı açık: {stats['chat_optins']}\n"
            f"📣 Duyuru izinli: {stats['announcement_optins']}\n"
            f"📝 Son 30 gün kayıt: {stats['messages_30d']}\n\n"
            "Komutlar:\n"
            "/admin_kullanicilar — son kullanıcılar\n"
            "/admin_sohbet ID — mevcut sohbet kayıtları\n"
            "/admin_duyuru Mesaj — izin veren herkese duyuru\n"
            + (f"🌐 Web paneli: {url}/admin" if url else "")
        )
    elif command == "/admin_kullanicilar":
        rows = await asyncio.to_thread(db.users, 15, 0)
        if not rows:
            await update.message.reply_text("Henüz kaydedilmiş kullanıcı yok.")
            return
        lines = [
            f"• {x['user_id']} — @{x['username'] or '—'}"
            f" {'🗨️' if x['transcript_enabled'] else ''}"
            f" {'📣' if x['announcements_enabled'] else ''}"
            for x in rows
        ]
        await update.message.reply_text("👥 Son kullanıcılar\n" + "\n".join(lines))
    elif command == "/admin_sohbet":
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_text("Kullanım: /admin_sohbet 123456789")
            return
        target_id = int(context.args[0])
        profile = await asyncio.to_thread(db.user, target_id)
        if not profile:
            await update.message.reply_text("Kullanıcı bulunamadı.")
            return
        if not profile["transcript_enabled"]:
            await update.message.reply_text("Bu kullanıcı için sohbet kaydı şu anda kapalı.")
            return
        messages = await asyncio.to_thread(db.conversations, target_id, 8)
        output = "\n\n".join(
            ("👤 " if x["direction"] == "user" else "🤖 ") + x["body"][:600]
            for x in messages
        ) or "Henüz kaydedilmiş sohbet mesajı bulunmuyor."
        await update.message.reply_text(
            f"🔐 Kullanıcı {target_id} — son kayıtlar\n\n" + output[:3700]
        )
    elif command == "/admin_duyuru":
        body = " ".join(context.args).strip()
        if not body or len(body) > 1500:
            await update.message.reply_text(
                "Kullanım: /admin_duyuru Merhaba, yeni özellik yayında! (en fazla 1500 karakter)"
            )
            return
        recipients = await asyncio.to_thread(db.recipients)
        if not recipients:
            await update.message.reply_text(
                "📭 Duyuru izni veren kullanıcı bulunamadı. "
                "Kullanıcılar /duyuru_ac yazarak kayıt olabilir."
            )
            return
        token = secrets.token_hex(6)
        context.user_data["admin_draft"] = {
            "token": token, "message": body, "created": time.monotonic(),
        }
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Gönderimi onayla", callback_data=f"admin:confirm:{token}"),
            InlineKeyboardButton("❌ Vazgeç", callback_data=f"admin:cancel:{token}"),
        ]])
        await update.message.reply_text(
            f"📣 Duyuru önizlemesi ({len(recipients)} izinli alıcı):\n\n"
            f"{body}\n\nGöndermek için 5 dakika içinde onayla.",
            reply_markup=keyboard,
        )


async def admin_announcement_callback(update, context):
    """Prevent accidental or repeated mass-messaging from admin commands."""
    query = update.callback_query
    if not is_owner(update):
        await query.answer("Erişim yok.", show_alert=True)
        return
    parts = (query.data or "").split(":")
    if len(parts) != 3:
        await query.answer("Geçersiz işlem.", show_alert=True)
        return
    _, action, token = parts
    draft = context.user_data.get("admin_draft")
    if not draft or draft["token"] != token or time.monotonic() - draft["created"] > 300:
        await query.answer("Onay süresi doldu. Duyuruyu yeniden hazırla.", show_alert=True)
        return
    context.user_data.pop("admin_draft", None)
    await query.answer()
    if action == "cancel":
        await query.edit_message_text("❌ Duyuru iptal edildi; hiçbir mesaj gönderilmedi.")
        return
    if action != "confirm":
        return
    await query.edit_message_text("📣 İzin veren kullanıcılara gönderiliyor...")
    try:
        db = await asyncio.to_thread(store)
        if db is None:
            raise RuntimeError("Missing Neon connection")
        result = await send_announcement(context.bot, db, draft["message"])
        await query.edit_message_text(
            f"✅ Gönderim bitti. İzinli alıcı: {result['recipients']}, "
            f"başarılı: {result['sent']}, başarısız: {result['failed']}."
        )
    except Exception:
        LOG.exception("Admin announcement failed")
        await query.edit_message_text(
            "⚠️ Gönderim tamamlanamadı. Bazı alıcılara ulaşmış olabilir; "
            "yeniden denemeden önce sonuçları kontrol et."
        )
