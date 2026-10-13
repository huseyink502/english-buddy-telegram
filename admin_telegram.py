"""Private Telegram admin, clear privacy notices and controllable chat logging."""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from functools import lru_cache

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from admin_store import AdminStore, send_announcement

LOG = logging.getLogger("karamaz-admin")

NEW_USER_NOTICE = (
    "🔐 Karamaz Akademi — Sohbet gizliliği\n\n"
    "Güvenlik ve hizmet kalitesi için bu bildirimin ardından botla yaptığın "
    "METİN konuşmaları ve yapay zekâ yanıtları, yalnızca bot sahibi tarafından "
    "görülebilecek şekilde en fazla 30 gün saklanır. Şu an gönderdiğin mesaj "
    "sohbet kaydına alınmadı.\n\n"
    "Bunu istemiyorsan sonraki mesajından ÖNCE /kayit_kapat yazabilirsin. "
    "/kayit_sil ile kayıtları silebilirsin; kayıt kapalı kalır. "
    "Ayrıntılar: /gizlilik. Yönetici duyuruları ayrıca /duyuru_ac ile açılır."
)

LEGACY_USER_NOTICE = (
    "🔐 Karamaz Akademi — Gizlilik güncellemesi\n\n"
    "Yeni sohbet kayıt politikamız açıkça bildiriliyor: bot sahibi güvenlik "
    "amacıyla en fazla 30 günlük metin mesajlarını görebilir. Ancak SENİN "
    "önceki kayıt tercihin değiştirilmedi. Kayıt önceden kapalıysa kapalı "
    "kalacak; açmak istersen /kayit_ac yaz.\n\n"
    "Dilediğin an /kayit_kapat veya /kayit_sil kullanabilirsin. "
    "Ayrıntılar: /gizlilik."
)


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
    """First disclose content logging, then record only subsequent messages."""
    user = update.effective_user
    chat = update.effective_chat
    if user is None or chat is None or chat.type != "private" or user.is_bot:
        return
    try:
        db = await asyncio.to_thread(store)
        if db is None:
            return
        await asyncio.to_thread(db.seen, user.id, user.username, user.first_name)
        # Callback queries can come from a previous bot message. Do not send
        # privacy announcements there or start recording without new user text.
        incoming = update.message
        if incoming is None:
            return

        version = await asyncio.to_thread(db.notice_version, user.id)
        if version != 1:
            notice = NEW_USER_NOTICE if version == 0 else LEGACY_USER_NOTICE
            # If Telegram delivery fails, leave recording disabled. The next
            # user update will trigger a new disclosure attempt.
            await incoming.reply_text(notice)
            await asyncio.to_thread(db.mark_notice, user.id)
            context.user_data["admin_skip_reply_message_id"] = incoming.message_id
            # The message that triggered disclosure must not be captured.
            return

        # Never log commands: these may contain tokens, other secrets or IDs.
        if incoming.text and not incoming.text.lstrip().startswith("/"):
            await asyncio.to_thread(db.store_text, user.id, "user", incoming.text)
    except Exception:
        LOG.warning("Optional admin telemetry unavailable")


async def note_reply(update, answer: str, context=None) -> None:
    """Persist AI text only when disclosure preceded the user's question."""
    user = update.effective_user
    if not user:
        return
    if context is not None:
        first_id = context.user_data.pop("admin_skip_reply_message_id", None)
        if first_id is not None and update.message and first_id == update.message.message_id:
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
            "Yeni kullanıcılara ilk iletişimde kayıt politikası bildirilir. "
            "Bildirimden SONRAKİ metin mesajları ve AI yanıtları en fazla 30 gün "
            "saklanabilir ve yalnızca bot sahibi bunları inceleyebilir. "
            "Bildirimden önceki mesajlar kaydedilmez; geçmiş Telegram mesajları "
            "geriye dönük alınamaz.\n"
            "Eski kullanıcıların önceki kayıt tercihleri korunur. "
            "/kayit_kapat ile kaydı durdurup önceki kayıtları silebilir, "
            "/kayit_sil ile geçmişi silebilirsin. İstersen /kayit_ac ile "
            "kaydı tekrar etkinleştirebilirsin.\n"
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
            f"🗨️ Sohbet kaydı açık: {stats['chat_optins']}\n"
            f"📣 Duyuru izinli: {stats['announcement_optins']}\n"
            f"📝 Son 30 gün kayıt: {stats['messages_30d']}\n\n"
            "Komutlar:\n"
            "/admin_kullanicilar — son kullanıcılar\n"
            "/admin_sohbet ID — kayıtlı sohbet geçmişi\n"
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
            await update.message.reply_text("Bu kullanıcı için sohbet kaydı kapalı.")
            return
        messages = await asyncio.to_thread(db.conversations, target_id, 8)
        output = "\n\n".join(
            ("👤 " if x["direction"] == "user" else "🤖 ") + x["body"][:600]
            for x in messages
        ) or "Henüz kayıtlı sohbet mesajı bulunmuyor."
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
