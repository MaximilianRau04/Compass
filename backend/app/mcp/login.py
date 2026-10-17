"""Owner login and consent page for the built-in OAuth server.

This page is public (Claude's OAuth flow opens it in the browser), so it is hardened:
password checked against the same bcrypt hash as the Caddy login, failed attempts are
throttled per IP and globally, and the page cannot be framed.
"""

import html
import time
from collections import defaultdict, deque

import anyio
import anyio.to_thread
import bcrypt
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app.config import get_settings
from app.mcp.oauth import CompassOAuthProvider, PendingRequest

FAILURE_WINDOW = 15 * 60
MAX_FAILURES_PER_IP = 5
MAX_FAILURES_TOTAL = 20
FAILURE_DELAY = 1.0

_failures: dict[str, deque[float]] = defaultdict(deque)
_all_failures: deque[float] = deque()

TEXT = {
    "de": {
        "title": "Compass verbinden",
        "lead": "<strong>{client}</strong> möchte auf deine Aufgaben in Compass zugreifen.",
        "redirect": "Danach geht es zurück zu {host}.",
        "user": "Benutzer",
        "password": "Passwort",
        "allow": "Zugriff erlauben",
        "deny": "Ablehnen",
        "wrong": "Benutzer oder Passwort ist falsch.",
        "locked": "Zu viele Fehlversuche. Versuch es in 15 Minuten erneut.",
        "expired": "Diese Anfrage ist abgelaufen. Starte die Verbindung in Claude neu.",
        "disabled": "Der Login ist nicht eingerichtet: COMPASS_BASIC_AUTH_USER und "
        "COMPASS_BASIC_AUTH_HASH fehlen in der .env des Servers.",
    },
    "en": {
        "title": "Connect Compass",
        "lead": "<strong>{client}</strong> wants to access your tasks in Compass.",
        "redirect": "Afterwards you will be sent back to {host}.",
        "user": "User",
        "password": "Password",
        "allow": "Allow access",
        "deny": "Deny",
        "wrong": "User or password is wrong.",
        "locked": "Too many failed attempts. Try again in 15 minutes.",
        "expired": "This request has expired. Start the connection in Claude again.",
        "disabled": "Login is not set up: COMPASS_BASIC_AUTH_USER and COMPASS_BASIC_AUTH_HASH "
        "are missing in the server's .env.",
    },
}

SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
    "form-action 'self' https: http://localhost:* http://127.0.0.1:*; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _lang(request: Request) -> str:
    accept = request.headers.get("accept-language", "").lower()
    return "de" if accept.startswith("de") else "en"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _prune(now: float) -> None:
    for entries in [*_failures.values(), _all_failures]:
        while entries and entries[0] < now - FAILURE_WINDOW:
            entries.popleft()


def _locked(ip: str) -> bool:
    _prune(time.monotonic())
    return len(_failures[ip]) >= MAX_FAILURES_PER_IP or len(_all_failures) >= MAX_FAILURES_TOTAL


def _record_failure(ip: str) -> None:
    now = time.monotonic()
    _failures[ip].append(now)
    _all_failures.append(now)


def reset_failures() -> None:
    _failures.clear()
    _all_failures.clear()


def _check_password(user: str, password: str) -> bool:
    settings = get_settings()
    expected_hash = settings.owner_password_hash.encode()
    try:
        password_ok = bcrypt.checkpw(password.encode(), expected_hash)
    except ValueError:
        password_ok = False
    # Compare the user name too, but only after the (slow) hash check to keep timing uniform.
    return password_ok and user == settings.compass_basic_auth_user


def _page(lang: str, body: str, status: int = 200) -> HTMLResponse:
    t = TEXT[lang]
    page = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t["title"]}</title>
