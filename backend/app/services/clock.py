from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def local_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def local_today() -> date:
    return datetime.now(local_tz()).date()


def utc_now() -> datetime:
    return datetime.now(ZoneInfo("UTC"))
