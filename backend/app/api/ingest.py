"""Endpoints for the phone. Not behind the basic auth (an app cannot do the browser login);
they need the bearer token from HEALTHCONNECT_TOKEN instead."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.deps import SessionDep
from app.config import get_settings
from app.ingestion import healthconnect
from app.models.integrations import IntegrationState
from app.schemas.health import IngestPayload, IngestResult, IngestStatus

router = APIRouter(prefix="/ingest", tags=["ingest"])


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().healthconnect_token
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "HEALTHCONNECT_TOKEN is not set")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid token", headers={"WWW-Authenticate": "Bearer"}
        )


Authorized = Depends(require_token)


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