<style>
  :root {{ --paper:#eef2f0; --raised:#f8faf9; --ink:#14202b; --muted:#5e6b74; --rule:#d3dbd8;
          --brass:#b07d2b; --brass-ink:#fff; --signal:#d1343b; color-scheme: light; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --paper:#0f1a24; --raised:#15232f; --ink:#e4ebe8; --muted:#8d9aa3; --rule:#26384a;
            --brass:#d3a04e; --brass-ink:#14202b; --signal:#f06a6f; color-scheme: dark; }} }}
  body {{ margin:0; min-height:100dvh; display:grid; place-items:center; background:var(--paper);
         color:var(--ink); font:16px/1.5 system-ui, sans-serif; padding:16px;
         box-sizing:border-box; }}
  main {{ width:100%; max-width:24rem; background:var(--raised); border:1px solid var(--rule);
         border-radius:14px; padding:24px; }}
  h1 {{ margin:0 0 12px; font:600 28px/1.1 "Barlow Condensed","Arial Narrow",sans-serif;
       letter-spacing:.02em; text-transform:uppercase; }}
  p {{ margin:0 0 12px; }} .muted {{ color:var(--muted); font-size:14px; }}
  .error {{ color:var(--signal); }}
  label {{ display:block; margin:14px 0 4px; font-size:12px; letter-spacing:.12em;
          text-transform:uppercase; color:var(--muted); }}
  input {{ width:100%; box-sizing:border-box; padding:10px 12px; border:1px solid var(--rule);
          border-radius:8px; background:var(--paper); color:var(--ink); font-size:16px; }}
  input:focus {{ outline:2px solid var(--brass); outline-offset:1px; }}
  .actions {{ display:flex; gap:8px; margin-top:20px; }}
  button {{ flex:1; padding:10px; border-radius:8px; font-size:15px; cursor:pointer;
           border:1px solid var(--rule); background:transparent; color:var(--ink); }}
  button.primary {{ background:var(--brass); color:var(--brass-ink); border-color:var(--brass);
                   font-weight:600; }}
</style>
</head>
<body><main><h1>{t["title"]}</h1>{body}</main></body>
</html>"""
    return HTMLResponse(page, status_code=status, headers=SECURITY_HEADERS)


def _form(lang: str, pending: PendingRequest, error: str | None = None) -> str:
    t = TEXT[lang]
    error_html = f'<p class="error" role="alert">{error}</p>' if error else ""
    return f"""
<p>{t["lead"].format(client=html.escape(pending.client_name))}</p>
<p class="muted">{t["redirect"].format(host=html.escape(pending.redirect_host))}</p>
{error_html}
<form method="post" action="/oauth/login">
  <input type="hidden" name="request" value="{html.escape(pending.id)}">
  <label for="user">{t["user"]}</label>
  <input id="user" name="user" autocomplete="username" required autofocus>
  <label for="password">{t["password"]}</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required>
  <div class="actions">
    <button type="submit" name="action" value="deny" formnovalidate>{t["deny"]}</button>
    <button type="submit" name="action" value="allow" class="primary">{t["allow"]}</button>
  </div>
</form>"""


def build_login_routes(provider: CompassOAuthProvider):
    async def login(request: Request) -> Response:
        lang = _lang(request)
        t = TEXT[lang]
        settings = get_settings()
        if not settings.compass_basic_auth_user or not settings.owner_password_hash:
            return _page(lang, f'<p class="error">{t["disabled"]}</p>', 503)

        if request.method == "GET":
            request_id = request.query_params.get("request", "")
        else:
            form = await request.form()
            request_id = str(form.get("request", ""))

        pending = await anyio.to_thread.run_sync(provider.get_pending, request_id)
        if pending is None:
            return _page(lang, f'<p class="error">{t["expired"]}</p>', 400)

        if request.method == "GET":
            return _page(lang, _form(lang, pending))

        if form.get("action") == "deny":
            target = await anyio.to_thread.run_sync(provider.deny, request_id)
            return RedirectResponse(target or "/", status_code=302, headers=SECURITY_HEADERS)

        ip = _client_ip(request)
        if _locked(ip):
            return _page(lang, _form(lang, pending, t["locked"]), 429)

        user, password = str(form.get("user", "")), str(form.get("password", ""))
        ok = await anyio.to_thread.run_sync(_check_password, user, password)
        if not ok:
            _record_failure(ip)
            await anyio.sleep(FAILURE_DELAY)
            return _page(lang, _form(lang, pending, t["wrong"]), 401)

        target = await anyio.to_thread.run_sync(provider.approve, request_id)
        if target is None:
            return _page(lang, f'<p class="error">{t["expired"]}</p>', 400)
        return RedirectResponse(target, status_code=302, headers=SECURITY_HEADERS)

    return login
