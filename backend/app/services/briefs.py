"""Texts Claude writes for a day: the daily brief, the news report, other routines' output.

Claude saves them with the MCP tool save_brief, usually from a scheduled routine. One text per
kind and day; saving again replaces it. The body is a small subset of Markdown (headings,
lists, bold, links) that the web app renders as text, never as HTML.
"""

import re
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.news import Brief
from app.services.clock import local_today

KIND = re.compile(r"[a-z0-9][a-z0-9-]{0,29}")
MAX_BODY = 12_000


class BriefError(ValueError):
    pass


def check_kind(kind: str) -> str:
    kind = kind.strip().lower()
    if not KIND.fullmatch(kind):
        raise BriefError("kind: lowercase letters, digits and dashes, e.g. daily, news, weekly")
    return kind


def save(
    session: Session,
    kind: str,
    body: str,
    title: str | None = None,
    day: date | None = None,
    actor: str = "claude",
) -> Brief:
    kind = check_kind(kind)
    body = body.replace("\r\n", "\n").strip()
    if not body:
        raise BriefError("body is empty")
    if len(body) > MAX_BODY:
        raise BriefError(f"body is longer than {MAX_BODY} characters")
    day = day or local_today()
    title = " ".join((title or "").split())[:200] or None
    brief = session.scalar(select(Brief).where(Brief.kind == kind, Brief.local_date == day))
    if brief is None:
        brief = Brief(kind=kind, local_date=day, body=body, title=title, actor=actor)
        session.add(brief)
    else:
        brief.body, brief.title, brief.actor = body, title, actor
    session.flush()
    return brief


def latest(session: Session, kind: str, since: date | None = None) -> Brief | None:
    stmt = select(Brief).where(Brief.kind == kind)
    if since:
        stmt = stmt.where(Brief.local_date >= since)
    return session.scalar(stmt.order_by(Brief.local_date.desc()).limit(1))


def recent(session: Session, kind: str | None = None, limit: int = 30) -> list[Brief]:
    stmt = select(Brief)
    if kind:
        stmt = stmt.where(Brief.kind == kind)
    return list(session.scalars(stmt.order_by(Brief.local_date.desc(), Brief.kind).limit(limit)))


def kinds(session: Session) -> dict[str, date]:
    """Every kind with the day of its newest text."""
    rows = session.execute(select(Brief.kind, func.max(Brief.local_date)).group_by(Brief.kind))
    return dict(rows.all())
