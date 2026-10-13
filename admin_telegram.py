"""Private Telegram owner commands and explicitly consented message logging."""
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


def is_owner(update) -> bool:
    uid = owner_id()
    return (
        uid > 0 and update.effective_user is not None
        and update.effective_user.id == uid
        and update.effective_chat is not None
        and update.effective_chat.type == "private"
    )


PRIVACY_NOTICE_VERSION = 1


def privacy_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Kayıtlı kullan (30 gün)", callback_data="privacy:accept")],
        [InlineKeyboardButton("🔒 Kayıtsız devam et", callback_data="privacy:decline")],
    ])


def privacy_notice() -> str:
    return (
        "🔐 Karamaz Akademi — Gizlilik tercihi\\n\\n"
        "Bot, kullanıcı yönetimi ve güvenlik için Telegram ID, kullanıcı adı "
        "ve son etkinlik tarihini saklar.\\n\\n"
        "✅ Kayıtlı kullan: Bundan sonraki metin mesajların ve AI cevapların "
        "yalnızca bot sahibinin erişebildiği admin panelinde görüntülenebilir "
        "ve en fazla 30 gün saklanır.\\n\\n"
        "🔒 Kayıtsız devam et: Botu normal kullanabilirsin; konuşma metinlerin "
        "yönetici panelinde saklanmaz.\\n\\n"
        "Tercihini /gizlilik bölümünden değiştirebilir, /kayit_sil ile daha "
        "önce kaydedilmiş metinlerini silebilirsin. AI'ya gönderdiğin mesajlar "
        "yanıt üretmek için Gemini veya Groq sağlayıcılarına iletilebilir. "
        "Günlük haber bildirimleri ve yönetici duyuruları ayrı izinler gerektirir."
    )


async def privacy_gate(update, context):
    """Show privacy choice once before any text transcript or normal bot action.

    Both choices allow full ordinary functionality. Existing users see the new
    notice once. Unacknowledged text is not logged, not even in the pending update.
    """
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None or chat.type != "private" or user.is_bot:
        return
    callback = update.callback_query
    data = callback.data if callback else ""
    if isinstance(data, str) and data in ("privacy:accept", "privacy:decline"):
        try:
            db = await asyncio.to_thread(store)
            if db is None:
                await callback.answer("Veritabanı şu an kullanılamıyor.", show_alert=True)
                raise ApplicationHandlerStop
            await asyncio.to_thread(db.seen, user.id, user.username, user.first_name)
            enabled = data == "privacy:accept"
            await asyncio.to_thread(db.acknowledge_privacy, user.id, enabled)
        except ApplicationHandlerStop:
            raise
        except Exception:
            LOG.warning("Privacy acknowledgement could not be saved")
            await callback.answer("Kaydedilemedi, sonra tekrar dene.", show_alert=True)
            raise ApplicationHandlerStop
        await callback.answer("Tercihin kaydedildi.")
        await callback.edit_message_text(
            ("✅ Kayıtlı kullanım etkin. " if enabled else "🔒 Kayıtsız kullanım etkin. ")
            + "Botu kullanmaya başlamak için /start yaz. "
            "Gizlilik tercihin /gizlilik ile değiştirilebilir."
        )
        raise ApplicationHandlerStop

    text = update.message.text.strip() if update.message and update.message.text else ""
    command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    free_commands = {"/gizlilik", "/kayit_sil", "/kayit_kapat",
                     "/duyuru_kapat", "/whoami"}
    if command in free_commands or (command.startswith("/admin") and is_owner(update)):
        return
    try:
        db = await asyncio.to_thread(store)
        if db is None:
            raise RuntimeError("Database unavailable")
        await asyncio.to_thread(db.seen, user.id, user.username, user.first_name)
        version, _ = await asyncio.to_thread(db.privacy_status, user.id)
        if version >= PRIVACY_NOTICE_VERSION:
            return
    except Exception:
        LOG.warning("Privacy gate database unavailable")
        if callback:
            await callback.answer("Gizlilik ayarları yüklenemedi.", show_alert=True)
        else:
            await update.effective_message.reply_text(
                "⚠️ Güvenli oturum başlatılamadı; biraz sonra tekrar dene."
            )
        raise ApplicationHandlerStop

    if callback:
        await callback.answer("Önce gizlilik tercihini seç.", show_alert=True)
    await update.effective_message.reply_text(privacy_notice(), reply_markup=privacy_keyboard())
    raise ApplicationHandlerStop


