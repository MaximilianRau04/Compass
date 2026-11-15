"""How ready the body is today, by fixed rules like the calorie recommendation: last night's sleep
against the sleep need, the resting heart rate and the HRV against their median of the last
28 days, and the training load of the last two days against the usual. Each finding takes points
off 100 and names its reason; without last night's sleep or a resting heart rate there is no
score, since the rest alone says too little."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import daily, health
from app.services.clock import local_today

BASELINE_DAYS = 28


@dataclass
class Readiness:
    date: date
    score: int | None  # 0 to 100, None without enough data
    level: str | None  # good | moderate | low
    # Codes the clients translate, e.g. "short_sleep", "resting_up", "hrv_down", "high_load".
    reasons: list[str] = field(default_factory=list)
    asleep_minutes: int | None = None
    resting_hr: int | None = None
    resting_median: float | None = None
    hrv: float | None = None
    hrv_median: float | None = None


def _hrv(extras: dict[str, float]) -> float | None:
    return extras.get("heart_rate_variability") or extras.get("heart_rate_variability_sdnn")


def readiness(session: Session, today: date | None = None) -> Readiness:
    today = today or local_today()
    rows = daily.daily_rows(session, BASELINE_DAYS + 1, today)
    *before, now = rows
    since = today - timedelta(days=BASELINE_DAYS)
    extras = health.extras(session, since, today)
    out = Readiness(date=today, score=None, level=None)
    out.asleep_minutes, out.resting_hr = now.asleep_minutes, now.resting_hr
    resting = [r.resting_hr for r in before if r.resting_hr is not None]
    out.resting_median = float(median(resting)) if resting else None
    hrvs = [v for d, e in extras.items() if d < today and (v := _hrv(e)) is not None]
    out.hrv = _hrv(extras.get(today, {}))
    out.hrv_median = round(float(median(hrvs)), 1) if hrvs else None
    if out.asleep_minutes is None or out.resting_hr is None:
        return out

    score = 100
    need = get_settings().sleep_need_minutes
    if out.asleep_minutes < 360:
        score -= 30
        out.reasons.append("short_sleep")
    elif out.asleep_minutes < need - 60:
        score -= 15
        out.reasons.append("short_sleep")
    if out.resting_median is not None and len(resting) >= 7:
        up = out.resting_hr - out.resting_median
        if up >= 5:
            score -= 25
            out.reasons.append("resting_up")
        elif up >= 3:
            score -= 10
            out.reasons.append("resting_up")
    if out.hrv is not None and out.hrv_median and len(hrvs) >= 7:
        ratio = out.hrv / out.hrv_median
        if ratio <= 0.85:
            score -= 20
            out.reasons.append("hrv_down")
        elif ratio <= 0.93:
            score -= 10
            out.reasons.append("hrv_down")
    # Sets of yesterday and the day before against the usual two days.
    recent = sum(r.sets for r in before[-2:])
    usual = 2 * sum(r.sets for r in before) / len(before) if before else 0
    if usual and recent >= 1.5 * usual and recent >= 20:
        score -= 10
        out.reasons.append("high_load")

    out.score = max(0, score)
    out.level = "good" if out.score >= 75 else "moderate" if out.score >= 50 else "low"
    return out
