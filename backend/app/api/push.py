from fastapi import APIRouter, Header, HTTPException, status

from app.api.deps import SessionDep
from app.config import get_settings
from app.models.push import PushSubscription
from app.schemas.push import (
    PushConfigRead,
    PushEndpoint,
    PushSubscribe,
    PushSubscriptionRead,
    PushTestRead,
    PushTopics,
)
from app.services import push

router = APIRouter(prefix="/push", tags=["push"])


def _read(sub: PushSubscription) -> PushSubscriptionRead:
    return PushSubscriptionRead(
        endpoint=sub.endpoint,
        topics=sub.topics,
        created_at=sub.created_at,
        last_sent_at=sub.last_sent_at,
    )


def _find(session: SessionDep, endpoint: str) -> PushSubscription:
    sub = push.find(session, endpoint)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this device is not subscribed")
    return sub


@router.get("/config", response_model=PushConfigRead)
def config():
    settings = get_settings()
    return PushConfigRead(
        enabled=push.enabled(),
        public_key=settings.vapid_public_key.strip() or None,
        topics=list(push.TOPICS),
        quiet_start=settings.push_quiet_start,
        quiet_end=settings.push_quiet_end,
    )


@router.post("/subscriptions", response_model=PushSubscriptionRead)
def subscribe(
    data: PushSubscribe, session: SessionDep, user_agent: str | None = Header(default=None)
):
    """Register this browser (again); without topics a new device gets all of them."""
    if not push.enabled():
        raise HTTPException(status.HTTP_409_CONFLICT, "push is not set up on the server")
    try:
        sub = push.subscribe(
            session, data.endpoint, data.keys.p256dh, data.keys.auth, data.topics, user_agent
        )
    except push.PushError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _read(sub)


@router.post("/subscriptions/lookup", response_model=PushSubscriptionRead)
def lookup(data: PushEndpoint, session: SessionDep):
    """The stored settings of this browser (the endpoint is too long for a URL)."""
    return _read(_find(session, data.endpoint))


@router.post("/subscriptions/topics", response_model=PushSubscriptionRead)
def set_topics(data: PushTopics, session: SessionDep):
    sub = _find(session, data.endpoint)
    try:
        sub.topics = push.check_topics(data.topics)
    except push.PushError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _read(sub)


@router.post("/subscriptions/remove", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(data: PushEndpoint, session: SessionDep):
    push.unsubscribe(session, data.endpoint)
    session.commit()


@router.post("/test", response_model=PushTestRead)
def test(data: PushEndpoint, session: SessionDep):
    """Send a test notification to this browser only."""
    sub = _find(session, data.endpoint)
    sent = push.deliver(
        session,
        [sub],
        push.Message(
            title="Compass",
            body="Benachrichtigungen funktionieren.",
            url="/einstellungen",
            tag="test",
            ttl=600,
        ),
    )
    session.commit()
    return PushTestRead(sent=sent == 1)
