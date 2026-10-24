"""The weekly review: the last 7 days in numbers and a calorie recommendation by fixed rules.

Rules (weight loss as the goal, see app.services.body):
- loss under SLOW_LOSS kg/week in this and the previous week, waist unchanged (within WAIST_SAME
  cm): eat KCAL_STEP kcal less per day;
- loss over FAST_LOSS kg/week, or strength falling (best estimated 1RM per exercise down by more
  than STRENGTH_DROP % on average against the two weeks before): eat KCAL_STEP kcal more;
- otherwise keep the calories.

The worker saves it every Sunday evening as a brief of kind "weekly"; Claude reads the same numbers
through the MCP tool weekly_review.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.health import DailyMetrics, SleepSession
from app.models.training import ExerciseSet, TrainingSession
from app.services import analysis, body, briefs, nutrition, progression, training
from app.services.clock import local_today, local_tz
from app.services.health import main_nights

SLOW_LOSS = 0.15
FAST_LOSS = 0.6
WAIST_SAME = 0.5
STRENGTH_DROP = 2.0
KCAL_STEP = 150


@dataclass
class Recommendation:
    action: str  # decrease | increase | keep
    kcal_delta: int
    current_kcal_goal: float | None
    new_kcal_goal: float | None
    reasons: list[str] = field(default_factory=list)


@dataclass
class Review:
    since: date
    until: date
    kcal: float | None
    protein_g: float | None
    fat_g: float | None
    nutrition_valid_days: int
    nutrition_left_out: int
    weight_mean7: float | None
    weight_change_kg: float | None
    weight_change_pct: float | None
    loss_per_week: float | None
    loss_previous_week: float | None
    weight_status: str | None
    waist_cm: float | None
    waist_change: float | None
    steps_median: int | None
    sessions: int
    split: dict[str, int]
    ready_to_increase: list[str]
    stagnant: list[str]
    strength_change_pct: float | None
    strength_up: list[str]
    strength_down: list[str]
    sleep_avg_minutes: int | None
    sleep_nights: int
    bedtime_sd_minutes: int | None
    median_bedtime: str | None
    short_nights: int
    resting_hr: float | None
    resting_alert: bool
    zone2_minutes: int
    zone2_in_training: int
    recommendation: Recommendation


def _best_e1rm(session: Session, first: date, last: date) -> dict[str, float]:
    tz = local_tz()
    start = datetime.combine(first, time.min, tzinfo=tz)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
    best: dict[str, float] = defaultdict(float)
    for s in session.scalars(
        select(ExerciseSet)
        .join(TrainingSession)
        .where(TrainingSession.started_at >= start, TrainingSession.started_at < end)
    ):
        value = training.e1rm(s.weight_kg, s.reps)
        if value is not None:
            best[s.exercise.name] = max(best[s.exercise.name], value)
    return dict(best)


def strength_trend(session: Session, today: date) -> tuple[float | None, list[str], list[str]]:
    """Average % change of the best estimated 1RM per exercise, last 2 weeks against the 2
    before."""
    now = _best_e1rm(session, today - timedelta(days=13), today)
    before = _best_e1rm(session, today - timedelta(days=27), today - timedelta(days=14))
    common = sorted(set(now) & set(before))
    if not common:
        return None, [], []
    changes = {name: (now[name] - before[name]) / before[name] * 100 for name in common}
    up = [n for n, c in changes.items() if c > 1]
    down = [n for n, c in changes.items() if c < -1]
    return round(mean(changes.values()), 1), up, down


def recommend(
    session: Session,
    today: date,
    loss: float | None,
    loss_before: float | None,
    waist_change: float | None,
    strength: float | None,
) -> Recommendation:
    goal = nutrition.goals_on(session, today).get("kcal")
    reasons = []
    delta = 0
    falling = strength is not None and strength < -STRENGTH_DROP
    if (loss is not None and loss > FAST_LOSS) or falling:
        delta = KCAL_STEP
        if loss is not None and loss > FAST_LOSS:
            reasons.append(f"loss of {loss:.2f} kg/week is above {FAST_LOSS} kg")
        if falling:
            reasons.append(f"strength down {strength:.1f} % (best e1RM, 2 weeks vs 2 before)")
    elif (
        loss is not None
        and loss_before is not None
        and loss < SLOW_LOSS
        and loss_before < SLOW_LOSS
        and waist_change is not None
        and abs(waist_change) <= WAIST_SAME
    ):
        delta = -KCAL_STEP
        reasons.append(
            f"loss under {SLOW_LOSS} kg/week for 2 weeks ({loss_before:.2f}, {loss:.2f}) "
            f"with the waist unchanged ({waist_change:+.1f} cm)"
        )
    else:
        if loss is None:
            reasons.append("not enough weigh-ins for a trend")
        elif loss < SLOW_LOSS and waist_change is None:
            reasons.append("loss is slow, but there is no waist measurement to confirm it")
        else:
            reasons.append("weight and strength are within the rules")
    return Recommendation(
        action="increase" if delta > 0 else "decrease" if delta < 0 else "keep",
        kcal_delta=delta,
        current_kcal_goal=goal,
        new_kcal_goal=goal + delta if goal is not None and delta else goal,
        reasons=reasons,
    )


def weekly_review(session: Session, today: date | None = None) -> Review:
    today = today or local_today()
    since = today - timedelta(days=6)

    food = nutrition.summary(session, 7)
    now = body.trend(session, weeks=2, today=today)
    before = body.trend(session, weeks=2, today=today - timedelta(days=7))
    steps = [
        m.steps
        for m in session.scalars(
            select(DailyMetrics).where(
                DailyMetrics.local_date >= since,
                DailyMetrics.local_date <= today,
                DailyMetrics.steps.is_not(None),
            )
        )
    ]
    tz = local_tz()
    start = datetime.combine(since, time.min, tzinfo=tz)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
    week_sessions = list(
        session.scalars(
            select(TrainingSession).where(
                TrainingSession.started_at >= start, TrainingSession.started_at < end
            )
        )
    )
    split: dict[str, int] = defaultdict(int)
    for t in week_sessions:
        split[training.split_for(t)] += 1
    targets = progression.suggestions(session, weeks=1)
    strength, up, down = strength_trend(session, today)
    nights = main_nights(
        list(
            session.scalars(
                select(SleepSession).where(
                    SleepSession.local_date >= since, SleepSession.local_date <= today
                )
            )
        )
    )
    rhythm = analysis.sleep_consistency(session, 7, today)
    resting = analysis.resting_trend(session, 30, today)
    zone = analysis.zone2_weeks(session, 1, today)
    # zone2_weeks counts calendar weeks; the review covers the last 7 days, close enough on Sunday.
    zone2 = zone[-1] if zone else None

    return Review(
        since=since,
        until=today,
        kcal=food.averages["kcal"],
        protein_g=food.averages["protein_g"],
        fat_g=food.averages["fat_g"],
        nutrition_valid_days=food.quality.valid_days,
        nutrition_left_out=len(food.quality.incomplete) + len(food.quality.same_as_previous_day),
        weight_mean7=now.mean7,
        weight_change_kg=now.change_kg,
        weight_change_pct=now.change_pct,
        loss_per_week=now.loss_per_week,
        loss_previous_week=before.loss_per_week,
        weight_status=now.status,
        waist_cm=now.waist[-1].cm if now.waist else None,
        waist_change=now.waist_change,
        steps_median=round(median(steps)) if steps else None,
        sessions=len(week_sessions),
        split=dict(split),
        ready_to_increase=[t.exercise.name for t in targets if t.action == "increase"],
        stagnant=[t.exercise.name for t in targets if t.stagnant],
        strength_change_pct=strength,
        strength_up=up,
        strength_down=down,
        sleep_avg_minutes=round(mean(n.asleep_minutes for n in nights)) if nights else None,
        sleep_nights=len(nights),
        bedtime_sd_minutes=rhythm.bedtime_sd_minutes,
        median_bedtime=rhythm.median_bedtime,
        short_nights=len(rhythm.short_nights),
        resting_hr=resting.latest_mean7,
        resting_alert=resting.alert,
        zone2_minutes=zone2.minutes if zone2 else 0,
        zone2_in_training=zone2.in_training if zone2 else 0,
        recommendation=recommend(
            session, today, now.loss_per_week, before.loss_per_week, now.waist_change, strength
        ),
    )


# --- The brief ---------------------------------------------------------------------------------

ACTIONS = {
    "decrease": "−{n} kcal pro Tag",
    "increase": "+{n} kcal pro Tag",
    "keep": "Kalorien so lassen",
}


def _num(value: float | None, unit: str = "", digits: int = 0) -> str:
    if value is None:
        return "–"
    text = f"{value:.{digits}f}".replace(".", ",")
    return f"{text} {unit}".strip()


def _hours(minutes: int | None) -> str:
    return "–" if minutes is None else f"{minutes // 60}:{minutes % 60:02d} h"


def markdown(r: Review) -> str:
    """The review as a German brief for the dashboard."""
    rec = r.recommendation
    lines = [
        f"## Empfehlung: {ACTIONS[rec.action].format(n=abs(rec.kcal_delta))}",
        f"- {'; '.join(rec.reasons)}",
    ]
    if rec.current_kcal_goal and rec.kcal_delta:
        lines.append(f"- Ziel von {rec.current_kcal_goal:.0f} auf {rec.new_kcal_goal:.0f} kcal")
    lines += [
        "",
        "## Ernährung",
        f"- Ø {_num(r.kcal, 'kcal')}, Eiweiß {_num(r.protein_g, 'g')}, Fett {_num(r.fat_g, 'g')} "
        f"über {r.nutrition_valid_days} gültige Tage"
        + (f" ({r.nutrition_left_out} nicht gezählt)" if r.nutrition_left_out else ""),
        "",
        "## Körper",
        f"- Gewicht {_num(r.weight_mean7, 'kg', 1)} (7-Tage-Mittel), "
        f"{_num(r.weight_change_kg, 'kg', 2)} zur Vorwoche ({_num(r.weight_change_pct, '%', 1)})",
        f"- Taille {_num(r.waist_cm, 'cm', 1)}"
        + (f", {r.waist_change:+.1f} cm".replace(".", ",") if r.waist_change is not None else ""),
        f"- Schritte Median {_num(r.steps_median)}",
        "",
        "## Training",
        f"- {r.sessions} Einheiten"
        + (f" ({', '.join(f'{k} {v}' for k, v in sorted(r.split.items()))})" if r.split else ""),
        f"- Kraft (bestes e1RM, 2 Wochen zu 2 Wochen): {_num(r.strength_change_pct, '%', 1)}",
    ]
    if r.ready_to_increase:
        lines.append(f"- Gewicht erhöhen: {', '.join(r.ready_to_increase)}")
    if r.stagnant:
        lines.append(f"- Stagniert: {', '.join(r.stagnant)}")
    lines.append(f"- Zone 2: {r.zone2_minutes} min, davon {r.zone2_in_training} im Training")
    lines += [
        "",
        "## Schlaf und Puls",
        f"- Ø {_hours(r.sleep_avg_minutes)} in {r.sleep_nights} Nächten, "
        f"{r.short_nights} unter 7 h",
        f"- Bettzeit Median {r.median_bedtime or '–'}, ± {_num(r.bedtime_sd_minutes, 'min')}",
        f"- Ruhepuls {_num(r.resting_hr, 'bpm', 1)}"
        + (" (erhöht, mehr Erholung einplanen)" if r.resting_alert else ""),
    ]
    return "\n".join(lines)


def save_weekly(session: Session, today: date | None = None) -> None:
    """Store this week's review as the brief of kind "weekly" (run by the worker on Sundays)."""
    review = weekly_review(session, today)
    briefs.save(
        session,
        "weekly",
        markdown(review),
        title=f"Wochenreview {review.since:%d.%m.}–{review.until:%d.%m.}",
        day=review.until,
        actor="worker",
    )
