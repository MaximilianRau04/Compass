from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.config import get_settings
from app.models.training import Exercise, ExerciseSet, TrainingSession
from app.services import notify, progression


def _session(
    session, exercise: Exercise, days_ago: int, sets: list[tuple[Decimal | None, int, int | None]]
):
    ts = TrainingSession(
        started_at=datetime.now(UTC) - timedelta(days=days_ago),
        workout_name="Push A",
        source="compass",
    )
    session.add(ts)
    session.flush()
    for i, (w, reps, rir) in enumerate(sets, start=1):
        session.add(
            ExerciseSet(
                session_id=ts.id,
                exercise_id=exercise.id,
                set_index=i,
                weight_kg=w,
                reps=reps,
                rir=rir,
            )
        )
    session.flush()
    return ts


def test_double_progression_adds_rep_until_top_of_range_then_increases_weight(session):
    ex = Exercise(name="Bench Press", rep_min=8, rep_max=10, weight_step=Decimal("2.5"))
    session.add(ex)
    session.flush()

    # Warm-up set (40 kg) is ignored; working sets at 80 kg haven't all reached 10 reps yet.
    _session(
        session,
        ex,
        3,
        [
            (Decimal("40"), 12, None),
            (Decimal("80"), 10, 2),
            (Decimal("80"), 9, 1),
        ],
    )
    [s] = progression.suggestions(session)
    assert (s.action, s.weight_kg, s.reps, s.rir_known, s.stagnant) == (
        "reps",
        80.0,
        10,
        True,
        False,
    )
    assert s.last_set_count == 3 and len(s.last_sets) == 2

    # All working sets reach rep_max with RIR <= 2 -> increase weight and drop back to rep_min.
    _session(session, ex, 1, [(Decimal("80"), 10, 2), (Decimal("80"), 10, 1)])
    [s] = progression.suggestions(session)
    assert (s.action, s.weight_kg, s.reps) == ("increase", 82.5, 8)


def test_high_rir_holds_weight_and_flags_stagnation_after_four_identical_sessions(session):
    ex = Exercise(name="Row", rep_min=8, rep_max=10, weight_step=Decimal("2.5"))
    session.add(ex)
    session.flush()

    for days_ago in (16, 12, 8, 4):
        _session(session, ex, days_ago, [(Decimal("60"), 10, 3), (Decimal("60"), 10, 3)])

    [s] = progression.suggestions(session)
    # RIR 3 exceeds MAX_RIR (2), so weight does not increase even at rep_max.
    assert s.action == "reps" and s.weight_kg == 60.0
    assert s.same_sessions == 4 and s.stagnant is True


def test_bodyweight_progression_adds_reps_then_extra_load(session):
    ex = Exercise(name="Pull-Up", bodyweight=True, rep_min=6, rep_max=8, weight_step=Decimal("2.5"))
    session.add(ex)
    session.flush()

    _session(session, ex, 4, [(None, 7, 2), (None, 6, 1)])
    [s] = progression.suggestions(session)
    assert (s.action, s.weight_kg, s.reps) == ("reps", None, 7)

    _session(session, ex, 1, [(None, 8, 2), (None, 8, 1)])
    [s] = progression.suggestions(session)
    assert (s.action, s.weight_kg, s.reps) == ("increase", 2.5, 6)


def test_quiet_hours_handles_midnight_wrap_daytime_and_disabled(monkeypatch):
    settings = get_settings()
    tz = notify.local_tz()

    monkeypatch.setattr(settings, "push_quiet_start", 23)
    monkeypatch.setattr(settings, "push_quiet_end", 8)
    assert notify.quiet(datetime(2026, 11, 10, 23, 30, tzinfo=tz)) is True
    assert notify.quiet(datetime(2026, 11, 10, 7, 59, tzinfo=tz)) is True
    assert notify.quiet(datetime(2026, 11, 10, 8, 0, tzinfo=tz)) is False

    monkeypatch.setattr(settings, "push_quiet_start", 12)
    monkeypatch.setattr(settings, "push_quiet_end", 14)
    assert notify.quiet(datetime(2026, 11, 10, 13, 0, tzinfo=tz)) is True
    assert notify.quiet(datetime(2026, 11, 10, 14, 0, tzinfo=tz)) is False

    monkeypatch.setattr(settings, "push_quiet_start", 8)
    monkeypatch.setattr(settings, "push_quiet_end", 8)
    assert notify.quiet(datetime(2026, 11, 10, 8, 0, tzinfo=tz)) is False
