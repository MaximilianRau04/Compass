from contextlib import nullcontext
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import SessionDep
from app.config import MailAccount, get_settings
from app.ingestion import mail as mail_sync
from app.mail.microsoft import SignInError
from app.models.mail import Email
from app.schemas.mail import (
    MailAccountRead,
    MailDismiss,
    MailOverview,
    MailRead,
    SignInPoll,
    SignInStart,
)
from app.schemas.tasks import TaskRead
from app.services import mail as mail_service
from app.services import mail_auth
from app.services.mail import MailError

router = APIRouter(prefix="/mail", tags=["mail"])


def read(e: Email) -> MailRead:
    return MailRead(
        id=e.id,
        account=e.account,
        from_name=e.from_name,
        from_addr=e.from_addr,
        subject=e.subject,
        received_at=e.received_at,
        seen=e.seen,
        bulk=e.bulk,
        priority=e.priority,
        needs_action=e.needs_action,
        category=e.category,
        summary=e.summary,
        task_title=e.task_title,
        triage=e.triage,
        # A discarded task no longer counts: the mail can become a task again.
        task_id=e.task_id if e.task is not None and e.task.status != "cancelled" else None,
        dismissed=e.dismissed_at is not None,
    )


def _get(session, mail_id: int) -> Email:
    try:
        return mail_service.get_mail(session, mail_id)
    except MailError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("", response_model=list[MailRead])
def list_mails(
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=365)] = 14,
    account: str | None = None,
    important: bool = False,
    dismissed: bool = False,
):
    return [read(e) for e in mail_service.list_mails(session, days, account, important, dismissed)]


@router.get("/overview", response_model=MailOverview)
def overview(session: SessionDep):
    important = mail_service.list_mails(session, important=True)
    return MailOverview(
        accounts=[MailAccountRead(**a.__dict__) for a in mail_service.accounts(session)],
        important=len(important),
        unread_important=sum(1 for e in important if not e.seen),
        top=[read(e) for e in important[:3]],
    )


@router.post("/sync")
def sync(session: SessionDep) -> dict[str, dict | str]:
    """Fetch new mails of every account now (the worker does this every MAIL_SYNC_MINUTES)."""
    return mail_sync.sync_all(lambda: nullcontext(session))


def _signin_account(name: str) -> MailAccount:
    try:
        accounts = get_settings().mail_accounts
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    account = accounts.get(name)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown mail account")
    if account.auth == "password":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name} signs in with a password")
    return account


@router.post("/accounts/{name}/signin", response_model=SignInStart)
def start_signin(name: str, session: SessionDep):
    """Start a Microsoft sign-in: the user enters the code at the address, then the app polls."""
    account = _signin_account(name)
    try:
        pending = mail_auth.start(session, account)
    except SignInError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    session.commit()
    return SignInStart(**pending.__dict__)


@router.post("/accounts/{name}/signin/poll", response_model=SignInPoll)
def poll_signin(name: str, session: SessionDep):
    result = mail_auth.poll(session, _signin_account(name))
    session.commit()
    return SignInPoll(**result.__dict__)


@router.delete("/accounts/{name}/signin", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(name: str, session: SessionDep):
    """Forget the tokens of this account. Its mails stay in Compass."""
    _signin_account(name)
    mail_auth.sign_out(session, name)
    session.commit()


@router.get("/{mail_id}", response_model=MailRead)
def get_mail(mail_id: int, session: SessionDep):
    """One mail, whatever its age: the search links to mails the list no longer shows."""
    return read(_get(session, mail_id))


@router.post("/{mail_id}/task", response_model=TaskRead)
def to_task(mail_id: int, session: SessionDep):
    task = mail_service.create_task(session, _get(session, mail_id))
    session.commit()
    return task


@router.post("/{mail_id}/dismiss", response_model=MailRead)
def dismiss(mail_id: int, data: MailDismiss, session: SessionDep):
    e = _get(session, mail_id)
    mail_service.set_dismissed(e, data.dismissed)
    session.commit()
    return read(e)
