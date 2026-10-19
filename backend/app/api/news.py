from contextlib import nullcontext
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.ingestion import news as news_sync
from app.models.integrations import IntegrationState
from app.models.news import Brief
from app.schemas.news import (
    BriefRead,
    FeedStatus,
    InterestRead,
    InterestsRead,
    InterestsUpdate,
    NewsFeedback,
    NewsItemRead,
    NewsOverview,
    TrendRead,
)
from app.services import briefs
from app.services import news as news_service
from app.services.clock import local_today

router = APIRouter(tags=["news"])

Stream = Literal["general", "personal"]


def read(s: news_service.Scored) -> NewsItemRead:
    i = s.item
    return NewsItemRead(
        id=i.id,
        feed=i.feed,
        stream=i.stream,
        url=i.url,
        title=i.title,
        summary=i.summary,
        published_at=i.published_at,
        feedback=i.feedback,
        score=s.score,
        topics=s.topics,
        trending=s.trending,
    )


def brief_read(b: Brief) -> BriefRead:
    return BriefRead.model_validate(b, from_attributes=True)


def _interests(session) -> InterestsRead:
    likes, dislikes = news_service.learned_interests(session)

    def out(rows):
        return [InterestRead(term=r.term, weight=r.weight) for r in rows]

    return InterestsRead(
        topics=out(news_service.manual_interests(session)), likes=out(likes), dislikes=out(dislikes)
    )


@router.get("/news", response_model=list[NewsItemRead])
def list_news(
    session: SessionDep,
    hours: Annotated[int, Query(ge=1, le=24 * 30)] = 36,
    stream: Stream | None = None,
):
    return [read(s) for s in news_service.ranked(session, hours, stream)]


@router.get("/news/overview", response_model=NewsOverview)
def overview(session: SessionDep):
    states = session.scalars(
        select(IntegrationState)
        .where(IntegrationState.name.like("news:%"))
        .order_by(IntegrationState.name)
    )
    report = briefs.latest(session, "news", since=local_today() - timedelta(days=6))
    return NewsOverview(
        feeds=[
            FeedStatus(
                feed=s.name.removeprefix("news:"),
                stream=(s.stats or {}).get("stream"),
                last_success_at=s.last_success_at,
                last_error=s.last_error,
                items=(s.stats or {}).get("items"),
            )
            for s in states
        ],
        trends=[TrendRead(**t.__dict__) for t in news_service.trends(session)],
        top=[
            read(s)
            for s in news_service.ranked(session, stream="personal", include_disliked=False)[:3]
        ],
        report=brief_read(report) if report else None,
    )


@router.post("/news/sync")
def sync(session: SessionDep) -> dict[str, dict | str]:
    """Fetch every feed now (the worker does this every NEWS_SYNC_MINUTES)."""
    return news_sync.sync_all(lambda: nullcontext(session))


@router.post("/news/{item_id}/feedback", response_model=NewsItemRead)
def feedback(item_id: int, data: NewsFeedback, session: SessionDep):
    try:
        item = news_service.get_item(session, item_id)
        news_service.set_feedback(session, item, data.value)
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(exc) else 422
        raise HTTPException(code, str(exc)) from exc
    session.commit()
    profile = news_service.load_profile(session)
    hot = {t.term for t in news_service.trends(session)}
    return read(news_service.score(item, profile, hot))


@router.get("/news/interests", response_model=InterestsRead)
def interests(session: SessionDep):
    return _interests(session)


@router.put("/news/interests", response_model=InterestsRead)
def update_interests(data: InterestsUpdate, session: SessionDep):
    try:
        news_service.replace_manual(session, {t.term: t.weight for t in data.topics})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _interests(session)


@router.delete("/news/interests/learned", status_code=status.HTTP_204_NO_CONTENT)
def reset_learned(session: SessionDep):
    """Forget what the thumbs taught; the thumbs on the items stay."""
    news_service.reset_learned(session)
    session.commit()


@router.get("/briefs", response_model=list[BriefRead])
def list_briefs(
    session: SessionDep,
    kind: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
):
    return [brief_read(b) for b in briefs.recent(session, kind, limit)]


@router.get("/briefs/today", response_model=BriefRead | None)
def today_brief(session: SessionDep):
    """Today's daily brief, if a routine (or Claude in a chat) saved one."""
    brief = briefs.latest(session, "daily", since=local_today())
    return brief_read(brief) if brief else None
