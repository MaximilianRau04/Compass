"""Read-only IMAP access.

Folders are opened with EXAMINE (read-only) and messages fetched with BODY.PEEK, so nothing in the
mailbox changes: no \\Seen flag is set, nothing is moved or deleted. Only headers are fetched for
the list; the text of a single mail is fetched on demand for its summary and never stored.
"""

import contextlib
import email
import email.policy
import imaplib
import re
import ssl
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from app.config import MailAccount

HEADER_FIELDS = "FROM SUBJECT DATE MESSAGE-ID LIST-ID LIST-UNSUBSCRIBE PRECEDENCE AUTO-SUBMITTED"
FETCH_CHUNK = 100
# Enough for the text of any normal mail; attachments past this point are cut off.
BODY_BYTES = 300_000
MAX_TEXT_CHARS = 8000
UTC = ZoneInfo("UTC")

_UID = re.compile(rb"UID (\d+)")
_FLAGS = re.compile(rb"FLAGS \(([^)]*)\)")
_INTERNALDATE = re.compile(rb'INTERNALDATE "([^"]+)"')


@dataclass
class Header:
    folder: str
    uidvalidity: int
    uid: int
    msg_key: str
    from_name: str | None
    from_addr: str
    subject: str
    received_at: datetime
    seen: bool
    bulk: bool


class _Text(HTMLParser):
    """Visible text of an HTML mail (no scripts, styles or tags)."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    return "".join(parser.parts)


def clean_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text.replace("\r", ""))
    lines = [line.strip() for line in text.split("\n")]
    # Quoted replies repeat older mails; the new part is what matters.
    lines = [line for line in lines if not line.startswith(">")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return re.sub(r"[ \t]{2,}", " ", text)[:MAX_TEXT_CHARS]


def message_text(data: bytes) -> str:
    """Plain text of a (possibly truncated) raw message; empty if nothing readable is found."""
    try:
        message = email.message_from_bytes(data, policy=email.policy.default)
        part = message.get_body(preferencelist=("plain", "html"))
        if part is None:
            return ""
        content = part.get_content()
        if part.get_content_subtype() == "html":
            content = html_to_text(content)
        return clean_text(content)
    except Exception:  # broken MIME, unknown charset, cut-off multipart
        return ""


def _decoded(message: email.message.EmailMessage, name: str) -> str:
    try:
        return str(message[name] or "").strip()
    except Exception:
        raw = message.get(name, failobj="")
        return str(raw).strip()


def parse_header(
    folder: str, uidvalidity: int, uid: int, flags: bytes, internaldate: bytes | None, raw: bytes
) -> Header:
    message = email.message_from_bytes(raw, policy=email.policy.default)
    from_name, from_addr = None, ""
    try:
        address = message["from"].addresses[0]
        from_name, from_addr = address.display_name or None, address.addr_spec
    except Exception:
        from_addr = _decoded(message, "from")
    received = None
    if internaldate:
        try:
            received = datetime.strptime(internaldate.decode(), "%d-%b-%Y %H:%M:%S %z")
        except ValueError:
            received = None
    if received is None:
        try:
            received = parsedate_to_datetime(_decoded(message, "date"))
        except (TypeError, ValueError):
            received = datetime.now(UTC)
    if received.tzinfo is None:
        received = received.replace(tzinfo=UTC)
    message_id = _decoded(message, "message-id")
    precedence = _decoded(message, "precedence").lower()
    auto = _decoded(message, "auto-submitted").lower()
    return Header(
        folder=folder,
        uidvalidity=uidvalidity,
        uid=uid,
        msg_key=(message_id or f"{folder}/{uidvalidity}/{uid}")[:500],
        from_name=(from_name or None) and from_name[:300],
        from_addr=(from_addr or "?")[:320],
        subject=(_decoded(message, "subject") or "(kein Betreff)")[:500],
        received_at=received.astimezone(UTC),
        seen=b"\\Seen" in flags,
        bulk=bool(
            message.get("list-id")
            or message.get("list-unsubscribe")
            or precedence in ("bulk", "list", "junk")
            or (auto and auto != "no")
        ),
    )


def _quote(folder: str) -> str:
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Mailbox:
    """One IMAP connection, used as a context manager."""

    def __init__(self, account: MailAccount, timeout: int = 60):
        self.account = account
        self.timeout = timeout
        self.conn: imaplib.IMAP4_SSL | None = None
        self.folder: str | None = None

    def __enter__(self) -> "Mailbox":
        self.conn = imaplib.IMAP4_SSL(
            self.account.host,
            self.account.port,
            ssl_context=ssl.create_default_context(),
            timeout=self.timeout,
        )
        self.conn.login(self.account.user, self.account.password)
        return self

    def __exit__(self, *exc) -> None:
        if self.conn is None:
            return
        with contextlib.suppress(imaplib.IMAP4.error, OSError):
            self.conn.logout()

    def examine(self, folder: str) -> int:
        """Open a folder read-only and return its UIDVALIDITY."""
        typ, _ = self.conn.select(_quote(folder), readonly=True)
        if typ != "OK":
            raise imaplib.IMAP4.error(f"cannot open folder {folder!r}")
        self.folder = folder
        _, data = self.conn.response("UIDVALIDITY")
        return int(data[0]) if data and data[0] else 0

    def uids_after(self, last_uid: int) -> list[int]:
        _, data = self.conn.uid("SEARCH", None, "UID", f"{last_uid + 1}:*")
        # "n:*" always matches the newest message, even if its UID is lower than n.
        return sorted(u for u in map(int, (data[0] or b"").split()) if u > last_uid)

    def uids_since(self, day: date) -> list[int]:
        _, data = self.conn.uid("SEARCH", None, "SINCE", day.strftime("%d-%b-%Y"))
        return sorted(map(int, (data[0] or b"").split()))

    def headers(self, uids: list[int], uidvalidity: int) -> list[Header]:
        out = []
        for i in range(0, len(uids), FETCH_CHUNK):
            chunk = ",".join(map(str, uids[i : i + FETCH_CHUNK]))
            query = f"(UID FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])"
            _, data = self.conn.uid("FETCH", chunk, query)
            for item in data:
                if not isinstance(item, tuple):
                    continue
                meta, raw = item
                uid = _UID.search(meta)
                if uid is None:
                    continue
                flags = _FLAGS.search(meta)
                date_match = _INTERNALDATE.search(meta)
                out.append(
                    parse_header(
                        self.folder,
                        uidvalidity,
                        int(uid.group(1)),
                        flags.group(1) if flags else b"",
                        date_match.group(1) if date_match else None,
                        raw,
                    )
                )
        return out

    def seen_flags(self, uids: list[int]) -> dict[int, bool]:
        out = {}
        for i in range(0, len(uids), FETCH_CHUNK):
            chunk = ",".join(map(str, uids[i : i + FETCH_CHUNK]))
            _, data = self.conn.uid("FETCH", chunk, "(UID FLAGS)")
            for item in data:
                meta = item[0] if isinstance(item, tuple) else item
                if not isinstance(meta, bytes):
                    continue
                uid, flags = _UID.search(meta), _FLAGS.search(meta)
                if uid:
                    out[int(uid.group(1))] = bool(flags and b"\\Seen" in flags.group(1))
        return out

    def text(self, uid: int) -> str:
        """Text of one mail in the open folder, for its summary. Not stored anywhere."""
        _, data = self.conn.uid("FETCH", str(uid), f"(BODY.PEEK[]<0.{BODY_BYTES}>)")
        raw = next((item[1] for item in data if isinstance(item, tuple)), b"")
        return message_text(raw)
