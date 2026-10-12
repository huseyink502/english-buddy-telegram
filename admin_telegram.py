"""Private Telegram owner commands and explicitly consented message logging."""
from __future__ import annotations

import asyncio
import logging
import os
from functools import lru_cache

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
        await update.message.reply_text(
            "🔐 Karamaz Akademi Gizlilik\n\n"
            "Bot, güvenlik ve kullanıcı yönetimi için Telegram ID, kullanıcı adı "
            "ve son etkinlik tarihini saklar. Bot sahibi bu temel listeyi görür.\n"
            "Sohbet metinlerin varsayılan olarak KAYDEDİLMEZ. /kayit_ac "
            "komutuyla açıkça izin verirsen daha sonraki metin mesajların ve "
            "AI yanıtları en fazla 30 gün saklanır ve yalnızca bot sahibi "
            "tarafından incelenebilir. Önceki mesajlar geriye dönük alınamaz.\n"
            "/kayit_kapat kayıt almayı durdurur, /kayit_sil mevcut kayıtları siler.\n"
            "Duyurular ayrıca /duyuru_ac ile açılır, /duyuru_kapat ile kapatılır.\n"
            "Haber özetleri /ozet_ac iznine bağlıdır. Üç izin birbirinden ayrıdır."
        )
        return
    db = await asyncio.to_thread(store)
    if db is None:
        await update.message.reply_text("Neon bağlantısı olmadan bu özellik kullanılamıyor.")
        return
    await asyncio.to_thread(
        db.seen, user_id, update.effective_user.username, update.effective_user.first_name
    )
    if command == "/kayit_ac":
        await asyncio.to_thread(db.set_consent, user_id, "transcript_enabled", True)
        await update.message.reply_text(
            "✅ Bu andan itibaren metin sohbetlerinin en fazla 30 gün "
            "saklanmasına ve bot sahibi tarafından incelenmesine izin verdin. "
            "/kayit_kapat ile durdurabilir, /kayit_sil ile silebilirsin."
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
        await update.message.reply_text("📣 İzinli alıcılara duyuru gönderiliyor...")
        result = await send_announcement(context.bot, db, body)
        await update.message.reply_text(
            f"✅ Gönderim bitti. İzinli: {result['recipients']}, "
            f"başarılı: {result['sent']}, başarısız: {result['failed']}."
        )
