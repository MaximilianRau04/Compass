"""Endpoints for machines: the Health Connect bridge on the phone and the local mail triage on
the laptop. Not behind the basic auth (neither can do the browser login); each needs its own
bearer token instead (HEALTHCONNECT_TOKEN, MAIL_TRIAGE_TOKEN)."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.deps import SessionDep
from app.config import get_settings
from app.ingestion import healthconnect
from app.mail.triage import TriageResult, sanitize
from app.models.integrations import IntegrationState
from app.schemas.health import IngestPayload, IngestResult, IngestStatus
from app.schemas.mail import PendingMail, TriageUpload, TriageUploadResult
from app.services import mail as mail_service

router = APIRouter(prefix="/ingest", tags=["ingest"])


def bearer_token(setting: str):
    """Dependency that checks the bearer token against the named setting."""

    def check(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = getattr(get_settings(), setting)
        if not expected:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, f"{setting.upper()} is not set"
            )
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), expected.encode()):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return Depends(check)


Authorized = bearer_token("healthconnect_token")
MailTriageAuthorized = bearer_token("mail_triage_token")


@router.get("/healthconnect", response_model=IngestStatus, dependencies=[Authorized])
def healthconnect_status(session: SessionDep):
    """Connection test for the app: token valid, plus the last sync as the server saw it."""
    state = session.get(IntegrationState, "healthconnect")
    return IngestStatus(
        ok=True,
        last_success_at=state.last_success_at if state else None,
        last_error=state.last_error if state else None,
    )


@router.post("/healthconnect", response_model=IngestResult, dependencies=[Authorized])
async def ingest_healthconnect(request: Request, session: SessionDep):
    if int(request.headers.get("content-length") or 0) > healthconnect.MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "batch is larger than 20 MB")
    body = await request.body()
    if len(body) > healthconnect.MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "batch is larger than 20 MB")
    try:
        payload = IngestPayload.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            exc.errors(include_url=False, include_context=False, include_input=False)[:20],
        ) from exc

    def run() -> dict:
        result = healthconnect.ingest(session, payload)
        session.commit()
        return result

    return await run_in_threadpool(run)


# --- Local mail triage (laptop) ------------------------------------------------------------------


def _local_accounts() -> list[str]:
    return [name for name, a in get_settings().mail_accounts.items() if a.triage == "local"]


@router.get("/mail/pending", response_model=list[PendingMail], dependencies=[MailTriageAuthorized])
def mail_pending(session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 25):
    """Mails of accounts with local triage that still need a summary. Only where to find them in
    the mailbox (folder, UIDVALIDITY, UID) plus sender and subject; the laptop reads the text."""
    return [
        PendingMail(
            id=e.id,
            account=e.account,
            folder=e.folder,
            uidvalidity=e.uidvalidity,
            uid=e.uid,
            sender=mail_service.sender(e),
            subject=e.subject,
            received_at=e.received_at,
        )
        for e in mail_service.pending_local(session, _local_accounts(), limit)
    ]


@router.post("/mail/triage", response_model=TriageUploadResult, dependencies=[MailTriageAuthorized])
def mail_triage(data: TriageUpload, session: SessionDep):
    result = mail_service.apply_local(
        session,
        # Cleaned again here: the laptop is trusted, its model output is not.
        {r.id: sanitize(TriageResult(**r.model_dump(exclude={"id"}))) for r in data.results},
        {f.id: f.error for f in data.failed},
        _local_accounts(),
    )
    session.commit()
    return result
