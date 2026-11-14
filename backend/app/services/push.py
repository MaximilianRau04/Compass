"""Web push: the devices that receive notifications and sending to them.

The browser subscribes with the public VAPID key and hands Compass its endpoint and keys; Compass
signs every message with the private key (VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY in .env). What is
sent when lives in app.services.notify.

Every notification has a key (e.g. "bedtime:2026-10-25"); a key that went out once is never sent
again. A device the push service no longer knows (404/410) is removed.

Create a key pair with: python -m app.services.push
"""

import base64
import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush
from sqlalchemy import any_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.push import PushSent, PushSubscription
from app.services.clock import utc_now

log = logging.getLogger("compass.push")

TOPICS = ("bedtime", "deadlines", "resting", "weekly", "finance", "sync", "claude")
# A device that failed this often in a row (without the push service saying it is gone) is
# dropped too.
MAX_FAILURES = 10


class PushError(ValueError):
    pass


def enabled() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key.strip() and s.vapid_private_key.strip())


def _subject() -> str:
    s = get_settings()
    return s.vapid_subject.strip() or s.mcp_public_url


def check_topics(topics: list[str]) -> list[str]:
    unknown = sorted(set(topics) - set(TOPICS))
    if unknown:
        raise PushError(f"unknown topics: {', '.join(unknown)} (known: {', '.join(TOPICS)})")
    return [t for t in TOPICS if t in topics]


def find(session: Session, endpoint: str) -> PushSubscription | None:
    return session.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))


def subscribe(
    session: Session,
    endpoint: str,
    p256dh: str,
    auth: str,
    topics: list[str] | None = None,
    user_agent: str | None = None,
) -> PushSubscription:
    """Store a device; subscribing again (new keys after a browser update) updates it."""
    if not endpoint.startswith("https://"):
        raise PushError("the endpoint must be an https URL")
    sub = find(session, endpoint)
    if sub is None:
        sub = PushSubscription(endpoint=endpoint, topics=list(TOPICS), failures=0)
        session.add(sub)
    sub.p256dh, sub.auth = p256dh, auth
    sub.failures = 0
    if topics is not None:
        sub.topics = check_topics(topics)
    if user_agent:
        sub.user_agent = user_agent[:300]
    session.flush()
    return sub


def unsubscribe(session: Session, endpoint: str) -> bool:
    sub = find(session, endpoint)
    if sub is None:
        return False
    session.delete(sub)
    session.flush()
    return True


@dataclass
class Message:
    title: str
    body: str
    url: str = "/"
    # Notifications with the same tag replace each other on the phone.
    tag: str | None = None
    # Seconds the push service keeps it for a phone that is offline.
    ttl: int = 6 * 3600
    urgent: bool = False

    def payload(self) -> str:
        return json.dumps(
            {"title": self.title, "body": self.body, "url": self.url, "tag": self.tag},
            ensure_ascii=False,
        )


def _deliver(sub: PushSubscription, message: Message) -> None:
    """Send one message to one device; raises WebPushException. Replaced in tests."""
    webpush(
        {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
        message.payload(),
        vapid_private_key=get_settings().vapid_private_key.strip(),
        vapid_claims={"sub": _subject()},
        ttl=message.ttl,
        headers={"Urgency": "high" if message.urgent else "normal"},
        timeout=10,
    )


def deliver(session: Session, subs: list[PushSubscription], message: Message) -> int:
    """Send to the given devices; returns how many took it."""
    sent = 0
    for sub in subs:
        try:
            _deliver(sub, message)
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                log.info("push: device %s is gone, removed", sub.id)
                session.delete(sub)
                continue
            sub.failures += 1
            log.warning("push to device %s failed (%s): %s", sub.id, status, exc.message[:200])
            if sub.failures >= MAX_FAILURES:
                session.delete(sub)
        except Exception as exc:  # network errors and the like: try again next time
            sub.failures += 1
            log.warning("push to device %s failed: %s", sub.id, exc)
        else:
            sub.failures = 0
            sub.last_sent_at = utc_now()
            sent += 1
    session.flush()
    return sent


def was_sent(session: Session, key: str) -> bool:
    return session.get(PushSent, key) is not None


def sent_recently(session: Session, topic: str, within: timedelta) -> bool:
    return (
        session.scalar(
            select(PushSent.key)
            .where(PushSent.topic == topic, PushSent.sent_at >= utc_now() - within)
            .limit(1)
        )
        is not None
    )


def mark_sent(session: Session, topic: str, key: str, title: str, devices: int = 0) -> None:
    if not was_sent(session, key):
        session.add(PushSent(key=key, topic=topic, title=title[:200], devices=devices))
        session.flush()


def send(session: Session, topic: str, key: str, message: Message) -> int:
    """Send to every device that wants the topic, once per key. Returns the number of devices;
    0 when push is off, nobody wants the topic or the key went out before."""
    if topic not in TOPICS:
        raise PushError(f"unknown topic {topic}")
    if not enabled() or was_sent(session, key):
        return 0
    subs = list(
        session.scalars(select(PushSubscription).where(any_(PushSubscription.topics) == topic))
    )
    if not subs:
        return 0
    sent = deliver(session, subs, message)
    if sent:
        mark_sent(session, topic, key, message.title, sent)
    return sent


def generate_keys() -> tuple[str, str]:
    """A new VAPID key pair as (public, private), both base64url without padding."""
    key = ec.generate_private_key(ec.SECP256R1())

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64(public), b64(private)


if __name__ == "__main__":
    public, private = generate_keys()
    print(f"VAPID_PUBLIC_KEY={public}\nVAPID_PRIVATE_KEY={private}")
