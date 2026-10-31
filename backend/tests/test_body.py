from contextlib import nullcontext
from datetime import timedelta
from decimal import Decimal

import pytest
from mcp import Client

from app.mcp import db as mcp_db
from app.mcp.server import mcp
from app.models.nutrition import BodyWeight
from app.services import body, nutrition
from app.services.clock import local_today

TODAY = local_today()


def weigh(session, days_ago, kg, source="manual"):
    session.add(
        BodyWeight(source=source, local_date=TODAY - timedelta(days=days_ago), kg=Decimal(str(kg)))
    )
    session.flush()


def test_one_weight_per_day_manual_first(session):
    weigh(session, 0, 80.4, "mfp_export")
    weigh(session, 0, 80.2, "healthconnect")
    assert [(p.kg, p.source) for p in nutrition.weights(session)] == [(80.2, "healthconnect")]
    body.log(session, "weight", 80.0)
    body.log(session, "weight", 79.9)  # same day again replaces
    assert [(p.kg, p.source) for p in nutrition.weights(session)] == [(79.9, "manual")]


def test_weekly_trend_from_7_day_means(session):
    nutrition.set_goal(session, "weight_loss_min", 0.2)
    nutrition.set_goal(session, "weight_loss_max", 0.4)
    # Last week around 81, this week around 80.7: 0.3 kg per week, on target.
    for i in range(7, 14):
        weigh(session, i, 81.0)
    for i in range(0, 7):
        weigh(session, i, 80.7)
    t = body.trend(session, weeks=4)
    assert (t.mean7, t.mean7_before, t.change_kg) == (80.7, 81.0, -0.3)
    assert t.change_pct == pytest.approx(-0.37, abs=0.01)
    assert (t.loss_per_week, t.status) == (0.3, "on_target")
    assert t.days[-1].mean7 == 80.7


def test_trend_status_and_goal(session):
    for i in range(7, 14):
        weigh(session, i, 81.0)
    for i in range(0, 7):
        weigh(session, i, 80.9)
    # Without a weight loss goal the trend only reports numbers.
    assert body.trend(session).status is None
    nutrition.set_goal(session, "weight_loss_min", 0.2)
    assert body.trend(session).status == "too_slow"
    nutrition.set_goal(session, "weight_loss_min", 0.05)
    assert body.trend(session).status == "on_target"


def test_too_few_weigh_ins_give_no_mean(session):
    weigh(session, 0, 80.0)
    weigh(session, 3, 80.5)
    t = body.trend(session)
    assert t.mean7 is None and t.change_kg is None and t.status is None


def test_waist_and_validation(session):
    body.log(session, "waist", 88.0, TODAY - timedelta(days=8))
    body.log(session, "waist", 87.5)
    t = body.trend(session)
    assert [w.cm for w in t.waist] == [88.0, 87.5] and t.waist_change == -0.5
    with pytest.raises(body.BodyError):
        body.log(session, "weight", 5)
    with pytest.raises(body.BodyError):
        body.log(session, "waist", 80, TODAY + timedelta(days=1))


def test_body_api(client, session):
    r = client.post("/api/body/log", json={"metric": "weight", "value": 80.3})
    assert r.status_code == 200 and r.json()["days"][-1]["kg"] == 80.3
    assert client.post("/api/body/log", json={"metric": "weight", "value": 1}).status_code == 422
    assert client.post("/api/body/log", json={"metric": "height", "value": 180}).status_code == 422
    assert len(client.get("/api/body/trend?weeks=4").json()["weeks"]) == 4


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_body_mcp_tools(session):
    mcp_db.set_session_factory(lambda: nullcontext(session))
    try:
        for i in range(1, 7):
            weigh(session, i, 80.0)
        async with Client(mcp, raise_exceptions=True) as c:
            r = await c.call_tool("log_body_metric", {"metric": "weight", "value": 80.0})
            assert r.structured_content["weigh_ins_last_7_days"] == 7
            assert r.structured_content["mean7_kg"] == 80.0
            r = await c.call_tool("log_body_metric", {"metric": "waist", "value": 1})
            assert r.is_error
            r = await c.call_tool("body_trend", {"weeks": 2})
            assert r.structured_content["target_loss_per_week"] == "0.2-0.4 kg"
    finally:
        mcp_db.set_session_factory(mcp_db.SessionLocal)
