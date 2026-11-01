from contextlib import nullcontext
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.config import Settings, get_settings
from app.ingestion import calendar
from app.models.calendar import CalendarEvent
from app.models.integrations import IntegrationState
from app.models.tasks import Task, TaskSource, TaskStatus
from app.services.clock import local_today

TODAY = date(2026, 10, 19)  # a Monday
BERLIN = ZoneInfo("Europe/Berlin")


def stamp(day: date, hhmm: str) -> str:
    return f"{day:%Y%m%d}T{hhmm}00"


def vevent(uid: str, summary: str, start: str, end: str | None = None, extra: str = "") -> str:
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"SUMMARY:{summary}"]
    if start.startswith("VALUE=DATE:"):
        lines.append(f"DTSTART;{start}")
    else:
        lines.append(f"DTSTART;TZID=Europe/Berlin:{start}")
    if end:
        lines.append(f"DTEND;TZID=Europe/Berlin:{end}")
    lines += [line for line in extra.splitlines() if line]
    lines.append("END:VEVENT")
    return "\n".join(lines)


def ics(*events: str) -> bytes:
    body = "\n".join(events)
    return f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//test//EN\n{body}\nEND:VCALENDAR\n".encode()


def lecture(day: date = TODAY) -> str:
    return vevent(
        "lecture-1",
        "Vorlesung",
        stamp(day, "1400"),
        stamp(day, "1530"),
        "RRULE:FREQ=WEEKLY;COUNT=3\nLOCATION:Room 0.124",
    )


def deadline(uid: str, title: str, day: date, hhmm: str = "2355", extra: str = "") -> str:
    return vevent(uid, f"{title} (Abgabetermin)", stamp(day, hhmm), extra=extra)


def ilias_tasks(session) -> list[Task]:
    return list(session.scalars(select(Task).where(Task.source == TaskSource.ilias)).unique())


# --- Parsing ---------------------------------------------------------------------------------


def test_parse_expands_recurrence_and_converts_to_utc():
    holiday = vevent("holiday", "Feiertag", f"VALUE=DATE:{TODAY + timedelta(days=2):%Y%m%d}")
    events = calendar.parse_ics(ics(lecture(), holiday), TODAY, TODAY + timedelta(days=30))

    lectures = [e for e in events if e.uid == "lecture-1"]
    assert len(lectures) == 3
    assert lectures[0].starts_at == datetime(2026, 10, 19, 12, 0, tzinfo=ZoneInfo("UTC"))
    assert lectures[0].ends_at - lectures[0].starts_at == timedelta(minutes=90)
    assert lectures[0].location == "Room 0.124"
    assert all(e.recurring for e in lectures)

    (day_off,) = [e for e in events if e.uid == "holiday"]
    assert day_off.all_day
    assert day_off.starts_at.astimezone(BERLIN).date() == TODAY + timedelta(days=2)
    assert day_off.ends_at - day_off.starts_at == timedelta(days=1)


def test_feed_names_from_settings():
    settings = Settings(
        ilias_ics_url="https://ilias.example/cal.ics",
        calendar_ics_feeds="google=https://g.example/x.ics?a=b uni=webcal://u.example/y",
    )
    assert settings.calendar_feeds == {
        "ilias": "https://ilias.example/cal.ics",
        "google": "https://g.example/x.ics?a=b",
        "uni": "webcal://u.example/y",
    }
    with pytest.raises(ValueError, match="reserved"):
        _ = Settings(calendar_ics_feeds="ilias=https://x").calendar_feeds
    with pytest.raises(ValueError, match="name=url"):
        _ = Settings(calendar_ics_feeds="https://x").calendar_feeds


# --- Events ----------------------------------------------------------------------------------


def test_sync_stores_updates_and_removes_events(session):
    meeting = vevent("meet", "Meeting", stamp(TODAY, "0900"), stamp(TODAY, "1000"))
    stats = calendar.sync_feed(session, "google", ics(lecture(), meeting), TODAY)
    assert stats == {"events": 4, "created": 4, "updated": 0, "removed": 0}

    again = calendar.sync_feed(session, "google", ics(lecture(), meeting), TODAY)
    assert again == {"events": 4, "created": 0, "updated": 0, "removed": 0}

    renamed = vevent("meet", "Meeting (moved room)", stamp(TODAY, "0900"), stamp(TODAY, "1000"))
    stats = calendar.sync_feed(session, "google", ics(renamed), TODAY)
    assert stats == {"events": 1, "created": 0, "updated": 1, "removed": 3}
    titles = session.scalars(select(CalendarEvent.title).where(CalendarEvent.feed == "google"))
    assert list(titles) == ["Meeting (moved room)"]


