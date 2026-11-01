from contextlib import nullcontext

import pytest
from mcp import Client

from app.mcp import db as mcp_db
from app.mcp.server import mcp
from app.models.oauth import AuditLog
from app.schemas.notes import NoteCreate, NoteUpdate
from app.services import notes as note_service
from app.services.notes import NoteError


def new(session, title, body="", **kw):
    return note_service.create_note(session, NoteCreate(title=title, body=body, **kw))


def titles(found):
    return [f.note.title for f in found]


def test_search_stems_partial_words_and_ranks(session):
    new(session, "Abgaben im Wintersemester", "Blatt 3 bis Freitag")
    new(session, "Postgres Tuning", "shared_buffers erhöhen, VACUUM regelmäßig")
    new(session, "Einkauf", "Milch, Brot. Nichts zu Abgaben.")
    # German stemming: "Abgabe" finds "Abgaben"; the title hit ranks first.
    assert titles(note_service.search(session, "Abgabe")) == [
        "Abgaben im Wintersemester",
        "Einkauf",
    ]
    assert titles(note_service.search(session, "postg")) == ["Postgres Tuning"]
    assert titles(note_service.search(session, "shared_buffers")) == ["Postgres Tuning"]
    assert note_service.search(session, "100%") == []
    found = note_service.search(session, "vacuum")
    assert "VACUUM" in found[0].snippet


def test_filters_pins_and_archive(session, client):
    areas = {a["slug"]: a["id"] for a in client.get("/api/areas").json()}
    a = new(session, "Uni-Notiz", area_id=areas["study"], tags=["Idee", "#idee", "lernen"])
    b = new(session, "Gepinnt", pinned=True)
    assert a.tags == ["idee", "lernen"]
    assert titles(note_service.search(session))[0] == "Gepinnt"
    assert titles(note_service.search(session, area_id=areas["study"])) == ["Uni-Notiz"]
    assert titles(note_service.search(session, tag="#IDEE")) == ["Uni-Notiz"]
    assert note_service.tag_counts(session) == [("idee", 1), ("lernen", 1)]

    note_service.update_note(session, b, NoteUpdate(archived=True))
    assert "Gepinnt" not in titles(note_service.search(session))
    assert titles(note_service.search(session, archived=True)) == ["Gepinnt"]
    note_service.update_note(session, b, NoteUpdate(archived=False, area_id=None))
    assert b.archived_at is None

    with pytest.raises(NoteError, match="No area"):
        new(session, "x", area_id=99999)


def test_update_only_changes_given_fields(session):
    note = new(session, "Titel", "Text", pinned=True)
    note_service.update_note(session, note, NoteUpdate(body="Neu\r\n"))
    assert (note.title, note.body, note.pinned) == ("Titel", "Neu", True)
    # title, body, tags and pinned cannot be set to null
    note_service.update_note(session, note, NoteUpdate(title=None, tags=None))
    assert note.title == "Titel"


def test_append_keeps_existing_text(session):
    note = new(session, "Ideen", "- erste")
    note_service.append(session, note, "- zweite")
    assert note.body == "- erste\n\n- zweite"
    empty = new(session, "Leer")
    assert note_service.append(session, empty, " text ").body == "text"
    with pytest.raises(NoteError):
        note_service.append(session, note, "  ")


def test_quick_note(session):
    note = note_service.quick_note(session, "notiz: Idee für Compass #projects #ideen #Ideen")
    assert note.title == "Idee für Compass"
    assert note.area.slug == "projects"
    assert note.tags == ["ideen"]
    assert note.body == ""

    multi = note_service.quick_note(session, "Note: Titel\nZeile 1\n  - Liste #tag")
    assert (multi.title, multi.body, multi.tags) == ("Titel", "Zeile 1\n  - Liste", ["tag"])

    long = note_service.quick_note(session, "notiz: " + "wort " * 40)
    assert long.title.endswith("…") and len(long.title) <= 120
    assert long.body.startswith("wort wort")
    with pytest.raises(NoteError):
        note_service.quick_note(session, "notiz: #study")