async def observe(update, context) -> None:
    """Minimal per-user roster; save messages only if user opted in."""
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None or chat.type != "private" or user.is_bot:
        return
    try:
        db = await asyncio.to_thread(store)
        if db is None:
            return
        await asyncio.to_thread(db.seen, user.id, user.username, user.first_name)
        incoming = update.message
        # Slash commands contain potential secrets: never log them.
        if incoming and incoming.text and not incoming.text.lstrip().startswith("/"):
            await asyncio.to_thread(db.store_text, user.id, "user", incoming.text)
    except Exception:
        LOG.warning("Optional admin telemetry unavailable")


async def note_reply(update, answer: str) -> None:
    """Log AI response only for users who explicitly opted in."""
    user = update.effective_user
    if not user:
        return
    try:
        db = await asyncio.to_thread(store)
        if db is not None:
            await asyncio.to_thread(db.store_text, user.id, "bot", answer)
    except Exception:
        LOG.warning("Optional opted-in chat transcript storage unavailable")


async def privacy_commands(update, context) -> None:
    if update.effective_chat.type != "private":
        return
    command = update.message.text.split()[0].split("@")[0].lower()
    user_id = update.effective_user.id
    if command == "/gizlilik":
        await update.message.reply_text(privacy_notice(), reply_markup=privacy_keyboard())
        return
    db = await asyncio.to_thread(store)
    if db is None:
        await update.message.reply_text("Neon bağlantısı olmadan bu özellik kullanılamıyor.")
        return
    await asyncio.to_thread(
        db.seen, user_id, update.effective_user.username, update.effective_user.first_name
    )
    if command == "/kayit_ac":
        # Legacy command remains compatible, but the public menu offers buttons.
        await asyncio.to_thread(db.acknowledge_privacy, user_id, True)
        await update.message.reply_text(
            "✅ Kayıtlı kullanım etkin. Tercihini /gizlilik üzerinden değiştirebilirsin."
        )
    elif command == "/kayit_kapat":
        # Protect prior sensitive messages as well when permission is revoked.
        await asyncio.to_thread(db.delete_transcripts, user_id)
        await update.message.reply_text("🔒 Sohbet kaydı kapatıldı ve eski kayıtların silindi.")
    elif command == "/kayit_sil":
        await asyncio.to_thread(db.delete_transcripts, user_id)
        await update.message.reply_text("🗑️ Sohbet kayıtların silindi ve kayıt izni kapatıldı.")
    elif command in ("/duyuru_ac", "/duyuru_kapat"):
        enabled = command == "/duyuru_ac"
        await asyncio.to_thread(db.set_consent, user_id, "announcements_enabled", enabled)
        await update.message.reply_text(
            "📣 Yönetici duyurularını almaya izin verdin." if enabled else
            "🔕 Yönetici duyuruları kapatıldı."
        )


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
            f"🗨️ Sohbet kaydı izinli: {stats['chat_optins']}\n"
            f"📣 Duyuru izinli: {stats['announcement_optins']}\n"
            f"📝 Son 30 gün kayıt: {stats['messages_30d']}\n\n"
            "Komutlar:\n"
            "/admin_kullanicilar — son kullanıcılar\n"
            "/admin_sohbet ID — izinli sohbet geçmişi\n"
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
            await update.message.reply_text("Bu kullanıcı sohbet kaydına izin vermemiş.")
            return
        messages = await asyncio.to_thread(db.conversations, target_id, 8)
        output = "\n\n".join(
            ("👤 " if x["direction"] == "user" else "🤖 ") + x["body"][:600]
            for x in messages
        ) or "Henüz izinli sohbet mesajı bulunmuyor."
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