def test_feeds_do_not_touch_each_other(session):
    calendar.sync_feed(session, "a", ics(lecture()), TODAY)
    calendar.sync_feed(session, "b", ics(), TODAY)
    assert session.scalars(select(CalendarEvent).where(CalendarEvent.feed == "a")).all()


def test_today_overview_and_calendar_api(client, session):
    today = local_today()
    meeting = vevent("meet", "Meeting", stamp(today, "0900"), stamp(today, "1000"))
    tomorrow = vevent("t", "Tomorrow", stamp(today + timedelta(days=1), "0900"))
    calendar.sync_feed(session, "google", ics(meeting, tomorrow), today)

    overview = client.get("/api/today").json()
    assert [e["title"] for e in overview["events"]] == ["Meeting"]

    week = client.get(
        "/api/calendar",
        params={"start": today.isoformat(), "end": (today + timedelta(days=6)).isoformat()},
    ).json()
    assert [e["title"] for e in week] == ["Meeting", "Tomorrow"]

    too_long = client.get(
        "/api/calendar",
        params={"start": today.isoformat(), "end": (today + timedelta(days=200)).isoformat()},
    )
    assert too_long.status_code == 422


def test_sync_all_records_failure_without_leaking_the_url(session, monkeypatch):
    settings = get_settings()
    secret = "https://ilias.example/calendar.php?token=SECRET"
    monkeypatch.setattr(settings, "ilias_ics_url", secret)
    monkeypatch.setattr(settings, "calendar_ics_feeds", "")

    def broken(url):
        raise OSError(f"cannot reach {url}")

    results = calendar.sync_all(lambda: nullcontext(session), fetch=broken)
    assert "SECRET" not in results["ilias"]
    state = session.get(IntegrationState, "calendar:ilias")
    assert state.last_error and "SECRET" not in state.last_error
    assert state.last_success_at is None

    # sync_all works from the real today, unlike the fixed TODAY of the other tests.
    feed = ics(lecture(local_today()))
    results = calendar.sync_all(lambda: nullcontext(session), fetch=lambda url: feed)
    assert results["ilias"]["created"] >= 1
    session.refresh(state)
    assert state.last_error is None and state.last_success_at is not None


# --- ILIAS deadlines -------------------------------------------------------------------------


def test_ilias_deadlines_become_tasks(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "ilias_deadline_area", "study")
    feed = ics(
        lecture(),
        deadline("ex-1", "Blatt 3", TODAY + timedelta(days=3), extra="DESCRIPTION:Kurs: TI II"),
        deadline("ex-old", "Blatt 1", TODAY - timedelta(days=7)),
    )
    stats = calendar.sync_feed(session, "ilias", feed, TODAY)
    assert stats["deadlines"] == {"created": 1, "updated": 0, "cancelled": 0, "reopened": 0}
    # Deadlines are tasks, not calendar events.
    assert stats["events"] == 3

    (task,) = ilias_tasks(session)
    assert task.title == "Blatt 3"
    assert task.due_date == TODAY + timedelta(days=3)
    assert task.due_time.strftime("%H:%M") == "23:55"
    assert task.area.slug == "study"
    assert task.notes == "Kurs: TI II"
    assert task.external_id == "ex-1"

    again = calendar.sync_feed(session, "ilias", feed, TODAY)
    assert again["deadlines"] == {"created": 0, "updated": 0, "cancelled": 0, "reopened": 0}
    assert len(ilias_tasks(session)) == 1


