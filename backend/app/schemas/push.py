from datetime import datetime

from pydantic import BaseModel, Field


class PushConfigRead(BaseModel):
    enabled: bool = Field(description="False until VAPID keys are set on the server")
    public_key: str | None
    topics: list[str]
    quiet_start: int = Field(description="Hour from which only the bedtime reminder comes")
    quiet_end: int


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class PushSubscribe(BaseModel):
    """What PushSubscription.toJSON() gives in the browser, plus the wanted topics."""

    endpoint: str = Field(min_length=10, max_length=2000)
    keys: PushKeys
    topics: list[str] | None = None


class PushEndpoint(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)


class PushTopics(PushEndpoint):
    topics: list[str]


class PushSubscriptionRead(BaseModel):
    endpoint: str
    topics: list[str]
    created_at: datetime
    last_sent_at: datetime | None


class PushTestRead(BaseModel):
    sent: bool
