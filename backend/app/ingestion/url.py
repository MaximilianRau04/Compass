"""Safe HTTP fetching for user-supplied feed URLs (calendars and news).

Feeds are fetched from the backend container, which shares a private network with Postgres and
other internal services. Before opening a connection (and on every HTTP redirect), the target host
is resolved and rejected if any of its addresses is private, loopback, link-local or otherwise
non-global.
"""

import ipaddress
import socket
import urllib.request
from urllib.parse import urlsplit


# shortcut: urllib resolves the host again when connecting (DNS rebinding), and feeds on a LAN or
# VPN (e.g. 100.64.0.0/10) are rejected; pin the checked IP or add an allowlist if that is needed.
def _ensure_public_host(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"could not resolve host {hostname!r}") from exc
    if not infos:
        raise ValueError(f"could not resolve host {hostname!r}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise ValueError("feed URL must point to a public address")


def check_public_url(url: str, *, allow_webcal: bool = False) -> str:
    """Validate scheme and host of a feed URL and return the normalized HTTP(S) URL."""
    normalized = url.strip()
    if allow_webcal and normalized.lower().startswith("webcal://"):
        normalized = "https://" + normalized[len("webcal://") :]
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in ("http", "https"):
        allowed = "https://, http:// or webcal://" if allow_webcal else "https:// or http://"
        raise ValueError(f"feed URL must start with {allowed}")
    if not parsed.hostname:
        raise ValueError("feed URL has no host")
    _ensure_public_host(parsed.hostname)
    return normalized


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(
    url: str,
    *,
    user_agent: str,
    max_bytes: int,
    size_error: str,
    timeout: int = 30,
    allow_webcal: bool = False,
) -> bytes:
    """Fetch a public HTTP(S) resource with redirect validation and a hard byte limit."""
    safe_url = check_public_url(url, allow_webcal=allow_webcal)
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    request = urllib.request.Request(safe_url, headers={"User-Agent": user_agent})
    with opener.open(request, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(size_error)
    return data
