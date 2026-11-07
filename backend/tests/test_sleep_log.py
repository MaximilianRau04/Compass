from datetime import timedelta

from sqlalchemy import select

from app.models.health import DailyMetrics, HealthRecord, SleepSession
from app.services.clock import local_today
from tests.test_healthconnect import ZEPP, at, ingest, iso, night


def manual(client, wake_day=None, bed="23:30", wake="07:00", awake=0):
    wake_day = wake_day or local_today()
    bed_day = wake_day - timedelta(days=1) if bed > wake else wake_day
    return client.post(
        "/api/sleep/manual",
        json={
            "start_at": iso(at(bed_day, bed)),
            "end_at": iso(at(wake_day, wake)),
            "awake_minutes": awake,
        },
    )


def test_a_night_entered_by_hand_counts_like_a_watch_night(client, session):
    yesterday = local_today() - timedelta(days=1)
    response = manual(client, yesterday, awake=30)
    assert response.status_code == 201
    entered = response.json()
    assert entered["local_date"] == yesterday.isoformat()
    assert (entered["in_bed_minutes"], entered["asleep_minutes"]) == (450, 420)
    assert entered["source_app"] == "compass"
    assert (
        session.scalar(
            select(DailyMetrics.sleep_minutes).where(DailyMetrics.local_date == yesterday)
        )
        == 420
    )

    summary = client.get("/api/sleep/summary?days=7").json()
    assert [n["id"] for n in summary["nights"]] == [entered["id"]]
    assert [n["id"] for n in client.get("/api/sleep/manual").json()] == [entered["id"]]

    # The phone's snapshot of the last days does not know it and must not remove it.
    ingest(
        session,
        [night("watch-1")],
        snapshots=[
            {
                "type": "sleep",
                "since": iso(at(yesterday - timedelta(days=3), "00:00")),
                "ids": ["watch-1"],
            }
        ],
    )
    record = session.scalar(select(HealthRecord).where(HealthRecord.source_app == "compass"))
    assert record.deleted_at is None
    assert session.get(SleepSession, entered["id"]) is not None


def test_bad_nights_are_refused(client, session):
    assert manual(client, bed="07:00", wake="07:00").status_code == 422  # zero length
    assert manual(client, bed="08:00", wake="06:00", awake=600).status_code == 422
    tomorrow = local_today() + timedelta(days=1)
    assert manual(client, tomorrow).status_code == 422  # in the future
    assert manual(client, local_today() - timedelta(days=2)).status_code == 201
    overlapping = manual(client, local_today() - timedelta(days=2), bed="01:00", wake="09:00")
    assert overlapping.status_code == 422


def test_only_nights_entered_by_hand_can_be_deleted(client, session):
    ingest(session, [night("watch-2", local_today() - timedelta(days=3))])
    watch = session.scalar(select(SleepSession).where(SleepSession.source_app == ZEPP))
    assert client.delete(f"/api/sleep/manual/{watch.id}").status_code == 404

    day = local_today() - timedelta(days=1)
    entered = manual(client, day).json()
    assert client.delete(f"/api/sleep/manual/{entered['id']}").status_code == 204
    assert session.scalar(select(HealthRecord).where(HealthRecord.source_app == "compass")) is None
    assert session.scalar(select(DailyMetrics).where(DailyMetrics.local_date == day)) is None
    assert client.get("/api/sleep/manual").json() == []
