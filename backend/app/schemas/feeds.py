import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

NAME = r"^[a-z0-9_-]{1,40}$"


class FeedCreate(BaseModel):
    name: str = Field(pattern=NAME)
    url: str = Field(min_length=1, max_length=2000)

    @field_validator("url")
    @classmethod
    def web_url(cls, value: str) -> str:
        value = value.strip()
        # The sync fetches this URL, so a file:// link must not get that far.
        if not re.fullmatch(r"(https?|webcal)://\S+", value, re.IGNORECASE):
            raise ValueError("the link must start with https://, http:// or webcal://")
        return value


class CalendarFeedCreate(FeedCreate):
    deadline_pattern: str | None = Field(None, max_length=500)
    area: str | None = Field(None, max_length=40)

    @field_validator("deadline_pattern")
    @classmethod
    def valid_pattern(cls, value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        try:
            re.compile(value)
        except re.error:
            raise ValueError("the deadline pattern is not a regular expression") from None
        return value


class NewsFeedCreate(FeedCreate):
    stream: Literal["general", "personal"] = "personal"


class FeedRead(BaseModel):
    name: str
    host: str | None
    origin: Literal["env", "app"]
    hidden: bool = False
    stream: str | None = None
    area: str | None = None
    deadline_pattern: str | None = None


class FeedsRead(BaseModel):
    calendars: list[FeedRead]
    news: list[FeedRead]
    config_error: str | None = None
