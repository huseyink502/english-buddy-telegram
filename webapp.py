"""ASGI HTTP webhook entrypoint for Render's free web-service tier.

The webhook is re-registered each time the service wakes from sleep. Incoming
updates are acknowledged quickly and placed on python-telegram-bot's queue.
"""
from contextlib import asynccontextmanager
import asyncio
import hashlib
import hmac
import logging
import os
import psycopg

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from telegram import Update

import bot as english_bot
from admin_web import router as admin_router
from admin_telegram import store as admin_storage
from admin_delivery import delivery_loop
from admin_maintenance import maintenance_loop

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
    tasks = []
    try:
        await english_bot.register_commands(application)
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
        if os.getenv('DATABASE_URL'):
            try:
                db = await asyncio.to_thread(admin_storage)
                tasks = [asyncio.create_task(delivery_loop(application.bot,db)),
                         asyncio.create_task(maintenance_loop(db))]
            except Exception:
                LOG.warning('Admin setup unavailable; webhook remains available')
        LOG.info("Telegram webhook registered on Render")
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        # Keep the webhook configured: Telegram will redeliver after cold starts.
        await application.stop()
        await application.shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(admin_router)


@app.middleware('http')
async def admin_response_security(request: Request, call_next):
    try:
        response = await call_next(request)
    except psycopg.Error:
        if not request.url.path.startswith('/admin'):
            raise
        # Database exception strings can contain connection credentials.
        LOG.warning('Admin database temporarily unavailable')
        from fastapi.responses import JSONResponse
        response = JSONResponse({'detail':'Yönetim veritabanı geçici olarak kullanılamıyor'},503)
    if request.url.path.startswith('/admin'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
    return response


@app.get("/", response_class=HTMLResponse)
async def home():
    """Simple public landing page, not a public entry to protected data."""
    response = HTMLResponse("""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Karamaz Akademi | Bot ve Yönetim</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;
background:#0b1220;color:#edf2fb;font:16px system-ui,-apple-system,sans-serif;
padding:24px}
main{width:min(100%,560px);padding:34px;border:1px solid #2b405a;
border-radius:18px;background:#152136;box-shadow:0 12px 34px #060b1533}
h1{margin:0 0 8px;font-size:1.75rem}
p{color:#b5c5dd;line-height:1.65}
a.action{display:inline-block;padding:12px 20px;border-radius:10px;
background:#397ff2;color:white;text-decoration:none;font-weight:700;
margin:12px 0 4px}
small{color:#a8b9d4;display:block;margin-top:24px}
</style></head><body><main>
<h1>🎓 Karamaz Akademi</h1>
<p>İngilizce çalışmaları, yapay zekâ ve haber takibi için Telegram botu.</p>
<p>Bot yöneticisiysen özel yönetim paneline aşağıdan ulaşabilirsin.
Panelin giriş bilgileri yalnızca Render üzerinden tanımlanır.</p>
<a class="action" href="/admin">🛡️ Yönetici panelini aç →</a>
<small>Yönetim paneline giriş için yetkili hesap ve parola gerekir.
İlk kullanımda gizlilik bildirimi sunulur; kayıt tercihleri /gizlilik ile yönetilir.</small>
</main></body></html>""")
    response.headers.update({
        "Cache-Control": "public, max-age=60",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy":
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'",
    })
    return response


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
