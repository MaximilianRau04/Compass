from datetime import date, timedelta

from app.services.clock import local_today


def today() -> date:
    return local_today()


def create(client, **fields):
    response = client.post("/api/tasks", json={"title": "Task", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def area_id(client, slug: str) -> int:
    return next(a["id"] for a in client.get("/api/areas").json() if a["slug"] == slug)


def test_seeded_areas(client):
    slugs = [a["slug"] for a in client.get("/api/areas").json()]
    assert slugs == ["uni", "work", "sport", "projects", "personal"]


def test_create_area(client):
    data = {"slug": "family", "name": "Family", "color": "teal", "sort_order": 60}
    response = client.post("/api/areas", json=data)
    assert response.status_code == 201
    assert (response.json()["name"], response.json()["archived"]) == ("Family", False)
    assert "family" in [a["slug"] for a in client.get("/api/areas").json()]

    assert client.post("/api/areas", json=data).status_code == 409
    bad_slug = client.post("/api/areas", json={"slug": "Not Valid", "name": "X"})
    assert bad_slug.status_code == 422


def test_rename_and_archive_area(client):
    uni = area_id(client, "uni")
    response = client.patch(f"/api/areas/{uni}", json={"name": "Study"})
    assert (response.json()["slug"], response.json()["name"]) == ("uni", "Study")

    assert client.patch(f"/api/areas/{uni}", json={"archived": True}).json()["archived"] is True
    assert "uni" not in [a["slug"] for a in client.get("/api/areas").json()]
    everything = client.get("/api/areas?include_archived=true").json()
    assert "uni" in [a["slug"] for a in everything]


def test_update_unknown_area(client):
    assert client.patch("/api/areas/999999", json={"name": "X"}).status_code == 404


def test_quick_add_creates_task_with_parsed_fields(client):
    response = client.post(
        "/api/tasks/quick", json={"text": "morgen 14 Uhr Blatt 3 abgeben #uni !hoch"}
    )
    assert response.status_code == 201
    task = response.json()
    assert task["title"] == "Blatt 3 abgeben"
    assert task["area"]["slug"] == "uni"
    assert task["priority"] == "high"
    assert task["due_date"] == (today() + timedelta(days=1)).isoformat()
    assert task["due_time"] == "14:00:00"

    events = client.get(f"/api/tasks/{task['id']}/events").json()
    assert events[0]["type"] == "created"
    assert events[0]["payload"]["quick_add"].startswith("morgen 14 Uhr")


def test_quick_add_preview_does_not_create(client):
    preview = client.post("/api/tasks/quick/preview", json={"text": "Paper lesen #work"}).json()
    assert preview["title"] == "Paper lesen"
    assert preview["area"]["slug"] == "work"
    assert client.get("/api/tasks").json() == []


def test_quick_add_rejects_empty_title(client):
    response = client.post("/api/tasks/quick", json={"text": "morgen #uni"})
    assert response.status_code == 422


def test_today_overview_buckets(client):
    t = today()
    overdue = create(client, title="overdue", due_date=(t - timedelta(days=1)).isoformat())
    due = create(client, title="due today", due_date=t.isoformat())
    planned = create(client, title="planned", scheduled_date=t.isoformat())
    carried = create(
        client, title="carried over", scheduled_date=(t - timedelta(days=2)).isoformat()
    )
    upcoming = create(client, title="upcoming", due_date=(t + timedelta(days=3)).isoformat())
    create(client, title="far away", due_date=(t + timedelta(days=30)).isoformat())
    done = create(client, title="done")
    client.post(f"/api/tasks/{done['id']}/complete")

    overview = client.get("/api/today").json()

    def ids(key):
        return [task["id"] for task in overview[key]]

    assert ids("overdue") == [overdue["id"]]
    assert ids("due_today") == [due["id"]]
    assert set(ids("scheduled")) == {planned["id"], carried["id"]}
    assert ids("upcoming") == [upcoming["id"]]
    assert ids("done_today") == [done["id"]]


def test_completing_recurring_task_creates_next_instance_once(client):
    t = today()
    task = create(client, title="Müll", scheduled_date=t.isoformat(), recurrence="FREQ=DAILY")

    client.post(f"/api/tasks/{task['id']}/complete")
    open_tasks = client.get("/api/tasks").json()
    assert len(open_tasks) == 1
    follow_up = open_tasks[0]
    assert follow_up["title"] == "Müll"
    assert follow_up["scheduled_date"] == (t + timedelta(days=1)).isoformat()

    # Reopen and complete again: no second follow-up.
    client.post(f"/api/tasks/{task['id']}/reopen")
    client.post(f"/api/tasks/{task['id']}/complete")
    assert len(client.get("/api/tasks").json()) == 1


def test_recurrence_keeps_offset_between_scheduled_and_due(client):
    t = today()
    task = create(
        client,
        scheduled_date=t.isoformat(),
        due_date=(t + timedelta(days=2)).isoformat(),
        recurrence="FREQ=WEEKLY",
    )
    client.post(f"/api/tasks/{task['id']}/complete")
    follow_up = client.get("/api/tasks").json()[0]
    assert follow_up["scheduled_date"] == (t + timedelta(days=7)).isoformat()
    assert follow_up["due_date"] == (t + timedelta(days=9)).isoformat()


def test_update_records_diff_and_cancel_is_the_undo(client):
    task = create(client, title="Alt")
    response = client.patch(
        f"/api/tasks/{task['id']}",
        json={
            "title": "Neu",
            "area_id": area_id(client, "personal"),
            "tags": ["#Einkauf", "einkauf"],
        },
    )
    assert response.status_code == 200
    assert response.json()["tags"] == ["einkauf"]

    client.patch(f"/api/tasks/{task['id']}", json={"status": "cancelled"})
    assert client.get("/api/tasks").json() == []
    cancelled = client.get("/api/tasks", params={"status": "cancelled"}).json()
    assert [t["id"] for t in cancelled] == [task["id"]]

    types = [e["type"] for e in client.get(f"/api/tasks/{task['id']}/events").json()]
    assert types == ["created", "updated", "cancelled"]
    updated = client.get(f"/api/tasks/{task['id']}/events").json()[1]["payload"]
    assert updated["title"] == {"from": "Alt", "to": "Neu"}


def test_validation_errors(client):
    assert client.post("/api/tasks", json={"title": "x", "area_id": 99999}).status_code == 422
    assert (
        client.post("/api/tasks", json={"title": "x", "recurrence": "FREQ=NIE"}).status_code == 422
    )
    assert client.post("/api/tasks", json={"title": ""}).status_code == 422
    assert client.get("/api/tasks/99999").status_code == 404


def test_filters(client):
    uni = area_id(client, "uni")
    a = create(client, title="Vorlesung nacharbeiten", area_id=uni)
    create(client, title="Einkaufen")
    assert [t["id"] for t in client.get("/api/tasks", params={"area_id": uni}).json()] == [a["id"]]
    assert [t["id"] for t in client.get("/api/tasks", params={"q": "vorlesung"}).json()] == [
        a["id"]
    ]


def test_no_delete_endpoint(client):
    task = create(client)
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 405
