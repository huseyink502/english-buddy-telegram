"""Password-protected, mobile-friendly owner-only admin pages.

Disabled until ADMIN_USER_ID and a strong ADMIN_WEB_PASSWORD are configured.
No secrets in links, cookies are signed, HttpOnly, Secure, and SameSite=Strict.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import os
import secrets
import time
from functools import lru_cache
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from admin_store import AdminStore, send_announcement

router = APIRouter()
FAILURES = {}
SESSION_LIFETIME = 8 * 3600
COOKIE = "karamaz_admin"
CSS = """
*{box-sizing:border-box}body{background:#0b1220;color:#edf2fb;
font-family:system-ui,-apple-system,sans-serif;margin:0;padding:22px}
main{max-width:1020px;margin:24px auto}h1{font-size:1.65rem}
h2{font-size:1.2rem;margin-top:28px}p,small{color:#a8b9d4}
section,.box{background:#152136;border:1px solid #2b405a;
border-radius:16px;padding:20px;margin:16px 0}
a{color:#7bd4fa}input,textarea{display:block;width:100%;
padding:12px;background:#101a2a;border:1px solid #52647f;
color:white;border-radius:8px;margin:9px 0;font:inherit}
button{background:#397ff2;border:0;color:white;border-radius:8px;
padding:12px 18px;font-weight:700;cursor:pointer}
table{width:100%;border-collapse:collapse}td,th{text-align:left;
padding:11px 8px;border-bottom:1px solid #30435e;word-break:break-word}
.muted{color:#b5c5dd}.good{color:#80e6ad}.warn{color:#ffd18a}
.stats{display:flex;flex-wrap:wrap;gap:12px}.stat{flex:1;min-width:145px}
.stat b{font-size:1.65rem}form.inline{display:inline-block}
footer{margin-top:25px;color:#a8b9d4}
"""


def config_ok() -> bool:
    # Deliberately off until the service owner explicitly enables the panel.
    return os.getenv("ADMIN_PANEL_ENABLED", "").strip().lower() in ("1", "true", "yes") and bool(os.getenv("DATABASE_URL")) and (
        os.getenv("ADMIN_USER_ID", "").strip().isdigit()
        and int(os.getenv("ADMIN_USER_ID", "0")) > 0
        and len(os.getenv("ADMIN_WEB_PASSWORD", "")) >= 20
    )


@lru_cache(maxsize=1)
def storage() -> AdminStore:
    obj = AdminStore(os.environ["DATABASE_URL"])
    obj.setup()
    return obj


def secret_bytes() -> bytes:
    return hashlib.sha256(os.environ["ADMIN_WEB_PASSWORD"].encode("utf-8")).digest()


def signature(value: str) -> str:
    return hmac.new(secret_bytes(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def signed_session() -> str:
    base = f"{int(time.time())}:{secrets.token_hex(20)}"
    return base + ":" + signature(base)


def is_admin(request: Request) -> bool:
    if not config_ok():
        return False
    value = request.cookies.get(COOKIE, "")
    try:
        stamp, nonce, sig = value.split(":")
        age = time.time() - int(stamp)
        if not (0 <= age < SESSION_LIFETIME) or len(nonce) != 40:
            return False
        return hmac.compare_digest(sig, signature(stamp + ":" + nonce))
    except (ValueError, TypeError):
        return False


def csrf_token(request: Request) -> str:
    return signature("csrf:" + request.cookies[COOKIE])


def guard_csrf(request: Request, value: str) -> None:
    if not is_admin(request):
        raise HTTPException(403, "Forbidden")
    origin = request.headers.get("origin")
    host = request.headers.get("host", "")
    # SameSite already protects against cross-origin cookies; also check Origin.
    if origin:
        parsed = urlparse(origin)
        if parsed.netloc != host or parsed.scheme not in ("https", "http"):
            raise HTTPException(403, "Invalid request origin")
    if not hmac.compare_digest(csrf_token(request), value):
        raise HTTPException(403, "Invalid form token")


async def values(request: Request) -> dict:
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Expected form data")
    data = await request.body()
    if len(data) > 6000:
        raise HTTPException(413, "Form too large")
    try:
        return {k: v[0] for k, v in parse_qs(
            data.decode("utf-8"), keep_blank_values=True, max_num_fields=10
        ).items()}
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(400, "Invalid form")


def page(title: str, body: str) -> HTMLResponse:
    safe_title = html.escape(title)
    result = HTMLResponse(
        f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{safe_title} | Karamaz Akademi</title><style>{CSS}</style>'
        f'</head><body><main><h1>🛡️ Karamaz Akademi · Yönetici Paneli</h1>'
        f'{body}<footer>Yetkili yönetici alanı · Kullanıcı sohbetleri yalnızca '
        f'ilk kullanımda bildirildikten sonra en fazla 30 gün saklanır; kullanıcı kaydı kapatıp silebilir.</footer></main></body></html>'
    )
    result.headers.update({
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy":
            "default-src 'none'; style-src 'unsafe-inline'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    })
    return result


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def login_page(message="") -> HTMLResponse:
    return page("Giriş", (
        '<section><h2>Güvenli giriş</h2><p>Yalnızca bot sahibi içindir.</p>'
        + ('<p class="warn">' + esc(message) + '</p>' if message else '')
        + '<form action="/admin/login" method="post">'
          '<label>Yönetici parolası</label>'
          '<input type="password" name="password" autocomplete="current-password" '
          'required minlength="20"><button type="submit">Giriş yap</button>'
          '</form></section>'
    ))


def protected(request: Request):
    if not config_ok():
        return page("Kurulum gerekli", (
            "<section><h2>Panel henüz etkin değil</h2>"
            "<p>Render Environment bölümüne ADMIN_USER_ID (Telegram sahibi ID), "
            "en az 20 karakterlik ADMIN_WEB_PASSWORD ve "
            "ADMIN_PANEL_ENABLED=true değişkenlerini ekleyin.</p></section>"
        ))
    if not is_admin(request):
        return login_page()
    return None


@router.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request):
    denied = protected(request)
    if denied:
        return denied
    import asyncio
    db = await asyncio.to_thread(storage)
    stats = await asyncio.to_thread(db.stats)
    people = await asyncio.to_thread(db.users, 25, 0)
    token = esc(csrf_token(request))
    cards = "".join(
        f'<div class="box stat"><b>{stats[key]}</b><br>{title}</div>'
        for key, title in [
            ("users", "Toplam kullanıcı"), ("active_7d", "Son 7 gün aktif"),
            ("chat_optins", "Sohbet kaydı açık"),
            ("announcement_optins", "Duyuru izni"),
            ("messages_30d", "30 günlük kayıt"),
        ]
    )
    rows = "".join(
        f'<tr><td><a href="/admin/user/{p["user_id"]}">{p["user_id"]}</a></td>'
        f'<td>{esc(p["username"] or p["first_name"] or "—")}</td>'
        f'<td>{esc(p["last_seen_at"].strftime("%d.%m.%Y %H:%M"))}</td>'
        f'<td>{"✅" if p["transcript_enabled"] else "—"}</td>'
        f'<td>{"✅" if p["announcements_enabled"] else "—"}</td></tr>'
        for p in people
    )
    return page("Panel", (
        '<p class="muted">Yeni kullanıcılara gizlilik bildirimi gönderildikten sonra '
        'sohbet kaydı açılır. Eski kullanıcıların tercihleri korunur. '
        'Kayıt her zaman /kayit_kapat ile kapatılabilir; '
        'duyurular ayrıca /duyuru_ac izni gerektirir.</p>'
        '<div class="stats">' + cards + '</div>'
        '<section><h2>Kullanıcılar</h2><p>İlk 25 kullanıcı. '
        '<a href="/admin/users?offset=0">Tüm kullanıcılar</a></p>'
        '<table><thead><tr><th>Telegram ID</th><th>Ad</th><th>Son etkinlik</th>'
        '<th>Sohbet kaydı</th><th>Duyuru izni</th></tr></thead><tbody>'
        + rows + '</tbody></table></section>'
        '<section><h2>📣 Duyuru gönder</h2>'
        '<p>Yalnızca /duyuru_ac ile bildirim izni veren kullanıcılara gider. '
        'Toplam alıcı: ' + str(stats["announcement_optins"]) + '</p>'
        '<form method="post" action="/admin/announcement">'
        '<input type="hidden" name="csrf" value="' + token + '">'
        '<textarea name="message" maxlength="1500" rows="5" required '
        'placeholder="Duyuru metnini yaz..."></textarea>'
        '<p><label><input type="checkbox" name="confirm" value="yes" required '
        'style="width:auto;display:inline-block"> İzinli alıcılara göndermeyi '
        'onaylıyorum.</label></p>'
        '<button type="submit">Duyuruyu gönder</button></form></section>'
        '<form method="post" action="/admin/logout">'
        '<input type="hidden" name="csrf" value="' + token + '">'
        '<button type="submit">Çıkış yap</button></form>'
    ))


@router.get("/admin/users", response_class=HTMLResponse)
async def list_users(request: Request, offset: int = 0):
    denied = protected(request)
    if denied:
        return denied
    import asyncio
    offset = max(0, min(offset, 100000))
    people = await asyncio.to_thread((await asyncio.to_thread(storage)).users, 50, offset)
    rows = "".join(
        f'<tr><td><a href="/admin/user/{p["user_id"]}">{p["user_id"]}</a></td>'
        f'<td>{esc(p["username"] or p["first_name"] or "")}</td>'
        f'<td>{esc(p["last_seen_at"])}</td></tr>'
        for p in people
    )
    return page("Kullanıcılar",
        '<section><h2>Kullanıcı listesi</h2><table><tr><th>ID</th><th>Ad</th>'
        '<th>Son aktivite</th></tr>' + rows + '</table>'
        f'<p><a href="/admin/users?offset={max(0,offset-50)}">Önceki</a> · '
        f'<a href="/admin/users?offset={offset+50}">Sonraki</a></p>'
        '<a href="/admin">Panele dön</a></section>')


@router.get("/admin/user/{user_id}", response_class=HTMLResponse)
async def user_messages(request: Request, user_id: int):
    denied = protected(request)
    if denied:
        return denied
    import asyncio
    db = await asyncio.to_thread(storage)
    person = await asyncio.to_thread(db.user, user_id)
    if person is None:
        raise HTTPException(404, "User not found")
    records = await asyncio.to_thread(db.conversations, user_id) if person["transcript_enabled"] else []
    body = '<section><h2>Kullanıcı ' + esc(user_id) + '</h2><p>Takma ad: ' + esc(person["username"]) + '</p>'
    if not person["transcript_enabled"]:
        body += '<p>Sohbet kaydı kapalı. Konuşma içerikleri görüntülenemez.</p>'
    else:
        body += '<p>Yalnızca son 30 günde kayıt açıkken saklanmış metinler:</p>'
        for msg in records:
            body += '<div class="box"><b>' + ("Kullanıcı" if msg["direction"] == "user" else "Bot") + '</b>'
            body += '<small> · ' + esc(msg["created_at"]) + '</small><p>'
            body += esc(msg["body"]).replace("\n", "<br>") + '</p></div>'
    return page("Sohbet", body + '<a href="/admin">Panele dön</a></section>')


@router.post("/admin/login")
async def login(request: Request):
    if not config_ok():
        raise HTTPException(503, "Admin panel not configured")
    form = await values(request)
    # Best-effort rate limit; restart resets failures. Recommend Render proxy WAF as well.
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    failures = [v for v in FAILURES.get(ip, []) if now - v < 900]
    if len(failures) >= 8:
        raise HTTPException(429, "Too many login attempts. Retry later.")
    supplied = form.get("password", "")
    if not hmac.compare_digest(supplied, os.environ["ADMIN_WEB_PASSWORD"]):
        FAILURES[ip] = failures + [now]
        return login_page("Parola geçersiz.")
    FAILURES.pop(ip, None)
    result = RedirectResponse("/admin", status_code=303)
    result.set_cookie(COOKIE, signed_session(), max_age=SESSION_LIFETIME,
                      secure=True, httponly=True, samesite="strict", path="/admin")
    result.headers["Cache-Control"] = "no-store"
    return result


@router.post("/admin/logout")
async def logout(request: Request):
    form = await values(request)
    guard_csrf(request, form.get("csrf", ""))
    response = RedirectResponse("/admin", status_code=303)
    response.delete_cookie(COOKIE, path="/admin")
    return response


@router.post("/admin/announcement", response_class=HTMLResponse)
async def announce(request: Request):
    form = await values(request)
    guard_csrf(request, form.get("csrf", ""))
    message = form.get("message", "").strip()
    if not message or len(message) > 1500:
        raise HTTPException(400, "Message must be 1-1500 characters")
    if form.get("confirm") != "yes":
        raise HTTPException(400, "Duyuru için gönderim onayı gerekli")
    db = await __import__("asyncio").to_thread(storage)
    bot = request.app.state.telegram_application.bot
    try:
        result = await send_announcement(bot, db, message)
    except ValueError:
        raise HTTPException(400, "Invalid announcement")
    return page("Duyuru sonucu",
        '<section><h2>Duyuru tamamlandı</h2>'
        f'<p>İzinli alıcı: {result["recipients"]}</p>'
        f'<p>Başarılı: {result["sent"]} · Başarısız: {result["failed"]}</p>'
        '<a href="/admin">Panele dön</a></section>')
