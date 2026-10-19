"""News feeds (RSS/Atom): fetch every configured feed and keep its entries in news_items.

Only title, link and a short plain-text summary are stored, never the article. Entries are
unique per feed and entry id, so a feed can be fetched as often as needed. Items older than
NEWS_KEEP_DAYS are removed.
"""

import html
import logging
import re
import urllib.request
from calendar import timegm
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import feedparser
from sqlalchemy import delete, literal_column
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.news import NewsItem
from app.services import integrations
from app.services.clock import utc_now
from app.services.news import terms_of

log = logging.getLogger("compass.news")

UTC = ZoneInfo("UTC")
MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_ITEMS_PER_FEED = 100
SUMMARY_CHARS = 500
CONFIG_STATE = "news:config"

TAG = re.compile(r"<[^>]+>")
URL = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
# Boilerplate of aggregators: hnrss ("Article URL: ... Points: 120"), Reddit ("submitted by").
BOILERPLATE = re.compile(
    r"(?:Article URL|Comments URL|Points|# Comments):\s*\S*|submitted by\s+/u/.*$|\[link\]|"
    r"\[comments\]",
    re.IGNORECASE | re.DOTALL,
)

Fetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class ParsedItem:
    key: str
    url: str
    title: str
    summary: str | None
    published_at: datetime


def fetch_feed(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "Compass news sync (self-hosted, one user)"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_FEED_BYTES + 1)
    if len(data) > MAX_FEED_BYTES:
        raise ValueError("feed is larger than 5 MB")
    return data


def plain(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    text = html.unescape(TAG.sub(" ", value))
    text = URL.sub(" ", BOILERPLATE.sub(" ", text))
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text or None


def parse_feed(data: bytes, now: datetime | None = None) -> list[ParsedItem]:
    now = now or utc_now()
    parsed = feedparser.parse(data)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"not a feed: {type(parsed.bozo_exception).__name__}")
    out = []
    for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
        link = (entry.get("link") or "").strip()
        title = plain(entry.get("title"), 500)
        if not title or not link.startswith(("https://", "http://")):
            continue
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        published = datetime.fromtimestamp(timegm(stamp), UTC) if stamp else now
        out.append(
            ParsedItem(
                key=(entry.get("id") or link)[:1000],
                url=link[:2000],
                title=title,
                summary=plain(entry.get("summary"), SUMMARY_CHARS),
                # A date in the future would keep an item on top for days.
                published_at=min(published, now),
            )
        )
    return out


def store(session: Session, stream: str, feed: str, items: list[ParsedItem]) -> dict:
    keep_since = utc_now() - timedelta(days=get_settings().news_keep_days)
    rows = {
        i.key: {
            "feed": feed,
            "stream": stream,
            "item_key": i.key,
            "url": i.url,
            "title": i.title,
            "summary": i.summary,
            "published_at": i.published_at,
            "terms": terms_of(i.title),
        }
        for i in items
        if i.published_at >= keep_since
    }
    if not rows:
        return {"items": 0, "new": 0}
    stmt = insert(NewsItem).values(list(rows.values()))
    stmt = stmt.on_conflict_do_update(
        index_elements=["feed", "item_key"],
        set_={k: stmt.excluded[k] for k in ("stream", "url", "title", "summary", "terms")},
    ).returning(NewsItem.id, literal_column("xmax = 0"))  # Postgres: true for inserted rows
    result = session.execute(stmt).all()
    session.flush()
    return {"items": len(result), "new": sum(1 for _, fresh in result if fresh)}


def prune(session: Session) -> int:
    cutoff = utc_now() - timedelta(days=get_settings().news_keep_days)
    result = session.execute(delete(NewsItem).where(NewsItem.published_at < cutoff))
    return result.rowcount or 0


def sync_all(session_factory, fetch: Fetcher = fetch_feed) -> dict[str, dict | str]:
    """Fetch every feed in its own transaction, so one broken feed does not stop the others.
    Returns the stats (or the error) per feed."""
    results: dict[str, dict | str] = {}
    with session_factory() as session:
        try:
            feeds = get_settings().news_feed_list
        except ValueError as exc:
            log.error("news config: %s", exc)
            integrations.record_failure(session, CONFIG_STATE, str(exc))
            session.commit()
            return {"config": str(exc)}
        integrations.clear(session, CONFIG_STATE)
        session.commit()

    for stream, feed, url in feeds:
        name = f"news:{feed}"
        try:
            items = parse_feed(fetch(url))
            with session_factory() as session:
                stats = store(session, stream, feed, items)
                integrations.record_success(session, name, {**stats, "stream": stream})
                session.commit()
            results[feed] = stats
        except Exception as exc:  # record any failure, keep the worker alive
            error = f"{type(exc).__name__}: {exc}"[:500]
            log.warning("news %s failed: %s", feed, error)
            with session_factory() as session:
                # A failed statement leaves the transaction aborted (the API shares one session).
                session.rollback()
                integrations.record_failure(session, name, error)
                session.commit()
            results[feed] = error

    with session_factory() as session:
        removed = prune(session)
        session.commit()
    if removed:
        log.info("news: removed %d old items", removed)
    return results
