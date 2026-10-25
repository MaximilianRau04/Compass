from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PushSubscription(TimestampMixin, Base):
    """A browser that receives push notifications (usually the PWA on the phone).

    topics: what this device wants, see app.services.push.TOPICS."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    topics: Mapped[list[str]] = mapped_column(ARRAY(String(30)), server_default="{}")
    user_agent: Mapped[str | None] = mapped_column(String(300))
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failures: Mapped[int] = mapped_column(Integer, default=0)


class PushSent(Base):
    """Every notification sent, by a key like "deadline:12:2026-10-25", so each goes out once."""

    __tablename__ = "push_sent"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    topic: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(200))
    devices: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