def test_context_notes(session):
    new(session, "Schreibstil", "Duzen, keine Emojis", tags=["kontext"])
    new(session, "Über mich", "Student", tags=["kontext"], pinned=True)
    new(session, "Goals", "Ship it", tags=["context"])
    new(session, "Anderes", "x")
    assert [n.title for n in note_service.context_notes(session)] == [
        "Über mich",
        "Goals",
        "Schreibstil",
    ]


def test_notes_api(client, session):
    created = client.post(
        "/api/notes", json={"title": "Link", "body": "https://x.y", "source": "share"}
    )
    assert created.status_code == 201
    note = created.json()
    assert note["source"] == "share" and note["archived"] is False
    assert client.post("/api/notes", json={"title": "x", "source": "claude"}).status_code == 422

    quick = client.post("/api/notes/quick", json={"text": "notiz: Paper lesen #study"}).json()
    assert quick["area"]["slug"] == "study"

    listed = client.get("/api/notes", params={"q": "paper"}).json()
    assert [n["title"] for n in listed] == ["Paper lesen"]

    patched = client.patch(f"/api/notes/{note['id']}", json={"archived": True, "tags": ["web"]})
    assert patched.json()["archived"] is True and patched.json()["tags"] == ["web"]
    assert client.get(f"/api/notes/{note['id']}").json()["body"] == "https://x.y"
    assert client.get("/api/notes/99999").status_code == 404
    assert client.patch("/api/notes/99999", json={"title": "x"}).status_code == 404

    task = client.post("/api/tasks", json={"title": "Blatt 3"}).json()
    client.post("/api/notes", json={"title": "Lösungsidee", "task_id": task["id"]})
    linked = client.get("/api/notes", params={"task_id": task["id"]}).json()
    assert [n["title"] for n in linked] == ["Lösungsidee"]
    assert {"tag": "web", "count": 1} not in client.get("/api/notes/tags").json()  # archived


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def mcp_client(session):
    mcp_db.set_session_factory(lambda: nullcontext(session))
    async with Client(mcp, raise_exceptions=True) as c:
        yield c
    mcp_db.set_session_factory(mcp_db.SessionLocal)


async def call(client, tool, **args):
    result = await client.call_tool(tool, args)
    assert not result.is_error, result.content
    return result.structured_content


@pytest.mark.anyio
async def test_mcp_notes(mcp_client, session):
    empty = await call(mcp_client, "get_context")
    assert empty["notes"] == [] and "No context notes" in empty["note"]

    note = await call(
        mcp_client, "add_note", title="Compass Ideen", body="- Tagesnotiz", area="projects"
    )
    assert note["source"] == "claude" and note["area"] == "projects"
    await call(mcp_client, "append_note", note_id=note["id"], text="- Korrelationen")
    found = await call(mcp_client, "search_notes", query="korrelation")
    assert [n["title"] for n in found["notes"]] == ["Compass Ideen"]
    full = await call(mcp_client, "get_note", note_id=note["id"])
    assert full["body"] == "- Tagesnotiz\n\n- Korrelationen"

    styl = await call(
        mcp_client, "add_note", title="Schreibstil", body="Duzen", tags=["kontext"], pinned=True
    )
    assert styl["pinned"] is True
    context = await call(mcp_client, "get_context")
    assert [n["title"] for n in context["notes"]] == ["Schreibstil"]

    result = await mcp_client.call_tool("get_note", {"note_id": 99999})
    assert result.is_error and "search_notes" in result.content[0].text
    result = await mcp_client.call_tool("add_note", {"title": "x", "area": "nope"})
    assert result.is_error and "Unknown area" in result.content[0].text
    result = await mcp_client.call_tool("append_note", {"note_id": 99999, "text": "x"})
    assert result.is_error

    actions = {(e.action, e.ok) for e in session.query(AuditLog)}
    assert {("add_note", True), ("append_note", True), ("append_note", False)} <= actions


def test_search_stems_english_words_too(session):
    new(session, "Marathon plan", "How to run a marathon")
    new(session, "Training log", "I was running every day")
    both = {"Marathon plan", "Training log"}
    assert set(titles(note_service.search(session, query="running"))) == both
    # Needs the English stem in the stored words, not only in the query.
    assert set(titles(note_service.search(session, query="runs"))) == both
