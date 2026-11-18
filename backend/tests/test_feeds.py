from datetime import UTC, date, datetime, timedelta
from urllib.error import HTTPError

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.ingestion import calendar, news
from app.models.calendar import CalendarEvent
from app.models.feeds import Feed
from app.models.news import NewsItem
from app.models.tasks import Task
from app.services import feeds, setup

SECRET = "https://cal.example/export?token=SECRET"
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Blog</title>
<item><title>A post</title><link>https://blog.example/a</link><guid>a</guid>
<pubDate>Mon, 26 Oct 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def ics(*titles: str) -> bytes:
    day = date.today() + timedelta(days=3)
    events = "".join(
        f"BEGIN:VEVENT\r\nUID:{n}@example\r\nSUMMARY:{title}\r\n"
        f"DTSTART;VALUE=DATE:{day:%Y%m%d}\r\nEND:VEVENT\r\n"
        for n, title in enumerate(titles)
    )
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{events}END:VCALENDAR\r\n".encode()


@pytest.fixture(autouse=True)
def only_app_feeds(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "calendar_ics_feeds", "")
    monkeypatch.setattr(settings, "ilias_ics_url", "")
    monkeypatch.setattr(settings, "calendar_deadlines", "")
    monkeypatch.setattr(settings, "calendar_feed_areas", "")
    monkeypatch.setattr(settings, "news_feeds", "")


@pytest.fixture
def fetched(monkeypatch):
    """What the next fetch returns, for both kinds of feed."""
    content = {"body": ics("Lecture")}
    monkeypatch.setattr(calendar, "fetch_ics", lambda url: content["body"])
    monkeypatch.setattr(news, "fetch_feed", lambda url: content["body"])
    return content


def add_calendar(client, name="work", url=SECRET, **fields):
    return client.post("/api/feeds/calendar", json={"name": name, "url": url, **fields})


def test_a_new_calendar_is_fetched_right_away(client, session, fetched):
    assert add_calendar(client).status_code == 201
    event = session.scalar(select(CalendarEvent).where(CalendarEvent.feed == "work"))
    assert event.title == "Lecture"
    states = {s["name"] for s in client.get("/api/integrations").json()}
    assert "calendar:work" in states


def test_the_api_never_sends_a_calendar_link_back(client, fetched):
    created = add_calendar(client)
    listed = client.get("/api/feeds")
    assert created.json()["host"] == "cal.example"
    assert "SECRET" not in created.text and "SECRET" not in listed.text
    assert "SECRET" not in client.get("/api/setup").text


def test_a_link_that_does_not_work_is_not_saved(client, session, monkeypatch):
    def refused(url):
        raise HTTPError(url, 403, "Forbidden", None, None)

    monkeypatch.setattr(calendar, "fetch_ics", refused)
    response = add_calendar(client)
    assert response.status_code == 422
    assert "HTTP 403" in response.json()["detail"]
    assert "SECRET" not in response.text
    assert client.get("/api/feeds").json()["calendars"] == []


def test_a_page_that_is_no_calendar_is_not_saved(client, fetched):
    fetched["body"] = b"<html>login</html>"
    response = add_calendar(client)
    assert response.status_code == 422
    assert response.json()["detail"] == "cannot read the feed: no feed found at this link"
    assert client.get("/api/feeds").json()["calendars"] == []


def test_a_page_that_is_no_news_feed_is_not_saved(client, fetched):
    fetched["body"] = b"<html>hello</html>"
    response = client.post("/api/feeds/news", json={"name": "blog", "url": "https://blog.example/"})
    assert response.status_code == 422
    assert client.get("/api/feeds").json()["news"] == []


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://x.example/a", "cal.example/x", "https://a b"]
)
def test_only_web_links_are_accepted(client, url):
    assert add_calendar(client, url=url).status_code == 422


def test_a_broken_deadline_pattern_is_refused(client):
    assert add_calendar(client, deadline_pattern="(").status_code == 422


def test_entries_matching_the_pattern_become_tasks(client, session, fetched):
    fetched["body"] = ics("Sheet 3 is due", "Lecture")
    response = add_calendar(client, name="moodle", deadline_pattern=" is due$")
    assert response.status_code == 201
    titles = [t.title for t in session.scalars(select(Task)).unique()]
    assert titles == ["Sheet 3"]
    events = session.scalars(select(CalendarEvent).where(CalendarEvent.feed == "moodle")).all()
    assert [e.title for e in events] == ["Lecture"]


def test_campus_calendar_added_in_app_defaults_to_uni(client, fetched):
    assert add_calendar(client, name="campus").status_code == 201
    assert add_calendar(client, name="uni", area="study").status_code == 201
    today = date.today()
    params = {"start": today.isoformat(), "end": (today + timedelta(days=7)).isoformat()}
    events = client.get("/api/calendar", params=params).json()
    assert {e["feed"]: e["area"] for e in events} == {"campus": "uni", "uni": "study"}


