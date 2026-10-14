"""Owner-only UI: password + Telegram OTP, revocable sessions and CSRF."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import os
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from admin_telegram import owner_id
from admin_telegram import store as storage

router = APIRouter()
COOKIE = "karamaz_admin"
LOGIN_COOKIE = "karamaz_login"
CHALLENGE_COOKIE = "karamaz_challenge"
SESSION_LIFETIME = 8 * 3600
ASSETS = Path(__file__).parent / "admin_assets"


def config_ok() -> bool:
    return (
        os.getenv("ADMIN_PANEL_ENABLED", "").lower() in ("1", "true", "yes")
        and bool(os.getenv("DATABASE_URL"))
        and owner_id() > 0
        and len(os.getenv("ADMIN_WEB_PASSWORD", "")) >= 20
    )


def signature(value: str) -> str:
    key = os.getenv("ADMIN_SESSION_SECRET") or os.environ["ADMIN_WEB_PASSWORD"]
    return hmac.new(
        key.encode(), ("karamaz-admin-v2:" + value).encode(), hashlib.sha256
    ).hexdigest()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def credential_hash() -> str:
    return signature(f"credential:{owner_id()}:{os.environ['ADMIN_WEB_PASSWORD']}")


def signed_session() -> str:
    return secrets.token_urlsafe(32)


async def is_admin(request: Request) -> bool:
    if not config_ok():
        return False
    token = request.cookies.get(COOKIE, "")
    if not (40 <= len(token) <= 64):
        return False
    try:
        db = await asyncio.to_thread(storage)
        return await asyncio.to_thread(
            db.session_valid, digest(token), owner_id(), credential_hash()
        )
    except Exception:
        return False


def csrf_token(request: Request) -> str:
    return signature("csrf:" + request.cookies.get(COOKIE, ""))


def guard_origin(request: Request):
    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.netloc != request.headers.get("host") or parsed.scheme != "https":
            raise HTTPException(403, "Invalid origin")


async def guard_csrf(request: Request, value: str):
    if not await is_admin(request):
        raise HTTPException(403, "Forbidden")
    guard_origin(request)
    if not equal(csrf_token(request), value):
        raise HTTPException(403, "Invalid form token")


async def values(request: Request) -> dict:
    if (
        request.headers.get("content-type", "").split(";")[0]
        != "application/x-www-form-urlencoded"
    ):
        raise HTTPException(415, "Expected form data")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 12000:
            raise HTTPException(413, "Form too large")
    try:
        return {
            k: v[0]
            for k, v in parse_qs(
                data.decode(), keep_blank_values=True, max_num_fields=12
            ).items()
        }
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid form")


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def date_label(value) -> str:
    return (
        value.astimezone(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M:%S")
        if value
        else "—"
    )


def page(title: str, body: str, status: int = 200) -> HTMLResponse:
    nonce = secrets.token_urlsafe(20)
    css = (ASSETS / "admin.css").read_text()
    result = HTMLResponse(
        '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{esc(title)} · Karamaz Akademi</title><style nonce="{nonce}">{css}</style>'
        f'<script src="/admin/assets/admin.js" defer nonce="{nonce}"></script></head>'
        '<body><aside><a class="brand" href="/admin">KA<span>Karamaz Akademi<small>Yönetim merkezi</small></span></a>'
        '<nav><a href="/admin">◈ Genel bakış</a><a href="/admin/users">♙ Kullanıcılar</a>'
        '<a href="/admin/announcements">↗ Duyurular</a></nav>'
        "<p>Özel yönetici alanı<br>30 günlük sohbet arşivi</p></aside><main>"
        f"<header><div><small>KARAMAZ AKADEMİ</small><h1>{esc(title)}</h1></div>"
        '<span class="badge">● Güvenli alan</span></header>'
        + body
        + "<footer>Tüm saatler Türkiye saati (UTC+3). Kullanıcı gizlilik tercihleri geçerlidir.</footer></main></body></html>",
        status_code=status,
    )
    result.headers.update(
        {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        }
    )
    return result


def set_cookie(response, name: str, value: str, age: int):
    response.set_cookie(
        name,
        value,
        max_age=age,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/admin",
    )


def login_page(message: str = "", status: int = 401):
    token = f"{int(time.time())}:{secrets.token_hex(16)}"
    token += ":" + signature("login:" + token)
    response = page(
        "Güvenli giriş",
        '<section class="login"><h2>Yalnızca bot yöneticisi</h2>'
        "<p>Parolanı girdikten sonra Telegram yönetici hesabına tek kullanımlık kod gönderilir.</p>"
        f'<p class="warn">{esc(message)}</p><form action="/admin/login" method="post">'
        f'<input type="hidden" name="csrf" value="{esc(token)}">'
        '<label>Yönetici parolası<input type="password" name="password" autocomplete="current-password" required minlength="20"></label>'
        '<button type="submit">Telegram kodu al</button></form></section>',
        status,
    )
    set_cookie(response, LOGIN_COOKIE, token, 900)
    return response


async def protected(request: Request):
    if not config_ok():
        return page(
            "Kurulum gerekli",
            "<section><h2>Panel henüz etkin değil</h2><p>Yönetici, Render ortamında ADMIN_PANEL_ENABLED, ADMIN_USER_ID, ADMIN_WEB_PASSWORD ve DATABASE_URL ayarlarını tamamlamalı.</p></section>",
            503,
        )
    if not await is_admin(request):
        return login_page()
    return None


def auth_form(request: Request, action: str, button: str) -> str:
    return f'<form method="post" action="{esc(action)}"><input type="hidden" name="csrf" value="{esc(csrf_token(request))}"><button>{esc(button)}</button></form>'


def user_rows(people) -> str:
    return "".join(
        f'<tr><td><a href="/admin/user/{int(p["user_id"])}">{int(p["user_id"])}</a></td>'
        f"<td>{esc(p['first_name'] or '—')}<small>@{esc(p['username'] or '—')}</small></td>"
        f"<td>{esc(date_label(p['joined_at']))}</td><td>{esc(date_label(p['last_seen_at']))}</td>"
        f'<td><span class="badge {"on" if p["transcript_enabled"] else "off"}">{"Açık" if p["transcript_enabled"] else "Kapalı"}</span></td>'
        f"<td>{'İzinli' if p['announcements_enabled'] else 'Kapalı'}</td></tr>"
        for p in people
    )


def user_table(people) -> str:
    return (
        '<div class="table-wrap"><table><thead><tr><th>Telegram ID</th><th>Kullanıcı</th><th>İlk giriş*</th><th>Son aktivite</th><th>Kayıt</th><th>Duyuru</th></tr></thead><tbody>'
        + user_rows(people)
        + "</tbody></table></div>"
    )


@router.get("/admin/assets/admin.js")
async def javascript():
    return Response(
        (ASSETS / "admin.js").read_text(),
        media_type="application/javascript",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"},
    )


@router.get("/admin")
async def dashboard(request: Request):
    denied = await protected(request)
    if denied is not None:
        return denied
    db = await asyncio.to_thread(storage)
    stats = await asyncio.to_thread(db.stats)
    people = await asyncio.to_thread(db.users, 10, 0)
    cards = "".join(
        f'<article class="stat"><small>{label}</small><b>{int(stats[key])}</b></article>'
        for key, label in (
            ("users", "Toplam kullanıcı"),
            ("active_1d", "Son 24 saat aktif"),
            ("active_7d", "Son 7 gün aktif"),
            ("messages_30d", "Kaydedilen mesaj"),
            ("chat_optins", "Kayıt açık"),
            ("chat_disabled", "Kayıt kapalı"),
            ("announcement_optins", "Duyuru aboneleri"),
        )
    )
    await asyncio.to_thread(db.audit, owner_id(), "dashboard.view")
    return page(
        "Genel bakış",
        '<p>Bot etkinliği ve izinli iletişimleri tek yerden takip et.</p><div class="stats">'
        + cards
        + "</div>"
        '<section><div class="section-heading"><h2>Son kullanıcı aktiviteleri</h2><a href="/admin/users">Tümünü gör →</a></div>'
        + user_table(people)
        + "<small>* Eski kullanıcılar için bu tarih admin sistemine ilk aktarım zamanıdır.</small></section>"
        + auth_form(request, "/admin/logout", "Güvenli çıkış"),
    )


@router.get("/admin/users")
async def list_users(
    request: Request, offset: int = 0, search: str = "", status: str = "all"
):
    denied = await protected(request)
    if denied is not None:
        return denied
    offset, search = max(0, min(offset, 100000)), search.strip()[:100]
    if status not in ("all", "on", "off"):
        raise HTTPException(400, "Invalid filter")
    people = await asyncio.to_thread(
        (await asyncio.to_thread(storage)).users, 50, offset, search, status
    )
    options = "".join(
        f'<option value="{v}" {"selected" if status == v else ""}>{t}</option>'
        for v, t in (
            ("all", "Tüm kayıt durumları"),
            ("on", "Kayıt açık"),
            ("off", "Kayıt kapalı"),
        )
    )
    links = "".join(
        f'<a class="button secondary" href="/admin/users?{esc(urlencode(dict(offset=n, search=search, status=status)))}">{t}</a>'
        for n, t in ((max(0, offset - 50), "← Önceki"), (offset + 50, "Sonraki →"))
    )
    return page(
        "Kullanıcılar",
        f'<section><form class="filters" method="get"><label>Arama<input name="search" value="{esc(search)}" placeholder="ID, ad veya kullanıcı adı"></label><label>Kayıt durumu<select name="status">{options}</select></label><button>Ara</button></form>'
        + user_table(people)
        + f'<div class="pagination"><span>{offset + 1}–{offset + len(people)} · Sayfa {offset // 50 + 1}</span>{links}</div></section>',
    )


@router.get("/admin/user/{user_id}")
async def user_messages(request: Request, user_id: int):
    denied = await protected(request)
    if denied is not None:
        return denied
    db = await asyncio.to_thread(storage)
    person = await asyncio.to_thread(db.user, user_id)
    if person is None:
        raise HTTPException(404, "User not found")
    await asyncio.to_thread(db.audit, owner_id(), "conversation.view", user_id)
    return page(
        "Kullanıcı detayı",
        f"<section><h2>{esc(person['first_name'])} <small>@{esc(person['username'])}</small></h2><p>Telegram ID: {user_id}<br>İlk giriş: {esc(date_label(person['joined_at']))}<br>Son aktivite: {esc(date_label(person['last_seen_at']))}</p>"
        '<div class="actions">'
        + auth_form(request, f"/admin/user/{user_id}/privacy/stop", "Kaydı durdur")
        + auth_form(
            request,
            f"/admin/user/{user_id}/privacy/erase",
            "Kaydı durdur ve geçmişi sil",
        )
        + "</div>"
        "<p>Yönetici kullanıcı adına kayıt açamaz. Kullanıcı kaydı /gizlilik üzerinden açabilir.</p></section>"
        f'<section id="chat" data-user="{user_id}"><div class="section-heading"><h2>Sohbet arşivi</h2><span id="chat-status" role="status">Yükleniyor…</span></div>'
        '<p>Son 30 gün · Görünür sekmede 20 saniyede bir güncellenir.</p><button id="older" class="secondary" hidden>Önceki mesajları yükle</button><div id="messages" aria-live="polite"></div></section>'
        f'<a class="button" href="/admin/announcements?target={user_id}">Bu kullanıcıya destek mesajı →</a>',
    )


@router.get("/admin/api/user/{user_id}/messages")
async def messages_api(request: Request, user_id: int, before: int = 0, after: int = 0):
    if not await is_admin(request):
        raise HTTPException(401, "Unauthorized")
    db = await asyncio.to_thread(storage)
    person = await asyncio.to_thread(db.user, user_id)
    if person is None:
        raise HTTPException(404, "User not found")
    enabled = person["transcript_enabled"]
    revision_before = await asyncio.to_thread(db.recording_revision, user_id)
    records = (
        await asyncio.to_thread(
            db.conversations, user_id, 40, max(0, before), max(0, after)
        )
        if enabled
        else []
    )
    enabled = (await asyncio.to_thread(db.consent, user_id))[0]
    revision = await asyncio.to_thread(db.recording_revision, user_id)
    if revision != revision_before:
        records = []
    return JSONResponse(
        {
            "enabled": enabled,
            "revision": revision,
            "messages": [
                {
                    **r,
                    "created_ts": r["created_at"].timestamp(),
                    "created_at": date_label(r["created_at"]),
                }
                for r in records
            ]
            if enabled
            else [],
            "has_more": enabled and len(records) == 40,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/admin/user/{user_id}/privacy/{action}")
async def user_privacy(request: Request, user_id: int, action: str):
    form = await values(request)
    await guard_csrf(request, form.get("csrf", ""))
    db = await asyncio.to_thread(storage)
    if action == "stop":
        await asyncio.to_thread(db.set_consent, user_id, "transcript_enabled", False)
    elif action == "erase":
        await asyncio.to_thread(db.delete_transcripts, user_id)
    else:
        raise HTTPException(400, "Invalid action")
    await asyncio.to_thread(db.audit, owner_id(), "privacy." + action, user_id)
    return RedirectResponse(f"/admin/user/{user_id}", 303)


@router.post("/admin/login")
async def login(request: Request):
    if not config_ok():
        raise HTTPException(503, "Admin panel not configured")
    form = await values(request)
    guard_origin(request)
    token = request.cookies.get(LOGIN_COOKIE, "")
    try:
        stamp, nonce, sig = token.split(":")
        if (
            not 0 <= time.time() - int(stamp) < 900
            or not equal(sig, signature("login:" + stamp + ":" + nonce))
            or not equal(token, form.get("csrf", ""))
        ):
            raise ValueError
    except ValueError:
        raise HTTPException(403, "Invalid login form")
    db = await asyncio.to_thread(storage)
    ip = request.client.host if request.client else "unknown"
    if not await asyncio.to_thread(db.admit_login, signature("ip:" + ip)):
        raise HTTPException(429, "Too many attempts")
    if not hmac.compare_digest(
        form.get("password", "").encode(), os.environ["ADMIN_WEB_PASSWORD"].encode()
    ):
        await asyncio.to_thread(db.audit, owner_id(), "login.failed")
        return login_page("Parola geçersiz.")
    challenge, code = secrets.token_urlsafe(32), f"{secrets.randbelow(1000000):06d}"
    await asyncio.to_thread(
        db.challenge,
        digest(challenge),
        signature(challenge + ":" + code),
        owner_id(),
        credential_hash(),
    )
    try:
        await request.app.state.telegram_application.bot.send_message(
            chat_id=owner_id(),
            text=f"🔐 Yönetici web giriş kodun: {code}\n5 dakika geçerli. Giriş isteği sana ait değilse kodu paylaşma.",
        )
    except Exception:
        raise HTTPException(503, "Telegram verification temporarily unavailable")
    response = page(
        "Telegram doğrulaması",
        f'<section class="login"><p>Yönetici Telegram hesabına gönderilen 6 haneli kodu gir.</p><form action="/admin/verify" method="post"><input type="hidden" name="csrf" value="{signature("verify:" + challenge)}"><label>Tek kullanımlık kod<input name="code" inputmode="numeric" pattern="[0-9]{{6}}" maxlength="6" autocomplete="one-time-code" required></label><button>Giriş yap</button></form></section>',
    )
    set_cookie(response, CHALLENGE_COOKIE, challenge, 300)
    return response


@router.post("/admin/verify")
async def verify(request: Request):
    if not config_ok():
        raise HTTPException(503, "Admin panel not configured")
    form = await values(request)
    guard_origin(request)
    token = request.cookies.get(CHALLENGE_COOKIE, "")
    if not token or not equal(form.get("csrf", ""), signature("verify:" + token)):
        raise HTTPException(403, "Invalid verification form")
    db = await asyncio.to_thread(storage)
    if not await asyncio.to_thread(
        db.verify_challenge,
        digest(token),
        signature(token + ":" + form.get("code", "")),
        owner_id(),
        credential_hash(),
    ):
        raise HTTPException(401, "Kod geçersiz veya süresi doldu. Tekrar giriş yap.")
    session = signed_session()
    await asyncio.to_thread(
        db.create_session, digest(session), owner_id(), credential_hash()
    )
    await asyncio.to_thread(db.audit, owner_id(), "login.success")
    response = RedirectResponse("/admin", 303)
    set_cookie(response, COOKIE, session, SESSION_LIFETIME)
    response.delete_cookie(CHALLENGE_COOKIE, path="/admin")
    response.delete_cookie(LOGIN_COOKIE, path="/admin")
    return response


@router.post("/admin/logout")
async def logout(request: Request):
    form = await values(request)
    await guard_csrf(request, form.get("csrf", ""))
    db = await asyncio.to_thread(storage)
    await asyncio.to_thread(db.revoke_session, digest(request.cookies[COOKIE]))
    await asyncio.to_thread(db.audit, owner_id(), "logout")
    response = RedirectResponse("/admin", 303)
    response.delete_cookie(COOKIE, path="/admin")
    return response


@router.get("/admin/announcements")
async def announcements(request: Request, target: int | None = None):
    denied = await protected(request)
    if denied is not None:
        return denied
    db = await asyncio.to_thread(storage)
    history = await asyncio.to_thread(db.dispatch_history, owner_id())
    rows = "".join(
        f"<tr><td>#{r['id']}<small>{esc(date_label(r['created_at']))}</small></td><td>{esc(r['content'][:100])}</td><td>{r['target_id'] or 'İzinli aboneler'}</td><td>{esc(r['state'])}</td><td>{r['sent']} / {r['failed']} / {r['skipped']} / {r['unknown']}</td></tr>"
        for r in history
    )
    return page(
        "Duyurular ve destek",
        "<section><h2>Yeni mesaj hazırla</h2><p>Toplu duyurular yalnızca duyuru izni verenlere gider. Tek kullanıcı mesajı destek iletişimidir.</p>"
        f'<form method="post" action="/admin/announcement/preview"><input type="hidden" name="csrf" value="{esc(csrf_token(request))}">'
        f'<label>Hedef Telegram ID (toplu duyuru için boş bırak)<input name="target" inputmode="numeric" value="{target or ""}"></label>'
        '<label>Mesaj<textarea name="message" rows="6" maxlength="1500" required></textarea></label><button>Önizlemeyi aç →</button></form></section>'
        "<section><h2>Gönderim geçmişi</h2><p>Başarılı / Başarısız / İzni kaldırılmış / Teslimi belirsiz. Kuyruktaki gönderimler servis uyandığında devam eder.</p>"
        '<div class="table-wrap"><table><tr><th>Tarih</th><th>Mesaj</th><th>Hedef</th><th>Durum</th><th>Teslim sayıları</th></tr>'
        + rows
        + '</table></div><a href="/admin/announcements">Durumu yenile</a></section>',
    )


@router.post("/admin/announcement/preview")
async def preview(request: Request):
    form = await values(request)
    await guard_csrf(request, form.get("csrf", ""))
    try:
        target = int(form["target"]) if form.get("target", "").strip() else None
        db = await asyncio.to_thread(storage)
        dispatch_id = await asyncio.to_thread(
            db.draft_dispatch, owner_id(), form.get("message", ""), target
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    count = 1 if target else len(await asyncio.to_thread(db.recipients))
    return page(
        "Gönderim önizlemesi",
        f'<section><h2>{"Destek mesajı" if target else "İzinli abonelere duyuru"}</h2><p>Şu anki alıcı sayısı: {count}</p><div class="preview">{esc(form["message"])}</div><p>5 dakika içinde onayla. Gönderim anında duyuru izni tekrar kontrol edilir.</p>'
        + auth_form(
            request, f"/admin/announcement/{dispatch_id}/confirm", "Gönderimi onayla"
        )
        + auth_form(request, f"/admin/announcement/{dispatch_id}/cancel", "Vazgeç")
        + "</section>",
    )


@router.post("/admin/announcement/{dispatch_id}/{action}")
async def confirm(request: Request, dispatch_id: int, action: str):
    form = await values(request)
    await guard_csrf(request, form.get("csrf", ""))
    if action not in ("confirm", "cancel"):
        raise HTTPException(400, "Invalid action")
    db = await asyncio.to_thread(storage)
    if not await asyncio.to_thread(
        db.confirm_dispatch, dispatch_id, owner_id(), action == "cancel"
    ):
        raise HTTPException(409, "Onay kullanılmış veya süresi dolmuş")
    return RedirectResponse("/admin/announcements", 303)
