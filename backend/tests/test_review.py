from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.nutrition import BodyMeasurement, BodyWeight
from app.models.oauth import AuditLog  # noqa: F401  (keeps the models registered)
from app.services import briefs, nutrition, review, workout_log
from app.services.clock import local_today
from tests.test_logger import bench, logged

TODAY = local_today()


def weights(session, this_week, last_week, before=None):
    for i in range(7):
        session.add(
            BodyWeight(
                source="manual", local_date=TODAY - timedelta(days=i), kg=Decimal(str(this_week))
            )
        )
        session.add(
            BodyWeight(
                source="manual",
                local_date=TODAY - timedelta(days=7 + i),
                kg=Decimal(str(last_week)),
            )
        )
        if before is not None:
            session.add(
                BodyWeight(
                    source="manual",
                    local_date=TODAY - timedelta(days=14 + i),
                    kg=Decimal(str(before)),
                )
            )
    session.flush()


def waist(session, *values):
    for days_ago, cm in values:
        session.add(
            BodyMeasurement(
                metric="waist_cm",
                local_date=TODAY - timedelta(days=days_ago),
                value=Decimal(str(cm)),
            )
        )
    session.flush()


@pytest.fixture
def losing_weight(session):
    nutrition.set_goal(session, "weight_loss_min", 0.2, TODAY - timedelta(days=60))
    nutrition.set_goal(session, "weight_loss_max", 0.4, TODAY - timedelta(days=60))


def test_no_recommendation_without_a_weight_loss_goal(session):
    weights(session, 80.0, 79.0)
    r = review.save_weekly(session, TODAY)
    assert (r.recommendation.action, r.recommendation.kcal_delta) == ("none", 0)
    brief = briefs.latest(session, "weekly")
    assert brief.body.startswith("## Nutrition") and "Recommendation" not in brief.body
    assert review.headline(r) == "Your week in numbers."


def test_slow_loss_with_same_waist_lowers_calories(session, losing_weight):
    nutrition.set_goal(session, "kcal", 2400, TODAY - timedelta(days=30))
    weights(session, 80.0, 80.1, 80.2)  # 0.1 kg per week, twice
    waist(session, (8, 85.0), (1, 85.2))
    r = review.weekly_review(session)
    assert (r.loss_per_week, r.loss_previous_week) == (0.1, 0.1)
    rec = r.recommendation
    assert (rec.action, rec.kcal_delta, rec.new_kcal_goal) == ("decrease", -150, 2250)


def test_slow_loss_without_waist_keeps_calories(session, losing_weight):
    weights(session, 80.0, 80.1, 80.2)
    rec = review.weekly_review(session).recommendation
    assert rec.action == "keep" and "waist" in rec.reasons[0]


def test_fast_loss_raises_calories(session, losing_weight):
    weights(session, 79.0, 80.0)
    rec = review.weekly_review(session).recommendation
    assert (rec.action, rec.kcal_delta) == ("increase", 150)


def test_falling_strength_raises_calories(session, losing_weight):
    workout_log.save(session, logged(days_ago=20, exercises=bench((100, 8, 2))))
    workout_log.save(session, logged(days_ago=3, exercises=bench((90, 8, 2))))
    r = review.weekly_review(session)
    assert r.strength_change_pct == pytest.approx(-10.0)
    assert r.strength_down == ["Bankdrücken"]
    assert r.recommendation.action == "increase"


def test_saved_as_weekly_brief(session, losing_weight):
    weights(session, 80.0, 80.3)
    review.save_weekly(session)
    brief = briefs.latest(session, "weekly")
    assert brief.local_date == TODAY and brief.actor == "worker"
    assert brief.body.startswith("## Recommendation: keep calories as they are")
    assert "## Sleep and heart rate" in brief.body


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_weekly_review_mcp_tool(session, losing_weight):
    from contextlib import nullcontext

    from mcp import Client

    from app.mcp import db as mcp_db
    from app.mcp.server import mcp

    weights(session, 80.0, 80.3)
    mcp_db.set_session_factory(lambda: nullcontext(session))
    try:
        async with Client(mcp, raise_exceptions=True) as c:
            r = await c.call_tool("weekly_review", {})
        data = r.structured_content
        assert data["recommendation"]["action"] == "keep"
        assert data["numbers"]["loss_per_week"] == 0.3
        assert data["markdown"].startswith("## Recommendation")
    finally:
        mcp_db.set_session_factory(mcp_db.SessionLocal)
