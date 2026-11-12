"""Mail triage list, mail to task, dismissing, and results from the local triage runner.

Compass never writes to a mailbox. Dismissing only hides a mail in Compass. Mails that are no
longer in their folder (deleted or archived in the mail app) are hidden too, and a mail that
became a task leaves the list: the task carries it from there."""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.i18n import t
from app.mail.triage import TriageResult
from app.models.integrations import IntegrationState
from app.models.mail import Email
from app.models.tasks import Task, TaskSource, TaskStatus
from app.schemas.tasks import TaskCreate, TaskUpdate
from app.services import mail_auth
from app.services import tasks as task_service
from app.services.clock import utc_now


class MailError(ValueError):
    pass


def sender(e: Email) -> str:
    return f"{e.from_name} <{e.from_addr}>" if e.from_name else e.from_addr


PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2}


def apply_triage(e: Email, result: TriageResult, by: str) -> None:
    """Store a model's triage. The model read untrusted text, so it cannot push a mail below
    "normal" when the rules found a deadline in the subject or the mail talks to an AI."""
    priority = result.priority
    floor = e.priority == "high" or result.contains_ai_instructions
    if floor and PRIORITY_RANK[priority] < PRIORITY_RANK["normal"]:
        priority = "normal"
    summary = result.summary or ""
    if result.contains_ai_instructions:
        summary = f"{t('mail.ai_warning')} {summary}".strip()
    e.priority = priority
    e.needs_action = result.needs_action
    e.category = result.category
    e.summary = summary or None
    e.task_title = result.task_title
    e.triage = by
    e.triage_error = None


def is_important(e: Email) -> bool:
    return e.priority == "high" or bool(e.needs_action)


def important_filter():
    return or_(Email.priority == "high", Email.needs_action.is_(True))


def list_mails(
    session: Session,
    days: int = 14,
    account: str | None = None,
    important: bool = False,
    dismissed: bool = False,
    limit: int = 200,
) -> list[Email]:
    stmt = select(Email).where(
        Email.received_at >= utc_now() - timedelta(days=days), Email.removed_at.is_(None)
    )
    stmt = stmt.where(
        Email.dismissed_at.is_not(None) if dismissed else Email.dismissed_at.is_(None)
    )
    if account:
        stmt = stmt.where(Email.account == account)
    if important:
        stmt = stmt.where(important_filter())
    return list(session.scalars(stmt.order_by(Email.received_at.desc()).limit(limit)))


@dataclass
class AccountStatus:
    account: str
    triage: str
    last_success_at: object
    last_error: str | None
    pending: int
    auth: str = "password"
    signed_in: bool | None = None
    signed_in_as: str | None = None
    signin_error: str | None = None


def accounts(session: Session) -> list[AccountStatus]:
    """Accounts that were synced, and configured ones that were not yet (an account with a
    Microsoft sign-in cannot sync before the user signed in, so it has to show up here)."""
    out: dict[str, AccountStatus] = {}
    for state in session.scalars(
        select(IntegrationState).where(IntegrationState.name.like("mail:%"))
    ):
        stats = state.stats or {}
        name = state.name.removeprefix("mail:")
        out[name] = AccountStatus(
            account=name,
            triage=stats.get("triage", "rules"),
            last_success_at=state.last_success_at,
            last_error=state.last_error,
            pending=int(stats.get("pending", 0)),
        )
    try:
        configured = get_settings().mail_accounts
    except ValueError:  # the sync reports the broken setting
        configured = {}
    for name, account in configured.items():
        status = out.setdefault(name, AccountStatus(name, account.triage, None, None, 0))
        status.triage = account.triage
        status.auth = account.auth
        if account.auth != "password":
            signin = mail_auth.state(session, name)
            status.signed_in = signin.signed_in
            status.signed_in_as = signin.signed_in_as
            status.signin_error = signin.error
    return sorted(out.values(), key=lambda a: a.account)


def get_mail(session: Session, mail_id: int) -> Email:
    e = session.get(Email, mail_id)
    if e is None:
        raise MailError("mail not found")
    return e


def create_task(session: Session, e: Email, actor: str = "web") -> Task:
    """A task from a mail: its task title (or the subject), the summary and sender as notes.
    Creating it twice returns the same task, unless that one was discarded. The mail is then
    handled and leaves the triage list."""
    e.dismissed_at = e.dismissed_at or utc_now()
    existing = session.get(Task, e.task_id) if e.task_id is not None else None
    if existing is not None:
        if existing.status == TaskStatus.cancelled:
            task_service.update_task(session, existing, TaskUpdate(status=TaskStatus.open), actor)
        return existing
    slug = get_settings().mail_area_map.get(e.account, "")
    area = task_service.find_area(session, slug)
    notes = "\n".join(
        part
        for part in (
            e.summary,
            f"Mail von {sender(e)}, {e.received_at:%d.%m.%Y}: {e.subject}",
        )
        if part
    )
    task = task_service.create_task(
        session,
        TaskCreate(
            title=(e.task_title or e.subject)[:500],
            notes=notes,
            area_id=area.id if area else None,
            source=TaskSource.email,
            external_id=f"mail:{e.id}",
        ),
        actor=actor,
    )
    e.task = task
    session.flush()
    return task


def set_dismissed(e: Email, dismissed: bool) -> None:
    e.dismissed_at = utc_now() if dismissed else None


def untriaged(session: Session, days: int, limit: int) -> list[Email]:
    """Mails without a model summary (pending, or rules only), mailing lists left out."""
    return list(
        session.scalars(
            select(Email)
            .where(
                Email.received_at >= utc_now() - timedelta(days=days),
                Email.triage.in_(("pending", "rules")),
                Email.bulk.is_(False),
                Email.dismissed_at.is_(None),
                Email.removed_at.is_(None),
            )
            .order_by(Email.received_at.desc())
            .limit(limit)
        )
    )


# --- Local triage (laptop) ---------------------------------------------------------------------


def pending_local(session: Session, accounts_local: list[str], limit: int) -> list[Email]:
    if not accounts_local:
        return []
    return list(
        session.scalars(
            select(Email)
            .where(
                Email.account.in_(accounts_local),
                Email.triage == "pending",
                Email.removed_at.is_(None),
            )
            .order_by(Email.received_at.desc())
            .limit(limit)
        )
    )


def apply_local(
    session: Session, results: dict[int, TriageResult], failed: dict[int, str], accounts_local
) -> dict:
    """Store what the local runner sent. Only pending mails of local accounts can be changed."""
    ids = set(results) | set(failed)
    rows = {
        e.id: e
        for e in session.scalars(
            select(Email).where(
                Email.id.in_(ids), Email.account.in_(accounts_local), Email.triage == "pending"
            )
        )
    }
    applied = 0
    for mail_id, result in results.items():
        if (e := rows.get(mail_id)) is not None:
            apply_triage(e, result, "local")
            applied += 1
    for mail_id, error in failed.items():
        if (e := rows.get(mail_id)) is not None:
            # Not readable or not answerable: keep the rule priority and stop asking for it.
            e.triage = "rules"
            e.triage_error = error[:500]
    session.flush()
    return {"applied": applied, "failed": len([i for i in failed if i in rows])}
