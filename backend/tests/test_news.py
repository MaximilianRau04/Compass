from contextlib import nullcontext
from datetime import timedelta
from email.utils import format_datetime

import pytest
from mcp import Client
from sqlalchemy import select

from app.ingestion import news as news_sync
from app.ingestion.news import ParsedItem
from app.mcp import db as mcp_db
from app.mcp.server import mcp
from app.models.integrations import IntegrationState
from app.models.news import Brief, NewsInterest, NewsItem
from app.services import briefs
from app.services import news as news_service
from app.services.clock import local_today, utc_now

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>T</title>
<item><title>Claude Code bekommt Agent Teams</title><link>https://example.com/a</link>
<guid>a-1</guid><pubDate>Mon, 19 Oct 2026 08:00:00 +0000</pubDate>
<description>&lt;p&gt;Anthropic stellt &lt;b&gt;neue&lt;/b&gt; Funktionen vor. https://x.y/z&lt;/p&gt;</description></item>
<item><title>No link here</title></item>
<item><title>Javascript link</title><link>javascript:alert(1)</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>A</title>
<entry><title>Rust 2.0 released</title><link href="https://example.org/rust"/>
<id>tag:rust</id><updated>2026-10-19T07:00:00Z</updated>
<summary>Article URL: https://example.org/rust Comments URL: https://hn/1 Points: 120</summary>
</entry></feed>"""


def recent_rss() -> bytes:
    """RSS with its item from an hour ago: items older than NEWS_KEEP_DAYS are not stored."""
    published = format_datetime(utc_now() - timedelta(hours=1))
    return RSS.replace(b"Mon, 19 Oct 2026 08:00:00 +0000", published.encode())


def item(title, feed="hn", hours_ago=1, summary=None, stream="personal", key=None):
    return (
        feed,
        stream,
        ParsedItem(
            key=key or f"{feed}:{title}",
            url=f"https://example.com/{abs(hash(title))}",
            title=title,
            summary=summary,
            published_at=utc_now() - timedelta(hours=hours_ago),
        ),
    )


def add(session, *entries):
    for feed, stream, parsed in entries:
        news_sync.store(session, stream, feed, [parsed])
    return {i.title: i for i in session.scalars(select(NewsItem))}


def test_terms_drop_stopwords_numbers_and_duplicates():
    assert news_service.terms_of(
        "Show HN: The new Claude-Code for C++ and Node.js, 2026 claude"
    ) == [
        "claude-code",
        "c++",
        "node.js",
        "claude",
    ]
    assert news_service.terms_of("Die neue KI von Google ist da") == ["ki", "google", "da"]


def test_parse_rss_and_atom():
    now = utc_now()
    rss = news_sync.parse_feed(RSS, now)
    assert [i.title for i in rss] == ["Claude Code bekommt Agent Teams"]
    assert rss[0].key == "a-1"
    assert rss[0].summary == "Anthropic stellt neue Funktionen vor."
    atom = news_sync.parse_feed(ATOM, now)
    assert atom[0].url == "https://example.org/rust"
    assert atom[0].summary is None  # only aggregator boilerplate
    with pytest.raises(ValueError, match="not a feed"):
        news_sync.parse_feed(b"<html><body>nope", now)


def test_store_is_idempotent(session):
    parsed = news_sync.parse_feed(recent_rss())
    assert news_sync.store(session, "personal", "t", parsed) == {"items": 1, "new": 1}
    assert news_sync.store(session, "personal", "t", parsed) == {"items": 1, "new": 0}
    row = session.scalar(select(NewsItem))
    assert row.terms == ["claude", "code", "bekommt", "agent", "teams"]


def test_sync_all_records_each_feed(session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(
        get_settings(), "news_feeds", "personal:good=https://a.test/rss general:bad=https://b.test"
    )

    def fetch(url):
        if "b.test" in url:
            raise OSError("down")
        return recent_rss()

    results = news_sync.sync_all(lambda: nullcontext(session), fetch)
    assert results["good"] == {"items": 1, "new": 1}
    assert "down" in results["bad"]
    assert session.get(IntegrationState, "news:good").stats["stream"] == "personal"
    assert session.get(IntegrationState, "news:bad").last_error

    monkeypatch.setattr(get_settings(), "news_feeds", "nonsense")
    assert "config" in news_sync.sync_all(lambda: nullcontext(session), fetch)


def test_profile_topics_and_feedback(session):
    items = add(
        session,
        item("LLM gets a new model"),
        item("Bitcoin hits record", feed="golem"),
        item("Gardening tips for autumn", feed="lobsters"),
    )
    ranked = {s.item.title: s for s in news_service.ranked(session)}
    # Seeded profile: llm +2, bitcoin -1.
    assert ranked["LLM gets a new model"].topics == ["llm"]
    assert ranked["LLM gets a new model"].score == 2
    assert ranked["Bitcoin hits record"].score == -1
    assert ranked["Gardening tips for autumn"].score == 0

    garden = items["Gardening tips for autumn"]
    news_service.set_feedback(session, garden, 1)
    assert session.get(NewsInterest, ("gardening", False)).weight == pytest.approx(0.3)
    assert session.get(NewsInterest, ("feed:lobsters", False)).weight == pytest.approx(0.2)
    # Changing your mind moves by the difference, not twice.
    news_service.set_feedback(session, garden, -1)
    assert session.get(NewsInterest, ("gardening", False)).weight == pytest.approx(-0.3)
    news_service.set_feedback(session, garden, None)
    assert session.get(NewsInterest, ("gardening", False)).weight == pytest.approx(0)

    # Learned words carry over to new items.
    news_service.set_feedback(session, garden, 1)
    add(session, item("Autumn gardening with kids", feed="hn"))
    ranked = {s.item.title: s for s in news_service.ranked(session)}
    assert ranked["Autumn gardening with kids"].score == pytest.approx(0.6)

    assert news_service.ranked(session, include_disliked=False)
    news_service.set_feedback(session, items["Bitcoin hits record"], -1)
    titles = [s.item.title for s in news_service.ranked(session, include_disliked=False)]
    assert "Bitcoin hits record" not in titles


def test_topics_match_whole_words(session):
    add(session, item("Mai-Wetter wird gut"), item("KI-Modell erklärt", feed="golem"))
    ranked = {s.item.title: s for s in news_service.ranked(session)}
    assert ranked["Mai-Wetter wird gut"].topics == []  # "ai" inside "Mai" is no match
    assert ranked["KI-Modell erklärt"].topics == ["ki"]


def test_trends_need_several_feeds_and_a_jump(session):
    add(
        session,
        item("Zed editor 1.0 is out", feed="hn"),
        item("Trying the zed editor", feed="lobsters"),
        item("Zed: first impressions", feed="simonw"),
        item("Python tips", feed="hn"),
        item("Python news", feed="lobsters"),
        item("Python everywhere", feed="simonw"),
    )
    # Python was just as common in the days before, so it is no trend.
    for n in range(12):
        add(session, item(f"python weekly {n}", feed="golem", hours_ago=60 + n * 20))
    found = {t.term: t for t in news_service.trends(session)}
    # "editor" is only in two feeds.
    assert set(found) == {"zed"}
    assert found["zed"].feeds == ["hn", "lobsters", "simonw"]
    ranked = {s.item.title: s for s in news_service.ranked(session)}
    assert ranked["Trying the zed editor"].trending == ["zed"]


def test_replace_manual_topics(session):
    topics = news_service.replace_manual(session, {"  Claude   Code ": 2, "rust": 0, "Zig": 9})
    assert {t.term: t.weight for t in topics} == {"claude code": 2, "zig": 5}


def test_briefs_replace_per_kind_and_day(session):
    first = briefs.save(session, "daily", "Guten Morgen")
    again = briefs.save(session, "daily", "Neu", title="Montag")
    assert first.id == again.id and again.body == "Neu"
    briefs.save(session, "news", "News", day=local_today() - timedelta(days=1))
    assert briefs.latest(session, "news").body == "News"
    assert briefs.latest(session, "news", since=local_today()) is None
    assert set(briefs.kinds(session)) == {"daily", "news"}
    with pytest.raises(briefs.BriefError):
        briefs.save(session, "Daily Brief!", "x")
    with pytest.raises(briefs.BriefError):
        briefs.save(session, "daily", "   ")


def test_news_api(client, session):
    items = add(
        session,
        item("LLM ships memory"),
        item("Wahl in Berlin", feed="tagesschau", stream="general"),
    )
    listed = client.get("/api/news", params={"stream": "personal"}).json()
    assert [i["title"] for i in listed] == ["LLM ships memory"]

    target = items["LLM ships memory"].id
    liked = client.post(f"/api/news/{target}/feedback", json={"value": 1}).json()
    assert liked["feedback"] == 1
    assert client.post(f"/api/news/{target}/feedback", json={"value": 5}).status_code == 422
    assert client.post("/api/news/999999/feedback", json={"value": 1}).status_code == 404

    interests = client.get("/api/news/interests").json()
    assert {"term": "ships", "weight": 0.3} in interests["likes"]
    updated = client.put("/api/news/interests", json={"topics": [{"term": "Zig", "weight": 2}]})
    assert updated.json()["topics"] == [{"term": "zig", "weight": 2.0}]
    assert client.delete("/api/news/interests/learned").status_code == 204
    assert client.get("/api/news/interests").json()["likes"] == []

    assert client.get("/api/briefs/today").json() is None
    briefs.save(session, "daily", "## Heute\n- Blatt 3")
    briefs.save(session, "news", "## KI\n- [x](https://example.com)")
    assert client.get("/api/briefs/today").json()["body"].startswith("## Heute")
    overview = client.get("/api/news/overview").json()
    assert overview["report"]["kind"] == "news"
    assert [i["title"] for i in overview["top"]] == ["LLM ships memory"]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def mcp_client(session):
    mcp_db.set_session_factory(lambda: nullcontext(session))
    async with Client(mcp, raise_exceptions=True) as c:
        yield c
    mcp_db.set_session_factory(mcp_db.SessionLocal)


@pytest.mark.anyio
async def test_mcp_news_and_briefs(mcp_client, session):
    items = add(session, item("LLM ships memory"), item("Bitcoin crash", feed="golem"))
    result = await mcp_client.call_tool("get_news_digest", {"stream": "personal"})
    digest = result.structured_content
    assert "Untrusted" in digest["note"]
    assert digest["items"][0]["title"] == "LLM ships memory"

    bitcoin = items["Bitcoin crash"].id
    result = await mcp_client.call_tool("feedback_news", {"item_id": bitcoin, "value": -1})
    assert result.structured_content["feedback"] == -1
    result = await mcp_client.call_tool("get_news_digest", {})
    assert "Bitcoin crash" not in [i["title"] for i in result.structured_content["items"]]

    result = await mcp_client.call_tool("save_brief", {"body": "## Montag\n- Fokus: Blatt 3"})
    assert result.structured_content["kind"] == "daily"
    assert session.scalar(select(Brief)).actor == "mcp:local"
    result = await mcp_client.call_tool("get_brief", {"kind": "daily"})
    assert result.structured_content["body"].startswith("## Montag")
    result = await mcp_client.call_tool("get_brief", {"kind": "news"})
    assert "No 'news' brief saved yet" in result.content[0].text
    result = await mcp_client.call_tool("save_brief", {"body": "x", "kind": "Not OK"})
    assert result.is_error


def test_fetch_errors_are_readable():
    import errno
    import socket
    import urllib.error

    from app.services.integrations import describe_error

    assert describe_error(urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)) == (
        "HTTP 503 Service Unavailable"
    )
    unreachable = urllib.error.URLError(OSError(errno.ENETUNREACH, "Network is unreachable"))
    assert describe_error(unreachable) == "server not reachable (timeout or no route)"
    assert describe_error(urllib.error.URLError(TimeoutError())) == (
        "server not reachable (timeout or no route)"
    )
    assert describe_error(urllib.error.URLError(socket.gaierror(-2, "x"))) == (
        "host name not found (DNS)"
    )
    assert describe_error(ValueError("not a feed")) == "ValueError: not a feed"
