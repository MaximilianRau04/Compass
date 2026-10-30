from app.config import get_settings
from app.models.notes import Note
from app.models.tasks import Task


def test_the_welcome_page_shows_once_on_an_empty_install(client):
    assert client.get("/api/setup").json()["first_run"] is True
    assert client.post("/api/setup/done").status_code == 204
    assert client.get("/api/setup").json()["first_run"] is False


def test_an_install_with_data_never_sees_it(client, session):
    session.add(Task(title="A task"))
    session.flush()
    assert client.get("/api/setup").json()["first_run"] is False


def test_notes_count_as_data_too(client, session):
    session.add(Note(title="A note"))
    session.flush()
    assert client.get("/api/setup").json()["first_run"] is False


def test_sources_say_on_or_off_without_their_values(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "mail_account_names", "")
    monkeypatch.setattr(settings, "calendar_ics_feeds", "work=https://cal.example/SECRET")
    monkeypatch.setattr(settings, "ilias_ics_url", "")
    monkeypatch.setattr(settings, "healthconnect_token", "")
    response = client.get("/api/setup")
    sources = response.json()["sources"]
    assert (sources["calendars"], sources["health"], sources["mail"]) == (True, False, False)
    assert "SECRET" not in response.text
