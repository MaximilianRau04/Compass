"""The first start: whether Compass is still empty, and which data sources are configured.

The welcome page shows once, on an install without tasks and notes, until it is finished. Sources
are only reported as on or off, never with their values.
"""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.integrations import IntegrationState
from app.models.notes import Note
from app.models.tasks import Task
from app.services import integrations

STATE = "onboarding"


def first_run(session: Session) -> bool:
    if session.get(IntegrationState, STATE) is not None:
        return False
    return not (
        session.scalar(select(exists().where(Task.id.is_not(None))))
        or session.scalar(select(exists().where(Note.id.is_not(None))))
    )


def finish(session: Session) -> None:
    integrations.record_success(session, STATE, {})


def sources() -> dict[str, bool]:
    s = get_settings()
    try:
        mail = bool(s.mail_accounts)
    except ValueError:  # the mail tab reports a broken setting
        mail = False
    return {
        "calendars": bool(s.calendar_ics_feeds.strip() or s.ilias_ics_url.strip()),
        "health": bool(s.healthconnect_token),
        "mail": mail,
        "news": bool(s.news_feeds.strip()),
        "finance": bool(
            s.enablebanking_app_id and s.enablebanking_private_key and s.enablebanking_redirect_url
        ),
        "push": bool(s.vapid_public_key and s.vapid_private_key),
    }