def test_sync_keeps_user_fields_and_records_deadline_changes(client, session):
    calendar.sync_feed(
        session, "ilias", ics(deadline("ex-1", "Blatt 3", TODAY + timedelta(days=3))), TODAY
    )
    (task,) = ilias_tasks(session)
    privat = next(a["id"] for a in client.get("/api/areas").json() if a["slug"] == "personal")
    planned = (TODAY + timedelta(days=1)).isoformat()
    client.patch(
        f"/api/tasks/{task.id}",
        json={"priority": "urgent", "area_id": privat, "scheduled_date": planned, "tags": ["ti"]},
    )

    moved = deadline("ex-1", "Blatt 3 (korrigiert)", TODAY + timedelta(days=5), "1200")
    stats = calendar.sync_feed(session, "ilias", ics(moved), TODAY)
    assert stats["deadlines"]["updated"] == 1

    session.refresh(task)
    assert task.title == "Blatt 3 (korrigiert)"
    assert task.due_date == TODAY + timedelta(days=5)
    assert task.due_time.strftime("%H:%M") == "12:00"
    assert task.priority.value == "urgent"
    assert task.area_id == privat
    assert task.scheduled_date.isoformat() == planned
    assert task.tags == ["ti"]

    synced = [e for e in task.events if e.type == "synced"]
    assert synced[-1].actor == "ilias"
    assert synced[-1].payload["due_date"]["to"] == (TODAY + timedelta(days=5)).isoformat()


def test_removed_deadline_is_cancelled_and_comes_back(session):
    feed = ics(deadline("ex-1", "Blatt 3", TODAY + timedelta(days=3)))
    calendar.sync_feed(session, "ilias", feed, TODAY)

    stats = calendar.sync_feed(session, "ilias", ics(lecture()), TODAY)
    assert stats["deadlines"]["cancelled"] == 1
    (task,) = ilias_tasks(session)
    assert task.status.value == "cancelled"
    assert task.events[-1].payload["reason"] == "removed_from_source"

    stats = calendar.sync_feed(session, "ilias", feed, TODAY)
    assert stats["deadlines"]["reopened"] == 1
    session.refresh(task)
    assert task.status.value == "open"


def test_finished_or_manually_cancelled_deadlines_stay_as_they_are(client, session):
    feed = ics(
        deadline("done", "Blatt 1", TODAY + timedelta(days=2)),
        deadline("dropped", "Blatt 2", TODAY + timedelta(days=4)),
    )
    calendar.sync_feed(session, "ilias", feed, TODAY)
    done, dropped = sorted(ilias_tasks(session), key=lambda t: t.title)
    client.post(f"/api/tasks/{done.id}/complete")
    client.patch(f"/api/tasks/{dropped.id}", json={"status": "cancelled"})

    calendar.sync_feed(session, "ilias", ics(), TODAY)
    calendar.sync_feed(session, "ilias", feed, TODAY)
    session.refresh(done)
    session.refresh(dropped)
    assert done.status.value == "done"
    # Cancelled by the user, not by the sync, so a sync does not bring it back.
    assert dropped.status.value == "cancelled"


def test_past_deadlines_are_not_cancelled_when_they_leave_the_feed(session):
    calendar.sync_feed(
        session, "ilias", ics(deadline("ex-1", "Blatt 3", TODAY + timedelta(days=1))), TODAY
    )
    later = TODAY + timedelta(days=3)
    stats = calendar.sync_feed(session, "ilias", ics(), later)
    assert stats["deadlines"]["cancelled"] == 0
    (task,) = ilias_tasks(session)
    assert task.status.value == "open"  # now overdue, still the user's to finish


def test_deadline_suffix_only_counts_for_the_ilias_feed(session):
    calendar.sync_feed(
        session, "google", ics(deadline("x", "Blatt 3", TODAY + timedelta(days=1))), TODAY
    )
    assert ilias_tasks(session) == []
    assert session.scalar(select(CalendarEvent).where(CalendarEvent.uid == "x")) is not None


def test_invalid_feed_setting_never_shows_the_url():
    secret = "https://calendar.example/ical/private-SECRET/basic.ics"
    for value in (secret, f"ok=https://a.example {secret}", f"https://x.example/?a=b {secret}"):
        with pytest.raises(ValueError) as exc:
            _ = Settings(calendar_ics_feeds=value).calendar_feeds
        assert "SECRET" not in str(exc.value)
        assert "private" not in str(exc.value)


