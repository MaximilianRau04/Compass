from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import SessionDep
from app.schemas.correlations import CorrelationPoint, CorrelationRead
from app.services import correlations

router = APIRouter(prefix="/correlations", tags=["correlations"])


def read(c: correlations.Correlation, points: bool) -> CorrelationRead:
    return CorrelationRead(
        x=c.x,
        y=c.y,
        lag=c.lag,
        n=c.n,
        r=c.r,
        points=[CorrelationPoint(date=d, x=x, y=y) for d, x, y in c.points] if points else [],
    )


@router.get("", response_model=list[CorrelationRead])
def overview(session: SessionDep, days: Annotated[int, Query(ge=14, le=365)] = 90):
    """The preset pairs, strongest first, without their points."""
    return [read(c, False) for c in correlations.overview(session, days)]


@router.get("/pair", response_model=CorrelationRead)
def pair(
    session: SessionDep,
    x: str,
    y: str,
    lag: Annotated[int, Query(ge=0, le=7)] = 0,
    days: Annotated[int, Query(ge=14, le=365)] = 90,
):
    """One pair with every day it rests on."""
    try:
        c = correlations.correlate(correlations.rows_for(session, days), x, y, lag)
    except correlations.CorrelationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return read(c, True)
