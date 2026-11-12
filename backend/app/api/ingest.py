"""Endpoints for machines: the health bridges on the phone (the Android and iOS apps, Health Auto
Export) and the local mail triage on the laptop. Not behind the basic auth (none can do the browser
login); each needs its own bearer token instead (HEALTH_TOKEN, MAIL_TRIAGE_TOKEN)."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.deps import SessionDep
from app.config import get_settings
from app.ingestion import health_auto_export, healthconnect
from app.mail.triage import TriageResult, sanitize
from app.models.integrations import IntegrationState
from app.schemas.health import AutoExportResult, IngestPayload, IngestResult, IngestStatus
from app.schemas.mail import PendingMail, TriageUpload, TriageUploadResult
from app.services import mail as mail_service

router = APIRouter(prefix="/ingest", tags=["ingest"])


def bearer_token(setting: str, variable: str | None = None):
    """Dependency that checks the bearer token against the named setting; `variable` is its name
    in .env for the error message."""

    def check(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = getattr(get_settings(), setting)
        if not expected:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, f"{variable or setting.upper()} is not set"
            )
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), expected.encode()):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return Depends(check)


Authorized = bearer_token("ingest_health_token", "HEALTH_TOKEN")
MailTriageAuthorized = bearer_token("mail_triage_token")


# /healthconnect is the path before the iOS bridge; the installed Android apps still use it.
@router.get("/health", response_model=IngestStatus, dependencies=[Authorized])
@router.get(
    "/healthconnect",
    response_model=IngestStatus,
    dependencies=[Authorized],
    include_in_schema=False,
)
def health_status(session: SessionDep):
    """Connection test for the app: token valid, plus the last sync as the server saw it."""
    state = session.get(IntegrationState, "healthconnect")
    return IngestStatus(
        ok=True,
        last_success_at=state.last_success_at if state else None,
        last_error=state.last_error if state else None,
    )


async def _read_json(request: Request, model):
    """The body as `model`, at most healthconnect.MAX_BYTES; 413 or 422 otherwise."""
    if int(request.headers.get("content-length") or 0) > healthconnect.MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "batch is larger than 20 MB")
    body = await request.body()
    if len(body) > healthconnect.MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "batch is larger than 20 MB")
    try:
        return model.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            exc.errors(include_url=False, include_context=False, include_input=False)[:20],
        ) from exc


@router.post("/health", response_model=IngestResult, dependencies=[Authorized])
@router.post(
    "/healthconnect",
    response_model=IngestResult,
    dependencies=[Authorized],
    include_in_schema=False,
)
async def ingest_health(request: Request, session: SessionDep):
    """Records of the bridge apps (Health Connect on Android, HealthKit on iOS)."""
    payload = await _read_json(request, IngestPayload)

    def run() -> dict:
        result = healthconnect.ingest(session, payload)
        session.commit()
        return result

    return await run_in_threadpool(run)


@router.post("/health-auto-export", response_model=AutoExportResult, dependencies=[Authorized])
async def ingest_health_auto_export(request: Request, session: SessionDep):
    """The JSON of the iOS app Health Auto Export (REST API automation, health metrics or
    workouts); see app.ingestion.health_auto_export."""
    export = await _read_json(request, health_auto_export.Export)
    device = request.headers.get("automation-name")
    device = f"{health_auto_export.SOURCE}: {device}"[:120] if device else None

    def run() -> dict:
        converted = health_auto_export.convert(session, export)
        totals: dict = {}
        for payload in health_auto_export.batches(converted, device):
            for key, value in healthconnect.ingest(session, payload).items():
                totals[key] = totals.get(key, 0) + value
        session.commit()
        return {**totals, "skipped": converted.skipped, "unknown": sorted(converted.unknown)}

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
