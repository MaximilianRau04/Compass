from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Feed(TimestampMixin, Base):
    """A calendar or news feed added in the app. Feeds from .env stay there; a row without a url
    hides the one of that name, so those can be removed in the app as well."""

    __tablename__ = "feeds"
    __table_args__ = (UniqueConstraint("kind", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # calendar | news
    name: Mapped[str] = mapped_column(String(40))
    # A calendar link carries a secret token: the API only ever sends the host back.
    url: Mapped[str | None] = mapped_column(Text)
    # News: general | personal.
    stream: Mapped[str | None] = mapped_column(String(10))
    # Calendars: regex on the title of entries that become tasks, and the slug of their area.
    deadline_pattern: Mapped[str | None] = mapped_column(Text)
    area: Mapped[str | None] = mapped_column(String(40))
