from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.tasks import Area

# German and English stemming ("Abgaben" finds "Abgabe", "running" finds "run"), plus the plain
# words so names match as written. Title words weigh more than body words.
SEARCH_VECTOR = (
    "setweight(to_tsvector('german', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('german', coalesce(body, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(body, '')), 'B') || "
    "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(body, ''))"
)


class Note(TimestampMixin, Base):
    """A Markdown note: knowledge, ideas, links, context about the user. There is no delete;
    archiving hides a note. Notes tagged "context" or "kontext" describe the user (profile,
    writing style) and are what the assistant reads before writing in the user's name."""

    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_search", "search", postgresql_using="gin"),
        Index(
            "uq_notes_source_external_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id", ondelete="SET NULL"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(60)), server_default="{}")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | claude | share
    external_id: Mapped[str | None] = mapped_column(String(300))
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    search: Mapped[str] = mapped_column(TSVECTOR, Computed(SEARCH_VECTOR, persisted=True))

    area: Mapped[Area | None] = relationship(lazy="joined")
