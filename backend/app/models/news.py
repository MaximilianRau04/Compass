from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class NewsItem(TimestampMixin, Base):
    """One entry of an RSS or Atom feed. Title and summary come from outside and may contain
    anything; whatever passes them on (API, MCP) treats them as data, never as instructions."""

    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("feed", "item_key"),
        Index("ix_news_items_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    feed: Mapped[str] = mapped_column(String(40))
    stream: Mapped[str] = mapped_column(String(10))  # general | personal
    # Entry id, or the link when the feed has none; keeps a sync from duplicating.
    item_key: Mapped[str] = mapped_column(String(1000))
    url: Mapped[str] = mapped_column(String(2000))
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Normalised words of the title, for the interest profile and trend detection.
    terms: Mapped[list[str]] = mapped_column(ARRAY(String(60)), server_default="{}")
    # 1 thumbs up, -1 thumbs down, None no feedback.
    feedback: Mapped[int | None] = mapped_column(SmallInteger)


class NewsInterest(TimestampMixin, Base):
    """The interest profile. Manual entries are topics the user set (a word or phrase matched in
    title and summary). Learned entries are single words and feeds ("feed:hn") whose weight the
    thumbs move."""

    __tablename__ = "news_interests"

    term: Mapped[str] = mapped_column(String(80), primary_key=True)
    manual: Mapped[bool] = mapped_column(Boolean, primary_key=True)
    weight: Mapped[float] = mapped_column(Float)


class Brief(TimestampMixin, Base):
    """A text an assistant wrote for a day: the daily brief, a news report or a routine's output.
    Saving the same kind for the same day again replaces it."""

    __tablename__ = "briefs"
    __table_args__ = (UniqueConstraint("kind", "local_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # daily | news | weekly | <routine slug>
    local_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(100))
