import base64
import hashlib
import secrets
from contextlib import nullcontext
from urllib.parse import parse_qs, urlparse

import bcrypt
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.mcp import db as mcp_db
from app.mcp.app import app
from app.mcp.login import reset_failures

BASE = "http://localhost:8001"
RESOURCE = f"{BASE}/mcp"
REDIRECT = "http://localhost:9999/callback"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def app_client():
    # The MCP session manager can only start once per app, so the lifespan runs per module.
    with TestClient(app, base_url=BASE, follow_redirects=False) as client:
        yield client


@pytest.fixture
def http(app_client, session, monkeypatch):
    # BASE matches the default MCP_PUBLIC_URL, which the server reads at import time.
    settings = get_settings()
    assert settings.mcp_public_url == BASE
    monkeypatch.setattr(settings, "compass_basic_auth_user", "owner")
    hashed = bcrypt.hashpw(b"secret", bcrypt.gensalt(rounds=4)).decode()
    # Stored like in .env: every $ doubled for Docker Compose.
    monkeypatch.setattr(settings, "compass_basic_auth_hash", hashed.replace("$", "$$"))
    monkeypatch.setattr("app.mcp.login.FAILURE_DELAY", 0)
    reset_failures()
    mcp_db.set_session_factory(lambda: nullcontext(session))
    yield app_client
    mcp_db.set_session_factory(mcp_db.SessionLocal)


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.rstrip(b"=").decode()


def register(http) -> str:
    response = http.post(
        "/register",
        json={
            "redirect_uris": [REDIRECT],
            "client_name": "Claude Test",
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


def start_authorization(http, client_id: str, challenge: str) -> str:
    response = http.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "scope": "compass",
            "resource": RESOURCE,
        },
    )
    assert response.status_code == 302, response.text
    login = urlparse(response.headers["location"])
    assert login.path == "/oauth/login"
    return parse_qs(login.query)["request"][0]


def login(http, request_id: str, password: str = "secret", action: str = "allow"):
    return http.post(
        "/oauth/login",
        data={"request": request_id, "user": "owner", "password": password, "action": action},
    )


def get_tokens(http) -> dict:
    client_id = register(http)
    verifier, challenge = pkce()
    request_id = start_authorization(http, client_id, challenge)
    response = login(http, request_id)
    assert response.status_code == 302
    callback = urlparse(response.headers["location"])
    params = parse_qs(callback.query)
    assert params["state"] == ["xyz"]
    token = http.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": params["code"][0],
            "code_verifier": verifier,
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "resource": RESOURCE,
        },
    )
    assert token.status_code == 200, token.text
    return {**token.json(), "client_id": client_id, "code": params["code"][0], "verifier": verifier}


def call_mcp(http, access_token: str | None):
    headers = dict(MCP_HEADERS)
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return http.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
    )


def test_discovery_metadata(http):
    resource = http.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["resource"] == RESOURCE
    server = http.get("/.well-known/oauth-authorization-server").json()
    assert server["registration_endpoint"] == f"{BASE}/register"
    assert server["code_challenge_methods_supported"] == ["S256"]


def test_mcp_requires_token(http):
    response = call_mcp(http, None)
    assert response.status_code == 401
    assert "resource_metadata" in response.headers["www-authenticate"]


def test_full_flow_gives_working_token(http):
    tokens = get_tokens(http)
    assert tokens["scope"] == "compass"
    response = call_mcp(http, tokens["access_token"])
    assert response.status_code == 200, response.text
    assert response.json()["result"]["serverInfo"]["name"] == "Compass"


def test_wrong_password_and_lockout(http):
    client_id = register(http)
    request_id = start_authorization(http, client_id, pkce()[1])
    for _ in range(5):
        assert login(http, request_id, password="wrong").status_code == 401
    # Locked now, even with the right password.
    assert login(http, request_id).status_code == 429


def test_deny_redirects_with_error(http):
    client_id = register(http)
    request_id = start_authorization(http, client_id, pkce()[1])
    response = login(http, request_id, action="deny")
    assert response.status_code == 302
    assert parse_qs(urlparse(response.headers["location"]).query)["error"] == ["access_denied"]


def test_login_page_cannot_be_framed(http):
    client_id = register(http)
    request_id = start_authorization(http, client_id, pkce()[1])
    page = http.get("/oauth/login", params={"request": request_id})
    assert page.status_code == 200
    assert "Claude Test" in page.text
    assert page.headers["x-frame-options"] == "DENY"


def test_code_is_single_use(http):
    tokens = get_tokens(http)
    again = http.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": tokens["code"],
            "code_verifier": tokens["verifier"],
            "client_id": tokens["client_id"],
            "redirect_uri": REDIRECT,
        },
    )
    assert again.status_code == 400


def test_refresh_rotates_tokens(http):
    tokens = get_tokens(http)
    refreshed = http.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": tokens["client_id"],
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    new = refreshed.json()
    assert call_mcp(http, new["access_token"]).status_code == 200
    # The old pair is revoked.
    assert call_mcp(http, tokens["access_token"]).status_code == 401
    reuse = http.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": tokens["client_id"],
        },
    )
    assert reuse.status_code == 400


def test_revoke(http):
    tokens = get_tokens(http)
    response = http.post(
        "/revoke",
        # The SDK's revoke handler requires the client_secret field even for public clients.
        data={
            "token": tokens["access_token"],
            "client_id": tokens["client_id"],
            "client_secret": "",
        },
    )
    assert response.status_code == 200, response.text
    assert call_mcp(http, tokens["access_token"]).status_code == 401


def test_token_for_other_resource_is_rejected(http):
    client_id = register(http)
    verifier, challenge = pkce()
    response = http.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "s",
            "resource": "https://other.example.com/mcp",
        },
    )
    request_id = parse_qs(urlparse(response.headers["location"]).query)["request"][0]
    code = parse_qs(urlparse(login(http, request_id).headers["location"]).query)["code"][0]
    token = http.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": client_id,
            "redirect_uri": REDIRECT,
        },
    ).json()["access_token"]
    assert call_mcp(http, token).status_code == 401
