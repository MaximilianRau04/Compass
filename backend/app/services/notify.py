"""What Compass pushes, and when. The worker runs check_all every few minutes.

- bedtime: PUSH_BEDTIME_LEAD_MINUTES before the latest bedtime (see analysis.bedtime_for, capped
  by LATEST_BEDTIME), and only when that is earlier than the usual bedtime (median of the last
  14 nights); otherwise you would be in bed by then anyway.
- deadlines: open tasks due within 24 hours, one notification for all new ones. A task without
  a time is due at the end of its day.
- resting: the resting heart rate alert (7-day mean at least 5 bpm above the median), at most
  every 3 days.
- weekly: the weekly review, sent by the worker right after saving it (see weekly_review).
- finance: a bank consent ends within 7 days (approve it again on the finance page).

Nothing but the bedtime reminder goes out in the quiet hours (PUSH_QUIET_START to _END); the
others wait until the quiet hours are over.
"""

import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.i18n import number, number_trimmed, short_date, t, weekday
from app.models.tasks import Task, TaskStatus
from app.services import analysis, finance, push
from app.services.clock import local_tz

log = logging.getLogger("compass.notify")

DEADLINE_AHEAD = timedelta(hours=24)
RESTING_EVERY = timedelta(days=3)


def quiet(now: datetime) -> bool:
    s = get_settings()
    hour = now.astimezone(local_tz()).hour
    start, end = s.push_quiet_start, s.push_quiet_end
    if start == end:
        return False
    return start <= hour or hour < end if start > end else start <= hour < end


def _when(at: datetime, now: datetime) -> str:
    """ "today 14:00", "tomorrow 09:00" or "Fri 09:00"."""
    days = (at.date() - now.date()).days
    day = t("today") if days == 0 else t("tomorrow") if days == 1 else weekday(at)
    return f"{day} {at:%H:%M}"


def _usual_bedtime_minutes(session: Session, today: date) -> int | None:
    """Usual bedtime as minutes from noon (like analysis.sleep_consistency counts them)."""
    usual = analysis.sleep_consistency(session, 14, today).median_bedtime
    if usual is None:
        return None
    h, m = map(int, usual.split(":"))
    return (h * 60 + m - 12 * 60) % (24 * 60)


def check_bedtime(session: Session, now: datetime) -> int:
    tz = local_tz()
    now = now.astimezone(tz)
    # The night belongs to the next day: from noon on it is about tomorrow, after midnight
    # about today.
    day = (now - timedelta(hours=12)).date() + timedelta(days=1)
    bed = analysis.bedtime_for(session, day)
    if bed is None:
        return 0
    latest = bed.latest_bedtime.astimezone(tz)
    lead = timedelta(minutes=get_settings().push_bedtime_lead_minutes)
    if not latest - lead <= now < latest:
        return 0
    usual = _usual_bedtime_minutes(session, day - timedelta(days=1))
    if usual is not None:
        latest_from_noon = (latest.hour * 60 + latest.minute - 12 * 60) % (24 * 60)
        if latest_from_noon >= usual:
            return 0
    first = bed.first_event_at.astimezone(tz)
    wake = bed.wake_at.astimezone(tz)
    return push.send(
        session,
        "bedtime",
        f"bedtime:{day.isoformat()}",
        push.Message(
            title=t("push.bedtime.title", time=f"{latest:%H:%M}"),
            body=t(
                "push.bedtime.body_capped" if bed.capped else "push.bedtime.body",
                when=_when(first, now).capitalize(),
                event=bed.title,
                wake=f"{wake:%H:%M}",
                hours=number_trimmed(get_settings().sleep_need_minutes / 60),
            ),
            url="/",
            tag="bedtime",
            ttl=int((latest - now).total_seconds()) + 600,
            urgent=True,
        ),
    )


def _due_at(task: Task) -> datetime:
    assert task.due_date is not None
    return datetime.combine(task.due_date, task.due_time or time(23, 59), tzinfo=local_tz())


def check_deadlines(session: Session, now: datetime) -> int:
    if quiet(now):
        return 0
    now = now.astimezone(local_tz())
    tasks = session.scalars(
        select(Task).where(
            Task.status.in_((TaskStatus.open, TaskStatus.in_progress)),
            Task.due_date.is_not(None),
            Task.due_date >= now.date(),
            Task.due_date <= (now + DEADLINE_AHEAD).date(),
        )
    ).unique()
    ahead = now + DEADLINE_AHEAD
    due = sorted((task for task in tasks if now <= _due_at(task) <= ahead), key=_due_at)
    new = [
        task for task in due if not push.was_sent(session, f"deadline:{task.id}:{task.due_date}")
    ]
    if not new:
        return 0
    if len(new) == 1:
        task = new[0]
        title, body = t("push.deadline.one", when=_when(_due_at(task), now)), task.title
    else:
        title = t("push.deadline.many", n=len(new))
        body = "\n".join(f"{_when(_due_at(task), now)}: {task.title}" for task in new)
    sent = push.send(
        session,
        "deadlines",
        f"deadline:{new[0].id}:{new[0].due_date}",
        push.Message(title=title[:200], body=body[:500], url="/tasks", tag="deadlines"),
    )
    if sent:
        # One notification covers all of them; mark the others as sent too.
        for task in new[1:]:
            push.mark_sent(session, "deadlines", f"deadline:{task.id}:{task.due_date}", title)
    return sent


def check_resting(session: Session, now: datetime) -> int:
    if quiet(now):
        return 0
    today = now.astimezone(local_tz()).date()
    trend = analysis.resting_trend(session, 30, today)
    if not trend.alert or push.sent_recently(session, "resting", RESTING_EVERY):
        return 0
    return push.send(
        session,
        "resting",
        f"resting:{today.isoformat()}",
        push.Message(
            title=t("push.resting.title"),
            body=t(
                "push.resting.body",
                mean=number(trend.latest_mean7),
                median=number(trend.median),
            ),
            url="/sleep",
            tag="resting",
            ttl=12 * 3600,
        ),
    )


def check_consent(session: Session, now: datetime) -> int:
    if quiet(now):
        return 0
    sent = 0
    for conn in finance.expiring(session, now):
        assert conn.valid_until is not None
        until = conn.valid_until.astimezone(local_tz())
        sent += push.send(
            session,
            "finance",
            f"consent:{conn.id}:{until.date().isoformat()}",
            push.Message(
                title=t("push.consent.title"),
                body=t("push.consent.body", bank=conn.aspsp_name, date=short_date(until)),
                url="/finance",
                tag="finance",
                ttl=24 * 3600,
            ),
        )
    return sent


def weekly_review(session: Session, title: str, recommendation: str, day: date) -> int:
    return push.send(
        session,
        "weekly",
        f"weekly:{day.isoformat()}",
        push.Message(title=title, body=recommendation, url="/", tag="weekly", ttl=24 * 3600),
    )


def check_all(session: Session, now: datetime) -> dict[str, int]:
    out = {}
    for name, check in (
        ("bedtime", check_bedtime),
        ("deadlines", check_deadlines),
        ("resting", check_resting),
        ("finance", check_consent),
    ):
        try:
            out[name] = check(session, now)
        except Exception:
            log.exception("notify: %s failed", name)
            session.rollback()
            out[name] = 0
        else:
            session.commit()
    return out
