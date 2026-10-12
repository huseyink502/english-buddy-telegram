"""ASGI HTTP webhook entrypoint for Render's free web-service tier.

The webhook is re-registered each time the service wakes from sleep. Incoming
updates are acknowledged quickly and placed on python-telegram-bot's queue.
"""
from contextlib import asynccontextmanager
import hashlib
import hmac
import logging
import os

from fastapi import FastAPI, HTTPException, Request, Response
from telegram import Update

import bot as english_bot
from admin_web import router as admin_router

LOG = logging.getLogger(__name__)


def webhook_secret(bot_token: str) -> str:
    """Secret contains only characters Telegram allows; never log it."""
    return hashlib.sha256(bot_token.encode("utf-8")).hexdigest()


def external_url() -> str:
    """Render supplies the externally reachable HTTPS hostname."""
    configured = os.getenv("WEBHOOK_BASE_URL", "").strip().rstrip("/")
    if configured:
        if not configured.startswith("https://"):
            raise RuntimeError("WEBHOOK_BASE_URL must start with https://")
        return configured
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if not hostname:
        raise RuntimeError("Missing RENDER_EXTERNAL_HOSTNAME or WEBHOOK_BASE_URL")
    return f"https://{hostname}"


@asynccontextmanager
async def lifespan(server: FastAPI):
    application = english_bot.build_application()
    await application.initialize()
    await application.start()
    # Webhook mode does not execute the polling post_init hook; register
    # Telegram's "/" menu explicitly on every Render startup.
    await english_bot.register_commands(application)
    try:
        url = external_url() + "/telegram/webhook"
        await application.bot.set_webhook(
            url=url,
            secret_token=webhook_secret(application.bot.token),
            max_connections=1,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=False,
        )
        server.state.telegram_application = application
        server.state.webhook_secret = webhook_secret(application.bot.token)
        LOG.info("Telegram webhook registered on Render")
        yield
    finally:
        # Keep the webhook configured: Telegram will redeliver after cold starts.
        await application.stop()
        await application.shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "english-buddy"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    expected = request.app.state.webhook_secret
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=403, detail="Forbidden")
    if len(await request.body()) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Update too large")
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("not a JSON object")
        telegram_app = request.app.state.telegram_application
        update = Update.de_json(payload, telegram_app.bot)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid Telegram update")
    if update is None:
        raise HTTPException(status_code=400, detail="Invalid Telegram update")
    # Telegram receives 200 immediately, even when Gemini takes time to answer.
    await telegram_app.update_queue.put(update)
    return Response(status_code=200)
