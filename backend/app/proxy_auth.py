"""Optional app-level proxy secret check for /api/* (defense in depth).

Normally Caddy protects the web app with basic auth and keeps /api/health and /api/ingest/*
open (the latter verify their own bearer tokens). When COMPASS_API_PROXY_SECRET is set, every
other request to the API must carry the matching X-Compass-Proxy-Secret header, so other
containers on the Docker network cannot call the API directly without going through Caddy.
When the setting is empty (default), the middleware is a no-op.
"""

import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

OPEN_PREFIXES = ("/api/health", "/api/ingest/")
HEADER = b"x-compass-proxy-secret"


class ProxySecret:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        expected = get_settings().compass_api_proxy_secret.strip()
        path = scope.get("path", "")
        if not expected or path == "/api/health" or path.startswith(OPEN_PREFIXES[1]):
            await self.app(scope, receive, send)
            return
        provided = ""
        for key, value in scope.get("headers", ()):
            if key.lower() == HEADER:
                provided = value.decode("latin-1").strip()
                break
        if not hmac.compare_digest(provided, expected):
            response = JSONResponse({"detail": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
