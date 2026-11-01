from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, column_property, mapped_column

from app.config import get_settings
from app.models.base import Base, TimestampMixin
from app.models.feeds import Feed


class CalendarEvent(TimestampMixin, Base):
    """Read-only mirror of events from ICS feeds. One row per occurrence of a recurring event."""

    __tablename__ = "calendar_events"
    __table_args__ = (
        UniqueConstraint("feed", "uid", "starts_at"),
        Index("ix_calendar_events_starts_at", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    feed: Mapped[str] = mapped_column(String(40))
    uid: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(500))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # All-day events start at local midnight; ends_at is then the exclusive end day.
    all_day: Mapped[bool] = mapped_column(default=False)
    raw: Mapped[str] = mapped_column(Text)
    # The area of a calendar added in the app. Loaded with the event: lists have hundreds of them.
    feed_area: Mapped[str | None] = column_property(
        select(Feed.area)
        .where(Feed.kind == "calendar", Feed.name == feed)
        .correlate_except(Feed)
        .scalar_subquery()
    )

    @property
    def area_slug(self) -> str | None:
        """The area of its calendar, e.g. study for a university timetable."""
        return get_settings().calendar_area_map.get(self.feed) or self.feed_area
