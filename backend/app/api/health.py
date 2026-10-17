from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response, session: Annotated[Session, Depends(get_session)]) -> dict:
    try:
        session.execute(text("SELECT 1"))
        db = "ok"
    except SQLAlchemyError:
        db = "unreachable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if db == "ok" else "degraded", "database": db}
