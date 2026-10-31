from fastapi import APIRouter, status

from app.api.deps import SessionDep
from app.config import get_settings
from app.schemas.setup import SetupRead
from app.services import setup

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("", response_model=SetupRead)
def read_setup(session: SessionDep):
    settings = get_settings()
    return SetupRead(
        first_run=setup.first_run(session),
        timezone=settings.timezone,
        language=settings.language,
        sources=setup.sources(session),
    )


@router.post("/done", status_code=status.HTTP_204_NO_CONTENT)
def finish_setup(session: SessionDep) -> None:
    setup.finish(session)
    session.commit()
