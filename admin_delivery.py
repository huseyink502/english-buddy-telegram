"""One small durable sender shared by web and Telegram, no paid worker needed."""

import asyncio
import logging
from datetime import timedelta

from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter

LOG = logging.getLogger(__name__)


async def deliver_one(bot, store) -> bool:
    job = await asyncio.to_thread(store.claim_delivery)
    if job is None:
        return False
    uid, dispatch_id = job["user_id"], job["dispatch_id"]
    state, error, delay = "sent", None, 0
    try:
        if job["target_id"] is None:
            _, permission = await asyncio.to_thread(store.consent, uid)
            if not permission:
                await asyncio.to_thread(
                    store.finish_delivery, dispatch_id, uid, "skipped"
                )
                return True
            text = (
                "📣 Karamaz Akademi duyurusu\n\n"
                + job["content"]
                + "\n\nDuyuru iznini /gizlilik ile yönetebilirsin."
            )
        else:
            text = "🛡️ Karamaz Akademi yönetici destek mesajı\n\n" + job["content"]
        await bot.send_message(chat_id=uid, text=text, disable_web_page_preview=True)
    except RetryAfter as exc:
        delay = (
            exc.retry_after.total_seconds()
            if isinstance(exc.retry_after, timedelta)
            else float(exc.retry_after)
        )
        state, error = ("pending" if job["attempts"] < 4 else "failed"), "rate_limit"
    except (Forbidden, BadRequest):
        state, error = "failed", "unreachable"
    except NetworkError:
        # Timeout may happen AFTER Telegram accepted the message.
        state, error = "unknown", "network_uncertain"
    except Exception:
        state, error = "failed", "delivery_error"
        LOG.warning("Admin delivery failed; message contents and credentials omitted")
    await asyncio.to_thread(
        store.finish_delivery, dispatch_id, uid, state, error, max(delay, 0)
    )
    if error == "rate_limit":
        await asyncio.sleep(min(max(delay, 0), 60))
    return True


async def delivery_loop(bot, store):
    while True:
        try:
            worked = await deliver_one(bot, store)
        except Exception:
            LOG.warning("Admin dispatch storage temporarily unavailable")
            worked = False
        await asyncio.sleep(0.12 if worked else 20)
