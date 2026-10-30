from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Email(TimestampMixin, Base):
    """Metadata of one mail plus its triage. The text itself is never stored: it is read from
    IMAP, summarised and dropped (for local accounts outside the server, see app.mail.local_triage).

    Sender, subject and summary come from outside and may contain anything; whatever passes them
    on (API, MCP) treats them as data, never as instructions."""

    __tablename__ = "emails"
    __table_args__ = (
        UniqueConstraint("account", "msg_key"),
        Index("ix_emails_account_received_at", "account", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account: Mapped[str] = mapped_column(String(20))  # a name from MAIL_ACCOUNTS
    # Message-ID, or folder/uidvalidity/uid for mails without one; keeps a sync from duplicating.
    msg_key: Mapped[str] = mapped_column(String(500))
    folder: Mapped[str] = mapped_column(String(200))
    uidvalidity: Mapped[int] = mapped_column(Integer)
    uid: Mapped[int] = mapped_column(Integer)
    from_name: Mapped[str | None] = mapped_column(String(300))
    from_addr: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(500))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # \\Seen flag in the mailbox, refreshed on every sync while the mail is recent.
    seen: Mapped[bool] = mapped_column(Boolean, default=False)
    # Mailing list or bulk mail (List-Id, List-Unsubscribe, Precedence: bulk).
    bulk: Mapped[bool] = mapped_column(Boolean, default=False)

    priority: Mapped[str] = mapped_column(String(10), default="normal")  # high | normal | low
    needs_action: Mapped[bool | None] = mapped_column(Boolean)
    category: Mapped[str | None] = mapped_column(String(30))
    summary: Mapped[str | None] = mapped_column(Text)
    task_title: Mapped[str | None] = mapped_column(String(300))
    # Who triaged it: rules, claude, local; "pending" while a model summary is still due.
    triage: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    triage_error: Mapped[str | None] = mapped_column(String(500))

    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    # Hidden from the triage list by the user; the mailbox itself is never touched.
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
