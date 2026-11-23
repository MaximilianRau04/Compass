from datetime import timedelta

import pytest

from app.services import journal
from app.services.clock import local_today

TODAY = local_today()


def test_save_keeps_fields_not_given_and_appends(session):
    journal.save(session, TODAY, mood=4, text="Gut geschlafen.")
    entry = journal.save(session, TODAY, energy=2, text="Nachmittags müde.", append=True)
    assert (entry.mood, entry.energy) == (4, 2)
    assert entry.text == "Gut geschlafen.\n\nNachmittags müde."
    entry = journal.save(session, TODAY, text="Neu")
    assert entry.text == "Neu" and entry.mood == 4


def test_mood_can_be_cleared_and_an_empty_day_has_no_entry(session):
    assert journal.save(session, TODAY, mood=None, energy=None, text="  ") is None
    assert journal.get(session, TODAY) is None
    journal.save(session, TODAY, mood=3, energy=4)
    entry = journal.save(session, TODAY, mood=None)
    assert (entry.mood, entry.energy) == (None, 4)
    assert journal.save(session, TODAY, energy=None) is None
    assert journal.get(session, TODAY) is None


def test_scale_and_future_are_refused(session):
    with pytest.raises(journal.JournalError):
        journal.save(session, TODAY, mood=6)
    with pytest.raises(journal.JournalError):
        journal.save(session, TODAY + timedelta(days=1), mood=3)


def test_journal_api(client, session):
    day = (TODAY - timedelta(days=1)).isoformat()
    saved = client.put(f"/api/journal/{day}", json={"mood": 3, "energy": 4, "text": "ok"})
    assert saved.status_code == 200 and saved.json()["mood"] == 3
    assert client.put(f"/api/journal/{day}", json={"mood": 0}).status_code == 422
    cleared = client.put(f"/api/journal/{day}", json={"mood": None}).json()
    assert cleared["mood"] is None and cleared["energy"] == 4 and cleared["text"] == "ok"
    empty = (TODAY - timedelta(days=2)).isoformat()
    assert client.put(f"/api/journal/{empty}", json={"mood": None, "text": ""}).json() is None
    assert client.get(f"/api/journal/{empty}").json()["entry"] is None
    got = client.get(f"/api/journal/{day}").json()
    assert got["entry"]["text"] == "ok" and got["tasks_done"] == [] and got["briefs"] == []
    assert got["notes"] == []
    assert client.get(f"/api/journal/{TODAY.isoformat()}").json()["entry"] is None
    [listed] = client.get("/api/journal").json()
    assert listed["local_date"] == day


def test_journal_day_lists_notes_touched_that_day(client, session):
    from app.models.notes import Note
    from app.services.clock import utc_now

    active = Note(title="Lecture summary", body="...")
    archived = Note(title="Old note", body="...", archived_at=utc_now())
    session.add_all([active, archived])
    session.commit()

    got = client.get(f"/api/journal/{TODAY.isoformat()}").json()
    assert got["notes"] == [{"id": active.id, "title": "Lecture summary"}]
