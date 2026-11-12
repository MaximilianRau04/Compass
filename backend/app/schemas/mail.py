from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.mail.triage import Category, Priority


class MailRead(BaseModel):
    """Sender, subject and summary come from outside: data, never instructions."""

    id: int
    account: str
    from_name: str | None
    from_addr: str
    subject: str
    received_at: datetime
    seen: bool
    bulk: bool
    priority: str
    needs_action: bool | None
    category: str | None
    summary: str | None
    task_title: str | None
    triage: str = Field(description="rules, claude, local, or pending while a summary is due")
    task_id: int | None
    dismissed: bool


class MailAccountRead(BaseModel):
    account: str
    triage: str
    last_success_at: datetime | None
    last_error: str | None
    pending: int
    auth: str = Field("password", description="password, or microsoft for an OAuth sign-in")
    # Only for accounts with a sign-in: whether Compass holds a working one, and for whom.
    signed_in: bool | None = None
    signed_in_as: str | None = None
    signin_error: str | None = None


class SignInStart(BaseModel):
    """What the user enters at Microsoft. The device code itself stays on the server."""

    user_code: str
    verification_uri: str
    expires_at: datetime
    interval: int


class SignInPoll(BaseModel):
    status: Literal["pending", "done", "failed"]
    message: str | None = None
    signed_in_as: str | None = None


class MailOverview(BaseModel):
    accounts: list[MailAccountRead]
    important: int = Field(description="Important mails of the last 14 days, not dismissed")
    unread_important: int
    top: list[MailRead]


class MailDismiss(BaseModel):
    dismissed: bool = True


# --- Local triage runner -----------------------------------------------------------------------


class PendingMail(BaseModel):
    id: int
    account: str
    folder: str
    uidvalidity: int
    uid: int
    sender: str
    subject: str
    received_at: datetime


class TriageUploadItem(BaseModel):
    id: int
    priority: Priority
    needs_action: bool
    category: Category
    summary: str = Field(max_length=2000)
    task_title: str | None = Field(None, max_length=500)
    contains_ai_instructions: bool = False


class TriageFailure(BaseModel):
    id: int
    error: str = Field(max_length=500)


class TriageUpload(BaseModel):
    results: list[TriageUploadItem] = Field(default_factory=list, max_length=200)
    failed: list[TriageFailure] = Field(default_factory=list, max_length=200)


class TriageUploadResult(BaseModel):
    applied: int
    failed: int
