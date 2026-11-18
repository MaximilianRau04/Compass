"""The calendar and news feeds in use: those from .env plus those added in the app.

Both are equal for the sync. .env stays read-only: a feed from there can only be hidden, and
comes back when the hidden row is removed.
"""

import re
from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import DEFAULT_CALENDAR_AREAS, get_settings
from app.models.calendar import CalendarEvent
from app.models.feeds import Feed
from app.models.news import NewsItem
from app.schemas.feeds import FeedRead, FeedsRead
from app.services import integrations

CALENDAR = "calendar"
NEWS = "news"


def _rows(session: Session, kind: str) -> dict[str, Feed]:
    rows = session.scalars(select(Feed).where(Feed.kind == kind).order_by(Feed.name))
    return {row.name: row for row in rows}


def calendars(session: Session) -> dict[str, str]:
    """URL per feed. Raises ValueError for a broken setting in .env."""
    rows = _rows(session, CALENDAR)
    feeds = {n: url for n, url in get_settings().calendar_feeds.items() if n not in rows}
    return feeds | {n: row.url for n, row in rows.items() if row.url}


def deadline_patterns(session: Session) -> dict[str, re.Pattern]:
    """Per feed, what marks an entry as a deadline. Raises ValueError like calendars."""
    patterns = dict(get_settings().deadline_patterns)
    for name, row in _rows(session, CALENDAR).items():
        if row.deadline_pattern:
            patterns[name] = re.compile(row.deadline_pattern, re.IGNORECASE)
    return patterns


def calendar_areas(session: Session) -> dict[str, str]:
    rows = _rows(session, CALENDAR)
    return (
        DEFAULT_CALENDAR_AREAS
        | {n: row.area for n, row in rows.items() if row.area}
        | get_settings().calendar_area_map
    )


def news(session: Session) -> list[tuple[str, str, str]]:
    """(stream, name, url) per feed. Raises ValueError for a broken setting in .env."""
    rows = _rows(session, NEWS)
    feeds = [f for f in get_settings().news_feed_list if f[1] not in rows]
    return feeds + [(row.stream or "personal", n, row.url) for n, row in rows.items() if row.url]


def _env_feeds(kind: str) -> dict[str, tuple[str, str | None]]:
    """(url, stream) per feed from .env."""
    settings = get_settings()
    if kind == CALENDAR:
        return {name: (url, None) for name, url in settings.calendar_feeds.items()}
    return {name: (url, stream) for stream, name, url in settings.news_feed_list}


def _read(session: Session, kind: str) -> tuple[list[FeedRead], str | None]:
    """The feeds of one kind for the settings page, without their URLs."""
    rows = _rows(session, kind)
    error = None
    try:
        env = _env_feeds(kind)
    except ValueError as exc:  # names the entry, never its value
        env, error = {}, str(exc)
    out = [
        FeedRead(
            name=name,
            host=urlsplit(url).hostname,
            origin="env",
            hidden=name in rows and not rows[name].url,
            stream=stream,
        )
        for name, (url, stream) in env.items()
        if name not in rows or not rows[name].url
    ]
    out += [
        FeedRead(
            name=name,
            host=urlsplit(row.url).hostname,
            origin="app",
            stream=row.stream,
            area=row.area,
            deadline_pattern=row.deadline_pattern,
        )
        for name, row in rows.items()
        if row.url
    ]
    return sorted(out, key=lambda feed: feed.name), error


def overview(session: Session) -> FeedsRead:
    calendar_feeds, calendar_error = _read(session, CALENDAR)
    news_feeds, news_error = _read(session, NEWS)
    return FeedsRead(
        calendars=calendar_feeds, news=news_feeds, config_error=calendar_error or news_error
    )


def is_free(session: Session, kind: str, name: str) -> bool:
    """Whether a new feed can take this name. The name keys the events or items of a feed."""
    try:
        env = _env_feeds(kind)
    except ValueError:
        env = {}
    return name not in env and name not in _rows(session, kind)


def add(session: Session, kind: str, name: str, url: str, **fields) -> Feed:
    feed = Feed(kind=kind, name=name, url=url, **fields)
    session.add(feed)
    session.flush()
    return feed


def _drop_data(session: Session, kind: str, name: str) -> None:
    """Remove what the feed brought in. Deadline tasks stay: they belong to the user by now."""
    model = CalendarEvent if kind == CALENDAR else NewsItem
    session.execute(delete(model).where(model.feed == name))
    integrations.clear(session, f"{kind}:{name}")


def remove(session: Session, kind: str, name: str) -> bool:
    """Delete a feed of the app or hide one from .env. False if there is no such feed."""
    row = _rows(session, kind).get(name)
    try:
        in_env = name in _env_feeds(kind)
    except ValueError:
        in_env = False
    if in_env:
        if row is None:
            session.add(Feed(kind=kind, name=name))
        else:
            row.url = None
    elif row is not None:
        session.delete(row)
    else:
        return False
    _drop_data(session, kind, name)
    session.flush()
    return True


def restore(session: Session, kind: str, name: str) -> bool:
    """Bring a hidden feed from .env back; the next sync fetches it. False if none is hidden."""
    row = _rows(session, kind).get(name)
    if row is None or row.url:
        return False
    session.delete(row)
    session.flush()
    return True