def test_a_calendar_added_in_the_app_has_its_area(client, session, fetched):
    assert add_calendar(client, area="study").status_code == 201
    today = date.today()
    listed = client.get(
        "/api/calendar",
        params={"start": today.isoformat(), "end": (today + timedelta(days=7)).isoformat()},
    ).json()
    assert [e["area"] for e in listed] == ["study"]


def test_a_name_can_only_be_taken_once(client, fetched, monkeypatch):
    assert add_calendar(client).status_code == 201
    assert add_calendar(client).status_code == 409
    monkeypatch.setattr(get_settings(), "calendar_ics_feeds", "google=https://g.example/x")
    assert add_calendar(client, name="google").status_code == 409


def test_a_news_feed_is_fetched_right_away(client, session, fetched):
    fetched["body"] = RSS
    response = client.post(
        "/api/feeds/news",
        json={"name": "blog", "url": "https://blog.example/rss", "stream": "general"},
    )
    assert response.status_code == 201
    assert response.json()["stream"] == "general"
    assert session.scalar(select(NewsItem).where(NewsItem.feed == "blog")).title == "A post"


def test_the_sync_reads_feeds_from_env_and_from_the_app(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "calendar_ics_feeds", "google=https://g.example/x")
    monkeypatch.setattr(get_settings(), "news_feeds", "general:bbc=https://bbc.example/rss")
    feeds.add(session, feeds.CALENDAR, "work", SECRET)
    feeds.add(session, feeds.NEWS, "blog", "https://blog.example/rss", stream="personal")
    assert feeds.calendars(session) == {"google": "https://g.example/x", "work": SECRET}
    assert feeds.news(session) == [
        ("general", "bbc", "https://bbc.example/rss"),
        ("personal", "blog", "https://blog.example/rss"),
    ]


def test_removing_a_calendar_takes_its_events_but_not_its_tasks(client, session, fetched):
    fetched["body"] = ics("Sheet 3 is due", "Lecture")
    add_calendar(client, name="moodle", deadline_pattern=" is due$")
    assert client.delete("/api/feeds/calendar/moodle").status_code == 204
    assert session.scalars(select(CalendarEvent)).all() == []
    assert session.scalar(select(Feed)) is None
    assert [t.title for t in session.scalars(select(Task)).unique()] == ["Sheet 3"]
    assert "calendar:moodle" not in {s["name"] for s in client.get("/api/integrations").json()}


def test_removing_a_news_feed_takes_its_items(client, session, fetched):
    fetched["body"] = RSS
    client.post("/api/feeds/news", json={"name": "blog", "url": "https://blog.example/rss"})
    assert client.delete("/api/feeds/news/blog").status_code == 204
    assert session.scalars(select(NewsItem)).all() == []


def test_a_feed_from_env_can_be_hidden_and_brought_back(client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "news_feeds", "general:bbc=https://bbc.example/rss")
    session.add(
        NewsItem(
            feed="bbc",
            stream="general",
            item_key="a",
            url="https://bbc.example/a",
            title="An item",
            published_at=datetime(2026, 10, 30, tzinfo=UTC),
        )
    )
    session.flush()
    entry = client.get("/api/feeds").json()["news"][0]
    assert (entry["name"], entry["origin"], entry["hidden"]) == ("bbc", "env", False)

    assert client.delete("/api/feeds/news/bbc").status_code == 204
    assert feeds.news(session) == []
    assert session.scalars(select(NewsItem)).all() == []
    assert client.get("/api/feeds").json()["news"][0]["hidden"] is True

    assert client.post("/api/feeds/news/bbc/restore").status_code == 204
    assert [f[1] for f in feeds.news(session)] == ["bbc"]
    assert client.get("/api/feeds").json()["news"][0]["hidden"] is False


def test_only_hidden_feeds_can_be_restored(client, fetched):
    add_calendar(client)
    assert client.post("/api/feeds/calendar/work/restore").status_code == 404
    assert client.post("/api/feeds/calendar/nothing/restore").status_code == 404


def test_removing_an_unknown_feed_is_a_404(client):
    assert client.delete("/api/feeds/calendar/nothing").status_code == 404


def test_a_broken_env_setting_does_not_break_the_page(client, fetched, monkeypatch):
    add_calendar(client)
    monkeypatch.setattr(get_settings(), "calendar_ics_feeds", "https://x.example/SECRET")
    response = client.get("/api/feeds")
    assert response.status_code == 200
    assert "CALENDAR_ICS_FEEDS" in response.json()["config_error"]
    assert "SECRET" not in response.text
    assert client.get("/api/setup").status_code == 200


def test_the_welcome_page_counts_feeds_of_the_app(client, session, fetched):
    assert setup.sources(session)["calendars"] is False
    add_calendar(client)
    assert setup.sources(session)["calendars"] is True