def test_sync_all_reports_a_broken_setting_instead_of_crashing(session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ilias_ics_url", "")
    monkeypatch.setattr(settings, "calendar_ics_feeds", "https://calendar.example/private-SECRET")

    results = calendar.sync_all(lambda: nullcontext(session), fetch=lambda url: ics())
    assert "entry 1 is not name=url" in results["config"]
    state = session.get(IntegrationState, "calendar:config")
    assert state.last_error and "SECRET" not in state.last_error

    monkeypatch.setattr(settings, "calendar_ics_feeds", "google=https://calendar.example/x")
    results = calendar.sync_all(lambda: nullcontext(session), fetch=lambda url: ics())
    assert results["google"]["events"] == 0
    assert session.get(IntegrationState, "calendar:config") is None


def test_a_new_export_timestamp_is_not_a_change(session):
    def export(dtstamp: str) -> bytes:
        return ics(vevent("m", "Meeting", stamp(TODAY, "0900"), extra=f"DTSTAMP:{dtstamp}"))

    calendar.sync_feed(session, "google", export("20261017T190000Z"), TODAY)
    again = calendar.sync_feed(session, "google", export("20261017T193000Z"), TODAY)
    assert again["updated"] == 0


def test_events_take_the_area_of_their_calendar(client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "calendar_feed_areas", "campus=study")
    today = local_today()
    calendar.sync_feed(
        session, "campus", ics(vevent("l", "Vorlesung", stamp(today, "1000"))), today
    )
    calendar.sync_feed(session, "google", ics(vevent("m", "Kino", stamp(today, "2000"))), today)
    events = client.get(
        "/api/calendar", params={"start": today.isoformat(), "end": today.isoformat()}
    ).json()
    assert {e["title"]: e["area"] for e in events} == {"Vorlesung": "study", "Kino": None}
    assert [e["area"] for e in client.get("/api/today").json()["events"]] == ["study", None]


# --- Deadlines of other feeds --------------------------------------------------------------------


def test_other_feeds_turn_entries_into_deadline_tasks(session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "calendar_deadlines", "moodle= is due$;canvas=^Due: ")
    monkeypatch.setattr(settings, "calendar_feed_areas", "moodle=study")
    soon = TODAY + timedelta(days=3)
    entry = vevent("essay", "Essay is due", stamp(soon, "2359"))
    stats = calendar.sync_feed(session, "moodle", ics(lecture(), entry), TODAY)
    assert stats["deadlines"]["created"] == 1
    titles = set(session.scalars(select(CalendarEvent.title)))
    assert "Essay is due" not in titles and titles  # the lecture stays an event

    task = session.scalar(select(Task).where(Task.source == TaskSource.feed))
    assert (task.title, task.external_id, task.due_date) == ("Essay", "moodle:essay", soon)
    assert task.area.slug == "study"

    # The same UID in another feed is another task, and neither sync touches the other's.
    other = vevent("essay", "Due: Lab report", stamp(soon, "1200"))
    calendar.sync_feed(session, "canvas", ics(other), TODAY)
    titles = {t.title for t in session.scalars(select(Task).where(Task.source == TaskSource.feed))}
    assert titles == {"Essay", "Lab report"}

    # A future deadline that is gone from its feed is cancelled, not deleted.
    assert (
        calendar.sync_feed(session, "moodle", ics(lecture()), TODAY)["deadlines"]["cancelled"] == 1
    )
    session.refresh(task)
    assert task.status == TaskStatus.cancelled


def test_feeds_without_a_pattern_only_have_events(session):
    entry = vevent("essay", "Essay is due", stamp(TODAY + timedelta(days=3), "2359"))
    stats = calendar.sync_feed(session, "google", ics(entry), TODAY)
    assert "deadlines" not in stats and stats["events"] == 1


def test_a_broken_deadline_pattern_is_reported_without_the_feed_url(session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "calendar_deadlines", "moodle=(")
    monkeypatch.setattr(settings, "calendar_ics_feeds", "moodle=https://m.example/SECRET")
    results = calendar.sync_all(lambda: nullcontext(session))
    assert "CALENDAR_DEADLINES" in results["config"] and "SECRET" not in results["config"]


def test_an_event_without_a_title_follows_the_server_language(monkeypatch):
    day = date(2026, 10, 20)
    data = (
        b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:1@x\r\n"
        b"DTSTART;VALUE=DATE:20261020\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    monkeypatch.setattr(get_settings(), "compass_language", "en")
    assert calendar.parse_ics(data, day, day + timedelta(days=1))[0].title == "(no title)"
    monkeypatch.setattr(get_settings(), "compass_language", "de")
    assert calendar.parse_ics(data, day, day + timedelta(days=1))[0].title == "(ohne Titel)"
