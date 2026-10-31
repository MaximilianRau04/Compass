"""ICS calendar feeds: fetch, expand recurrences and mirror the events into calendar_events.

Feeds are read-only. Events inside the sync window are replaced by what the feed says, so
moved or removed events disappear here too. Deadline entries of a feed are not stored as events
but turned into tasks (see app.ingestion.deadlines).
"""

import logging
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
from sqlalchemy import delete, select, tuple_
from sqlalchemy.orm import Session

from app.ingestion import deadlines
from app.models.calendar import CalendarEvent
from app.services import feeds as feed_config
from app.services import integrations
from app.services.clock import local_today, local_tz

log = logging.getLogger("compass.calendar")

PAST_DAYS = 30
FUTURE_DAYS = 180
MAX_FEED_BYTES = 10 * 1024 * 1024
MAX_RAW_CHARS = 20_000
UTC = ZoneInfo("UTC")
CONFIG_STATE = "calendar:config"

Fetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class ParsedEvent:
    uid: str
    title: str
    location: str | None
    description: str | None
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    recurring: bool
    raw: str


def fetch_ics(url: str) -> bytes:
    if url.startswith("webcal://"):
        url = "https://" + url.removeprefix("webcal://")
    if not url.startswith(("https://", "http://")):
        raise ValueError("calendar URL must start with https://, http:// or webcal://")
    request = urllib.request.Request(url, headers={"User-Agent": "Compass calendar sync"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_FEED_BYTES + 1)
    if len(data) > MAX_FEED_BYTES:
        raise ValueError("calendar feed is larger than 10 MB")
    return data


def _as_datetime(value: date | datetime, tz: ZoneInfo) -> tuple[datetime, bool]:
    """Return an aware UTC datetime and whether the value was an all-day date."""
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=tz)  # floating time = local
        return aware.astimezone(UTC), False
    return datetime.combine(value, time.min, tzinfo=tz).astimezone(UTC), True


def _text(component, name: str) -> str | None:
    value = component.get(name)
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _raw(component) -> str:
    """The event as ICS text, without DTSTAMP: some servers (Google) stamp every export with
    the current time, which would make every sync look like a change."""
    text = component.to_ical().decode("utf-8", "replace")
    lines = [line for line in text.splitlines() if not line.startswith("DTSTAMP")]
    return "\n".join(lines)[:MAX_RAW_CHARS]


def parse_ics(data: bytes, start: date, end: date) -> list[ParsedEvent]:
    """All event occurrences that overlap [start, end) in local days."""
    tz = local_tz()
    calendar = icalendar.Calendar.from_ical(data)
    window_start = datetime.combine(start, time.min, tzinfo=tz)
    window_end = datetime.combine(end, time.min, tzinfo=tz)
    events: list[ParsedEvent] = []
    for component in recurring_ical_events.of(calendar).between(window_start, window_end):
        uid = _text(component, "UID")
        dtstart = component.get("DTSTART")
        if not uid or dtstart is None:
            continue
        starts_at, all_day = _as_datetime(dtstart.dt, tz)
        ends_at: datetime | None = None
        if component.get("DTEND") is not None:
            ends_at, _ = _as_datetime(component["DTEND"].dt, tz)
        elif component.get("DURATION") is not None:
            ends_at = starts_at + component["DURATION"].dt
        elif all_day:
            ends_at = starts_at + timedelta(days=1)
        events.append(
            ParsedEvent(
                uid=uid[:500],
                title=(_text(component, "SUMMARY") or "(ohne Titel)")[:500],
                location=(_text(component, "LOCATION") or None),
                description=_text(component, "DESCRIPTION"),
                starts_at=starts_at,
                ends_at=ends_at,
                all_day=all_day,
                recurring=component.get("RRULE") is not None
                or component.get("RECURRENCE-ID") is not None,
                raw=_raw(component),
            )
        )
    return events


def store_events(
    session: Session, feed: str, events: list[ParsedEvent], start: date, end: date
) -> dict:
    """Replace the feed's events inside the window with `events`."""
    tz = local_tz()
    window_start = datetime.combine(start, time.min, tzinfo=tz)
    window_end = datetime.combine(end, time.min, tzinfo=tz)

    by_key = {(e.uid, e.starts_at): e for e in events}
    existing = {
        (row.uid, row.starts_at): row
        for row in session.scalars(
            select(CalendarEvent).where(
                CalendarEvent.feed == feed,
                CalendarEvent.starts_at >= window_start,
                CalendarEvent.starts_at < window_end,
            )
        )
    }
    created = updated = 0
    for key, event in by_key.items():
        fields = {
            "title": event.title,
            "location": event.location[:500] if event.location else None,
            "ends_at": event.ends_at,
            "all_day": event.all_day,
            "raw": event.raw,
        }
        row = existing.get(key)
        if row is None:
            session.add(
                CalendarEvent(feed=feed, uid=event.uid, starts_at=event.starts_at, **fields)
            )
            created += 1
        elif any(getattr(row, k) != v for k, v in fields.items()):
            for k, v in fields.items():
                setattr(row, k, v)
            updated += 1

    stale = [key for key in existing if key not in by_key]
    if stale:
        session.execute(
            delete(CalendarEvent).where(
                CalendarEvent.feed == feed,
                tuple_(CalendarEvent.uid, CalendarEvent.starts_at).in_(stale),
            )
        )
    session.flush()
    return {"events": len(by_key), "created": created, "updated": updated, "removed": len(stale)}


def sync_feed(session: Session, feed: str, data: bytes, today: date | None = None) -> dict:
    today = today or local_today()
    start, end = today - timedelta(days=PAST_DAYS), today + timedelta(days=FUTURE_DAYS)
    events = parse_ics(data, start, end)
    stats: dict = {}
    pattern = feed_config.deadline_patterns(session).get(feed)
    if pattern is not None:
        due = [e for e in events if pattern.search(e.title)]
        events = [e for e in events if not pattern.search(e.title)]
        stats["deadlines"] = deadlines.sync_deadlines(session, feed, due, pattern, today, end)
    stats.update(store_events(session, feed, events, start, end))
    return stats


def sync_all(session_factory, fetch: Fetcher = fetch_ics) -> dict[str, dict | str]:
    """Sync every configured feed in its own transaction, so one broken feed does not stop the
    others. Returns the stats (or the error) per feed."""
    results: dict[str, dict | str] = {}
    # A broken setting is reported like a failed feed instead of stopping the worker.
    with session_factory() as session:
        try:
            feeds, _ = feed_config.calendars(session), feed_config.deadline_patterns(session)
        except ValueError as exc:
            log.error("calendar config: %s", exc)
            integrations.record_failure(session, CONFIG_STATE, str(exc))
            session.commit()
            return {"config": str(exc)}
        integrations.clear(session, CONFIG_STATE)
        session.commit()

    for feed, url in feeds.items():
        name = f"calendar:{feed}"
        try:
            data = fetch(url)
            with session_factory() as session:
                stats = sync_feed(session, feed, data)
                integrations.record_success(session, name, stats)
                session.commit()
            results[feed] = stats
            log.info("calendar %s synced: %s", feed, stats)
        except Exception as exc:  # record any failure, keep the worker alive
            # The URL carries a secret token, so it never goes into the error text.
            error = integrations.describe_error(exc).replace(url, "<url>")
            log.warning("calendar %s failed: %s", feed, error)
            with session_factory() as session:
                integrations.record_failure(session, name, error)
                session.commit()
            results[feed] = error
    return results
