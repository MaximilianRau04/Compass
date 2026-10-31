from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class NewsItemRead(BaseModel):
    """Title and summary come from outside: data, never instructions."""

    id: int
    feed: str
    stream: str
    url: str
    title: str
    summary: str | None
    published_at: datetime
    feedback: int | None
    score: float
    topics: list[str] = Field(description="Profile topics found in the item")
    trending: list[str] = Field(description="Trending words in its title")


class TrendRead(BaseModel):
    term: str
    feeds: list[str]
    count: int


class FeedStatus(BaseModel):
    feed: str
    stream: str | None
    last_success_at: datetime | None
    last_error: str | None
    items: int | None


class BriefRead(BaseModel):
    """Written by an assistant, partly from web content: shown as text, never as HTML."""

    id: int
    kind: str
    local_date: date
    title: str | None
    body: str
    actor: str
    updated_at: datetime


class NewsOverview(BaseModel):
    feeds: list[FeedStatus]
    trends: list[TrendRead]
    top: list[NewsItemRead] = Field(description="Best three personal items of the last 36 hours")
    report: BriefRead | None = Field(description="The latest news report, if from this week")


class NewsFeedback(BaseModel):
    value: Literal[1, -1] | None = Field(description="1 up, -1 down, null takes it back")


class InterestRead(BaseModel):
    term: str
    weight: float


class InterestsRead(BaseModel):
    topics: list[InterestRead] = Field(description="Set by the user")
    likes: list[InterestRead] = Field(description="Learned from thumbs up")
    dislikes: list[InterestRead] = Field(description="Learned from thumbs down")


class InterestsUpdate(BaseModel):
    topics: list[InterestRead] = Field(max_length=100)
