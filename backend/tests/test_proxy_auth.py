from app.config import get_settings


def test_proxy_secret_disabled_by_default(client):
    assert client.get("/api/setup").status_code == 200


def test_proxy_secret_blocks_unauthenticated_api_calls_when_set(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "compass_api_proxy_secret", "shared-proxy-secret")

    # Health and ingest keep their own authentication model.
    assert client.get("/api/health").status_code == 200

    # Regular API routes require the matching header.
    assert client.get("/api/setup").status_code == 401
    assert client.get("/api/setup", headers={"X-Compass-Proxy-Secret": "wrong"}).status_code == 401
    assert (
        client.get(
            "/api/setup", headers={"X-Compass-Proxy-Secret": "shared-proxy-secret"}
        ).status_code
        == 200
    )
