from datetime import time, timedelta
from types import SimpleNamespace

import pytest
from py_vapid import Vapid
from pywebpush import WebPushException

from app.config import get_settings
from app.ingestion import calendar
from app.models.push import PushSubscription
from app.models.tasks import Task
from app.services import notify, push
from app.services.clock import local_today
from tests.test_analysis import sleep
from tests.test_calendar import ics, stamp, vevent
from tests.test_healthconnect import at, ingest

TODAY = local_today()
TOMORROW = TODAY + timedelta(days=1)
ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


@pytest.fixture
def sent(monkeypatch):
    """Push switched on; messages land in the returned list instead of a push service."""
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_public_key", "public")
    monkeypatch.setattr(settings, "vapid_private_key", "private")
    out = []
    monkeypatch.setattr(push, "_deliver", lambda sub, message: out.append((sub.endpoint, message)))
    return out


def device(session, endpoint=ENDPOINT, topics=None):
    return push.subscribe(session, endpoint, "p256dh-key", "auth-key", topics)


def test_generated_keys_work_for_signing():
    public, private = push.generate_keys()
    assert len(public) == 87 and len(private) == 43  # 65 and 32 bytes, base64url
    headers = Vapid.from_string(private).sign(
        {"sub": "mailto:me@example.com", "aud": "https://fcm.googleapis.com"}
    )
    assert headers["Authorization"].startswith("vapid ")


def test_subscribe_through_the_api(client, sent):
    config = client.get("/api/push/config").json()
    assert config["enabled"] and config["public_key"] == "public"

    data = {"endpoint": ENDPOINT, "keys": {"p256dh": "k", "auth": "a"}}
    r = client.post("/api/push/subscriptions", json=data)
    assert r.status_code == 200
    assert r.json()["topics"] == list(push.TOPICS)

    r = client.post(
        "/api/push/subscriptions/topics", json={"endpoint": ENDPOINT, "topics": ["deadlines"]}
    )
    assert r.json()["topics"] == ["deadlines"]
    bad = {"endpoint": ENDPOINT, "topics": ["spam"]}
    assert client.post("/api/push/subscriptions/topics", json=bad).status_code == 422
    # Subscribing again (new keys) keeps the chosen topics.
    client.post("/api/push/subscriptions", json=data)
    lookup = client.post("/api/push/subscriptions/lookup", json={"endpoint": ENDPOINT})
    assert lookup.json()["topics"] == ["deadlines"]

    assert client.post("/api/push/test", json={"endpoint": ENDPOINT}).json() == {"sent": True}
    assert sent[0][1].tag == "test"

    remove = client.post("/api/push/subscriptions/remove", json={"endpoint": ENDPOINT})
    assert remove.status_code == 204
    lookup = client.post("/api/push/subscriptions/lookup", json={"endpoint": ENDPOINT})
    assert lookup.status_code == 404


def test_subscribe_needs_keys_on_the_server(client):
    assert client.get("/api/push/config").json()["enabled"] is False
    data = {"endpoint": ENDPOINT, "keys": {"p256dh": "k", "auth": "a"}}
    assert client.post("/api/push/subscriptions", json=data).status_code == 409


def test_send_once_per_key_and_only_to_the_topic(session, sent):
    device(session)
    device(session, "https://fcm.googleapis.com/fcm/send/laptop", ["weekly"])
    message = push.Message("Titel", "Text")
    assert push.send(session, "deadlines", "deadline:1", message) == 1
    assert push.send(session, "deadlines", "deadline:1", message) == 0
    assert [endpoint for endpoint, _ in sent] == [ENDPOINT]
    with pytest.raises(push.PushError):
        push.send(session, "spam", "x", message)


def test_gone_devices_are_removed(session, sent, monkeypatch):
    device(session)

    def gone(sub, message):
        raise WebPushException("gone", response=SimpleNamespace(status_code=410))

    monkeypatch.setattr(push, "_deliver", gone)
    assert push.send(session, "deadlines", "deadline:1", push.Message("T", "B")) == 0
    assert session.query(PushSubscription).count() == 0
    # Nothing was delivered, so the key may go out once a device is there.
    assert not push.was_sent(session, "deadline:1")


def test_deadlines_within_24_hours_in_one_notification(session, sent):
    device(session)
    now = at(TODAY, "10:00")
    session.add_all(
        [
            Task(title="Blatt 3", due_date=TOMORROW, due_time=time(9, 0)),
            Task(title="Bericht", due_date=TODAY, due_time=time(18, 0)),
            Task(title="Später", due_date=TOMORROW, due_time=time(12, 0)),
            Task(title="Ohne Zeit", due_date=TODAY),
        ]
    )
    session.flush()
    assert notify.check_deadlines(session, now) == 1
    [(_, message)] = sent
    assert message.title == "3 Abgaben in 24 h"
    assert message.body.splitlines() == [
        "heute 18:00: Bericht",
        "heute 23:59: Ohne Zeit",
        "morgen 09:00: Blatt 3",
    ]
    assert notify.check_deadlines(session, now) == 0
    # Two hours later the next one comes within 24 hours, alone.
    assert notify.check_deadlines(session, now + timedelta(hours=2)) == 1
    assert sent[-1][1].title == "Fällig morgen 12:00"
    assert sent[-1][1].body == "Später"


def test_no_deadline_notifications_in_the_quiet_hours(session, sent):
    device(session)
    session.add(Task(title="Blatt 3", due_date=TOMORROW, due_time=time(10, 0)))
    session.flush()
    assert notify.check_deadlines(session, at(TODAY, "23:30")) == 0
    assert notify.check_deadlines(session, at(TOMORROW, "05:00")) == 0
    assert notify.check_deadlines(session, at(TOMORROW, "08:00")) == 1


def lecture_tomorrow(session, start="0800"):
    calendar.sync_feed(
        session, "campus", ics(vevent("l", "Vorlesung", stamp(TOMORROW, start))), TODAY
    )


def test_bedtime_reminder_before_the_latest_bedtime(session, sent):
    device(session)
    lecture_tomorrow(session)  # up at 06:00, latest bedtime 22:00
    assert notify.check_bedtime(session, at(TODAY, "21:00")) == 0
    assert notify.check_bedtime(session, at(TODAY, "21:40")) == 1
    [(_, message)] = sent
    assert message.title == "Spätestens 22:00 ins Bett"
    assert message.body.startswith("Morgen 08:00 Vorlesung, aufstehen 06:00.")
    assert notify.check_bedtime(session, at(TODAY, "21:50")) == 0


def test_no_bedtime_reminder_when_usually_in_bed_earlier(session, sent):
    device(session)
    d = lambda n: TODAY - timedelta(days=n)  # noqa: E731
    ingest(session, [sleep(f"n{i}", d(i), 1, "21:00", "05:00") for i in range(5)])
    lecture_tomorrow(session)
    assert notify.check_bedtime(session, at(TODAY, "21:40")) == 0
