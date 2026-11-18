"""Read-only IMAP access.

Folders are opened with EXAMINE (read-only) and messages fetched with BODY.PEEK, so nothing in the
mailbox changes: no \\Seen flag is set, nothing is moved or deleted. Only headers are fetched for
the list; the text of a single mail is fetched on demand for its summary and never stored.
"""

import base64
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
from app.i18n import t

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


def clean_text(text: str, limit: int = MAX_TEXT_CHARS, keep_quotes: bool = False) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text.replace("\r", ""))
    lines = [line.strip() for line in text.split("\n")]
    if not keep_quotes:
        # Quoted replies repeat older mails; for a summary the new part is what matters.
        lines = [line for line in lines if not line.startswith(">")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return re.sub(r"[ \t]{2,}", " ", text)[:limit]


def _body(message: email.message.EmailMessage, limit: int, keep_quotes: bool) -> str:
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    if part.get_content_subtype() == "html":
        content = html_to_text(content)
    return clean_text(content, limit, keep_quotes)


def message_text(data: bytes, limit: int = MAX_TEXT_CHARS, keep_quotes: bool = False) -> str:
    """Plain text of a (possibly truncated) raw message; empty if nothing readable is found."""
    try:
        message = email.message_from_bytes(data, policy=email.policy.default)
        return _body(message, limit, keep_quotes)
    except Exception:  # broken MIME, unknown charset, cut-off multipart
        return ""


@dataclass
class Message:
    """One mail as the read-only MCP shows it."""

    uid: int
    from_: str
    to: str
    cc: str
    date: str
    subject: str
    seen: bool
    text: str
    attachments: list[str]
    truncated: bool


def parse_message(uid: int, raw: bytes, seen: bool, limit: int) -> Message:
    message = email.message_from_bytes(raw, policy=email.policy.default)
    try:
        text = _body(message, limit, keep_quotes=True)
    except Exception:
        text = ""
    attachments = []
    try:
        for part in message.iter_attachments():
            name = part.get_filename() or part.get_content_type()
            attachments.append(name[:200])
    except Exception:
        pass
    return Message(
        uid=uid,
        from_=_decoded(message, "from"),
        to=_decoded(message, "to")[:1000],
        cc=_decoded(message, "cc")[:1000],
        date=_decoded(message, "date"),
        subject=_decoded(message, "subject"),
        seen=seen,
        text=text,
        attachments=attachments,
        truncated=len(raw) >= BODY_BYTES or len(text) >= limit,
    )


def decode_folder(name: str) -> str:
    """IMAP folder names are modified UTF-7 (RFC 3501): "Entw&APw-rfe" is "Entwürfe"."""

    def part(match: re.Match) -> str:
        chunk = match.group(1)
        if not chunk:
            return "&"
        data = chunk.replace(",", "/")
        return base64.b64decode(data + "=" * (-len(data) % 4)).decode("utf-16-be")

    return re.sub(r"&([^-]*)-", part, name)


def encode_folder(name: str) -> str:
    out, pending = [], ""

    def flush():
        nonlocal pending
        if pending:
            data = base64.b64encode(pending.encode("utf-16-be")).decode().rstrip("=")
            out.append("&" + data.replace("/", ",") + "-")
            pending = ""

    for char in name:
        if 0x20 <= ord(char) <= 0x7E:
            flush()
            out.append("&-" if char == "&" else char)
        else:
            pending += char
    flush()
    return "".join(out)


_LIST = re.compile(rb'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>.+)$')


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
        subject=(_decoded(message, "subject") or t("mail.no_subject"))[:500],
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


def xoauth2(user: str, access_token: str) -> bytes:
    """The SASL XOAUTH2 initial response (Microsoft and Google use the same format)."""
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01".encode()


class Mailbox:
    """One IMAP connection, used as a context manager. Accounts with an OAuth sign-in need the
    current access token (app.services.mail_auth); the others log in with their password."""

    def __init__(self, account: MailAccount, timeout: int = 60, access_token: str | None = None):
        self.account = account
        self.timeout = timeout
        self.access_token = access_token
        self.conn: imaplib.IMAP4_SSL | None = None
        self.folder: str | None = None

    def __enter__(self) -> "Mailbox":
        if self.account.auth != "password" and not self.access_token:
            # The local tools read accounts from their own .env and have no sign-in.
            raise imaplib.IMAP4.error(
                f"{self.account.name} signs in with {self.account.auth.capitalize()}: only the "
                "Compass server can read it so far"
            )
        self.conn = imaplib.IMAP4_SSL(
            self.account.host,
            self.account.port,
            ssl_context=ssl.create_default_context(),
            timeout=self.timeout,
        )
        if self.access_token:
            token = xoauth2(self.account.user, self.access_token)
            try:
                self.conn.authenticate("XOAUTH2", lambda _: token)
            except imaplib.IMAP4.error as exc:
                self.__exit__()
                raise imaplib.IMAP4.error(
                    f"{exc} (the mailbox refused the sign-in: is {self.account.user} the "
                    "address you signed in with, and is IMAP turned on for it?)"
                ) from None
        else:
            self.conn.login(self.account.user, self.account.password)
        return self

    def __exit__(self, *exc) -> None:
        if self.conn is None:
            return
        with contextlib.suppress(imaplib.IMAP4.error, OSError):
            self.conn.logout()

    def examine(self, folder: str) -> int:
        """Open a folder read-only and return its UIDVALIDITY."""
        typ, _ = self.conn.select(_quote(encode_folder(folder)), readonly=True)
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
        """Seen flag per UID that is still in the open folder. Deleted mails (gone, or flagged
        \\Deleted and not yet expunged) are left out, so the caller can tell they are gone."""
        out = {}
        for i in range(0, len(uids), FETCH_CHUNK):
            chunk = ",".join(map(str, uids[i : i + FETCH_CHUNK]))
            typ, data = self.conn.uid("FETCH", chunk, "(UID FLAGS)")
            if typ != "OK":
                # Never read a failed fetch as "all of them were deleted".
                raise imaplib.IMAP4.error(f"cannot fetch flags in {self.folder!r}")
            for item in data:
                meta = item[0] if isinstance(item, tuple) else item
                if not isinstance(meta, bytes):
                    continue
                uid, flags = _UID.search(meta), _FLAGS.search(meta)
                if not uid or (flags and b"\\Deleted" in flags.group(1)):
                    continue
                out[int(uid.group(1))] = bool(flags and b"\\Seen" in flags.group(1))
        return out

    def folders(self) -> list[str]:
        """Selectable folders, decoded (e.g. "Entwürfe")."""
        _, data = self.conn.list()
        out = []
        for line in data:
            if not isinstance(line, bytes) or not (match := _LIST.match(line)):
                continue
            if b"\\Noselect" in match.group("flags"):
                continue
            name = match.group("name").decode(errors="replace").strip()
            if name.startswith('"') and name.endswith('"'):
                name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            out.append(decode_folder(name))
        return out

    def search(self, since: date | None, unread_only: bool, text: str | None) -> list[int]:
        """UIDs matching the filters. ASCII text is searched by the server (headers and body);
        other text only in sender and subject, filtered here, because servers handle non-ASCII
        search terms unevenly."""
        criteria: list[str] = []
        if since:
            criteria += ["SINCE", since.strftime("%d-%b-%Y")]
        if unread_only:
            criteria.append("UNSEEN")
        server_text = text if text and text.isascii() else None
        if server_text:
            criteria += ["TEXT", '"' + server_text.replace("\\", "").replace('"', "") + '"']
        _, data = self.conn.uid("SEARCH", None, *(criteria or ["ALL"]))
        return sorted(map(int, (data[0] or b"").split()))

    def message(self, uid: int, limit: int = 20_000) -> Message | None:
        query = f"(UID FLAGS BODY.PEEK[]<0.{BODY_BYTES}>)"
        _, data = self.conn.uid("FETCH", str(uid), query)
        for item in data:
            if not isinstance(item, tuple):
                continue
            match = _UID.search(item[0])
            if match and int(match.group(1)) == uid:
                flags = _FLAGS.search(item[0])
                seen = bool(flags and b"\\Seen" in flags.group(1))
                return parse_message(uid, item[1], seen, limit)
        return None

    def text(self, uid: int) -> str:
        """Text of one mail in the open folder, for its summary. Not stored anywhere."""
        _, data = self.conn.uid("FETCH", str(uid), f"(BODY.PEEK[]<0.{BODY_BYTES}>)")
        raw = next((item[1] for item in data if isinstance(item, tuple)), b"")
        return message_text(raw)
