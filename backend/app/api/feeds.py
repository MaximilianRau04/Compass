from typing import Literal

from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep
from app.ingestion import calendar as calendar_sync
from app.ingestion import news as news_sync
from app.schemas.feeds import CalendarFeedCreate, FeedRead, FeedsRead, NewsFeedCreate
from app.services import feeds, integrations

router = APIRouter(prefix="/feeds", tags=["feeds"])

Kind = Literal["calendar", "news"]


def _check_free(session, kind: str, name: str) -> None:
    if not feeds.is_free(session, kind, name):
        raise HTTPException(status.HTTP_409_CONFLICT, f'there is already a feed called "{name}"')


def _unusable(session, exc: Exception, url: str) -> HTTPException:
    """The link did not work. Nothing is saved, and the secret in the URL stays out of the text."""
    session.rollback()
    # A ValueError is ours or the parser's, which quotes the page: its text stays out of the reply.
    error = "no feed found at this link" if isinstance(exc, ValueError) else None
    error = error or integrations.describe_error(exc).replace(url, "<url>")
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"cannot read the feed: {error}")


@router.get("", response_model=FeedsRead)
def list_feeds(session: SessionDep):
    return feeds.overview(session)


@router.post("/calendar", response_model=FeedRead, status_code=status.HTTP_201_CREATED)
def add_calendar(body: CalendarFeedCreate, session: SessionDep):
    """Save a calendar and fetch it right away, so a wrong link shows up here and not in a log."""
    _check_free(session, feeds.CALENDAR, body.name)
    try:
        data = calendar_sync.fetch_ics(body.url)
        feed = feeds.add(
            session,
            feeds.CALENDAR,
            body.name,
            body.url,
            deadline_pattern=body.deadline_pattern,
            area=body.area,
        )
        stats = calendar_sync.sync_feed(session, body.name, data)
    except Exception as exc:  # whatever a bad link causes, the user gets the reason
        raise _unusable(session, exc, body.url) from None
    integrations.record_success(session, f"{feeds.CALENDAR}:{body.name}", stats)
    session.commit()
    return next(f for f in feeds.overview(session).calendars if f.name == feed.name)


@router.post("/news", response_model=FeedRead, status_code=status.HTTP_201_CREATED)
def add_news(body: NewsFeedCreate, session: SessionDep):
    """Save a news feed and fetch it right away, like a calendar."""
    _check_free(session, feeds.NEWS, body.name)
    try:
        items = news_sync.parse_feed(news_sync.fetch_feed(body.url))
        if not items:
            raise ValueError("no entries")
        feed = feeds.add(session, feeds.NEWS, body.name, body.url, stream=body.stream)
        stats = news_sync.store(session, body.stream, body.name, items)
    except Exception as exc:  # whatever a bad link causes, the user gets the reason
        raise _unusable(session, exc, body.url) from None
    integrations.record_success(
        session, f"{feeds.NEWS}:{body.name}", {**stats, "stream": body.stream}
    )
    session.commit()
    return next(f for f in feeds.overview(session).news if f.name == feed.name)


@router.delete("/{kind}/{name}", status_code=status.HTTP_204_NO_CONTENT)
def remove_feed(kind: Kind, name: str, session: SessionDep) -> None:
    """Delete a feed of the app with its events or items, or hide one from .env."""
    if not feeds.remove(session, kind, name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such feed")
    session.commit()


@router.post("/{kind}/{name}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_feed(kind: Kind, name: str, session: SessionDep) -> None:
    if not feeds.restore(session, kind, name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such hidden feed")
    session.commit()
