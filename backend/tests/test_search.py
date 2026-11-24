from datetime import timedelta

from app.models.calendar import CalendarEvent
from app.models.mail import Email
from app.services.clock import utc_now


def task(client, **fields) -> dict:
    response = client.post("/api/tasks", json={"title": "Task", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def event(session, title: str, days: int, location: str | None = None) -> CalendarEvent:
    starts = utc_now() + timedelta(days=days)
    e = CalendarEvent(
        feed="uni", uid=f"{title}-{days}", title=title, location=location, starts_at=starts, raw=""
    )
    session.add(e)
    session.flush()
    return e


def mail(session, subject: str, n: int = 1, **fields) -> Email:
    e = Email(
        account="private",
        msg_key=f"<{n}@example.com>",
        folder="INBOX",
        uidvalidity=1,
        uid=n,
        from_addr="office@example.com",
        subject=subject,
        received_at=utc_now() - timedelta(hours=n),
        **fields,
    )
    session.add(e)
    session.flush()
    return e


def search(client, q: str, **params) -> dict:
    response = client.get("/api/search", params={"q": q, **params})
    assert response.status_code == 200, response.text
    return response.json()


def titles(found: dict, kind: str) -> list[str]:
    return [item.get("title") or item.get("subject") for item in found[kind]]


def test_search_finds_every_kind(client, session):
    task(client, title="Thesis outline")
    client.post("/api/notes", json={"title": "Thesis ideas", "body": "Compare two planners."})
    event(session, "Thesis meeting", days=2)
    mail(session, "Your thesis registration")
    task(client, title="Buy milk")

    found = search(client, "thesis")
    assert titles(found, "tasks") == ["Thesis outline"]
    assert titles(found, "notes") == ["Thesis ideas"]
    assert titles(found, "events") == ["Thesis meeting"]
    assert titles(found, "mails") == ["Your thesis registration"]


def test_tasks_match_notes_and_tags_with_all_words_in_any_order(client):
    task(client, title="Hand in sheet 3", notes="for the algorithms lecture")
    task(client, title="Read paper", tags=["algorithms"])
    task(client, title="Sheet 4")

    assert set(titles(search(client, "algorithms"), "tasks")) == {"Hand in sheet 3", "Read paper"}
    assert titles(search(client, "lecture sheet"), "tasks") == ["Hand in sheet 3"]
    assert titles(search(client, "sheet exam"), "tasks") == []


def test_open_tasks_come_before_done_and_discarded_ones(client):
    done = task(client, title="Report draft")
    client.post(f"/api/tasks/{done['id']}/complete")
    gone = task(client, title="Report for nobody")
    client.patch(f"/api/tasks/{gone['id']}", json={"status": "cancelled"})
    task(client, title="Report final")

    found = search(client, "report")["tasks"]
    assert found[0]["title"] == "Report final"
    assert {t["status"] for t in found} == {"open", "done", "cancelled"}


def test_events_show_what_comes_next_first(client, session):
    event(session, "Seminar", days=-20)
    event(session, "Seminar", days=-3)
    event(session, "Seminar", days=9, location="Room 0.108")
    event(session, "Seminar", days=2)

    found = search(client, "seminar")["events"]
    days = [(e["starts_at"][:10]) for e in found]
    assert days == sorted(days[:2]) + sorted(days[2:], reverse=True)
    assert found[1]["location"] == "Room 0.108"
    assert len(search(client, "0.108")["events"]) == 1


def test_mails_match_sender_and_summary_but_not_removed_ones(client, session):
    mail(session, "Invoice", 1, from_name="Stadtwerke")
    mail(session, "Reminder", 2, summary="The invoice of March is still open.")
    mail(session, "Old invoice", 3, removed_at=utc_now())

    assert titles(search(client, "invoice"), "mails") == ["Invoice", "Reminder"]
    assert titles(search(client, "stadtwerke"), "mails") == ["Invoice"]
    assert titles(search(client, "office@example.com"), "mails") == ["Invoice", "Reminder"]


def test_percent_and_underscore_are_plain_characters(client):
    task(client, title="Reach 100% coverage")
    task(client, title="Rename snake_case fields")
    task(client, title="Something else")

    assert titles(search(client, "100%"), "tasks") == ["Reach 100% coverage"]
    assert titles(search(client, "e_c"), "tasks") == ["Rename snake_case fields"]
    # The filter of the task list had the same gap.
    listed = client.get("/api/tasks", params={"q": "100%"}).json()
    assert [t["title"] for t in listed] == ["Reach 100% coverage"]
    assert client.get("/api/tasks", params={"q": "%"}).json() == listed


def test_short_queries_find_nothing_and_the_limit_applies(client):
    for n in range(5):
        task(client, title=f"Call {n}")
    assert search(client, "c") == {
        "tasks": [],
        "notes": [],
        "journal": [],
        "events": [],
        "mails": [],
    }
    assert search(client, "  ") == {
        "tasks": [],
        "notes": [],
        "journal": [],
        "events": [],
        "mails": [],
    }
    assert len(search(client, "call", limit=3)["tasks"]) == 3
    assert client.get("/api/search").status_code == 422
