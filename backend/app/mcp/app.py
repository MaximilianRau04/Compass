"""ASGI entrypoint of the MCP server: uvicorn app.mcp.app:app

Served on its own public hostname. Besides /mcp it exposes only what the OAuth flow needs:
discovery metadata, /register, /authorize, /token, /revoke and the owner login page.
"""

import logging
from urllib.parse import urlparse

from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.mcp.login import build_login_routes
from app.mcp.server import mcp, provider

settings = get_settings()
logging.basicConfig(level=settings.log_level)

mcp.custom_route("/oauth/login", methods=["GET", "POST"])(build_login_routes(provider))


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok"})


public = urlparse(settings.mcp_public_url)
allowed_hosts = [public.netloc, f"{public.hostname}:*", "localhost:*", "127.0.0.1:*"]

app = mcp.streamable_http_app(
    # Stateless JSON responses: no session state to lose on restart, nothing to stream.
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts),
)
