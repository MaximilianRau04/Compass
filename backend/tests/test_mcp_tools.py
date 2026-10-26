from contextlib import nullcontext
from datetime import datetime, timedelta

import pytest
from mcp import Client

from app.ingestion import calendar, gymday
from app.mcp import db as mcp_db
from app.mcp.server import mcp
from app.models.oauth import AuditLog
from app.services.clock import local_today, local_tz
from tests.test_healthconnect import at, ingest, night, record


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(session):
    mcp_db.set_session_factory(lambda: nullcontext(session))
    async with Client(mcp, raise_exceptions=True) as c:
        yield c
    mcp_db.set_session_factory(mcp_db.SessionLocal)


async def call(client, tool, **args):
    result = await client.call_tool(tool, args)
    assert not result.is_error, result.content
    return result.structured_content


async def call_error(client, tool, **args) -> str:
    result = await client.call_tool(tool, args)
    assert result.is_error
    return result.content[0].text


@pytest.mark.anyio
async def test_tools_are_listed_with_annotations(client):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {
        "get_today",
        "list_tasks",
        "get_deadlines",
        "get_task",
        "list_areas",
        "add_task",
        "quick_add",
        "update_task",
        "complete_task",
        "get_calendar",
        "training_summary",
        "exercise_progress",
        "sleep_summary",
        "nutrition_summary",
        "set_nutrition_goal",
        "list_important_mails",
        "mails_to_triage",
        "save_mail_triage",
        "get_news_digest",
        "feedback_news",
        "save_brief",
        "get_brief",
        "search_notes",
        "get_note",
        "get_context",
        "add_note",
        "append_note",
        "progression_suggestions",
        "body_trend",
        "log_body_metric",
        "weekly_review",
        "send_notification",
        "finance_summary",
        "list_transactions",
        "categorize_transactions",
        "set_budget",
        "log_depot_value",
    }
    assert tools["get_today"].annotations.read_only_hint is True
    assert tools["add_task"].annotations.destructive_hint is False
    for name in (
        "get_calendar",
        "training_summary",
        "exercise_progress",
        "sleep_summary",
        "nutrition_summary",
        "list_important_mails",
        "get_news_digest",
        "get_brief",
    ):
        assert tools[name].annotations.read_only_hint is True


@pytest.mark.anyio
async def test_add_task_and_see_it_today(client, session):
    today = local_today()
    task = await call(
        client, "add_task", title="Paper lesen", scheduled_date=today.isoformat(), area="work"
    )
    assert task["source"] == "claude"
    assert task["area"] == "work"

    overview = await call(client, "get_today")
    assert [t["title"] for t in overview["scheduled"]] == ["Paper lesen"]

    entries = session.query(AuditLog).all()
    assert [(e.action, e.ok) for e in entries] == [("add_task", True)]


@pytest.mark.anyio
async def test_quick_add_marks_source_claude(client):
    task = await call(client, "quick_add", text="morgen 14 Uhr Blatt 3 abgeben #uni !hoch")
    assert task["title"] == "Blatt 3 abgeben"
    assert task["source"] == "claude"
    assert task["priority"] == "high"
    assert task["due_time"] == "14:00"


@pytest.mark.anyio
async def test_update_with_clear_and_cancel(client):
    today = local_today()
    task = await call(client, "add_task", title="Alt", due_date=today.isoformat(), tags=["a"])
    updated = await call(
        client, "update_task", task_id=task["id"], title="Neu", clear=["due_date", "tags"]
    )
    assert (updated["title"], updated["due_date"], updated["tags"]) == ("Neu", None, [])

    await call(client, "update_task", task_id=task["id"], status="cancelled")
    listed = await call(client, "list_tasks")
    assert listed["count"] == 0

    detail = await call(client, "get_task", task_id=task["id"])
    assert [e["type"] for e in detail["history"]] == ["created", "updated", "cancelled"]
    assert all(e["actor"] == "claude" for e in detail["history"])


@pytest.mark.anyio
async def test_complete_recurring_returns_next_instance(client):
    today = local_today()
    task = await call(
        client,
        "add_task",
        title="Müll",
        scheduled_date=today.isoformat(),
        recurrence="FREQ=WEEKLY",
    )
    result = await call(client, "complete_task", task_id=task["id"])
    assert result["task"]["status"] == "done"
    assert result["next_instance"]["scheduled_date"] == (today + timedelta(days=7)).isoformat()


@pytest.mark.anyio
async def test_deadlines(client):
    today = local_today()
    await call(client, "add_task", title="late", due_date=(today - timedelta(days=1)).isoformat())
    await call(client, "add_task", title="soon", due_date=(today + timedelta(days=3)).isoformat())
    await call(client, "add_task", title="far", due_date=(today + timedelta(days=60)).isoformat())
    result = await call(client, "get_deadlines", days=14)
    assert [t["title"] for t in result["overdue"]] == ["late"]
    assert [t["title"] for t in result["upcoming"]] == ["soon"]


@pytest.mark.anyio
async def test_helpful_errors_and_failed_writes_are_audited(client, session):
    error = await call_error(client, "add_task", title="x", area="nope")
    assert "Valid areas: uni, work" in error
    assert "No task with id 999" in await call_error(client, "complete_task", task_id=999)
    task = await call(client, "add_task", title="exists")
    assert "Nothing to change" in await call_error(client, "update_task", task_id=task["id"])
    assert "needs a due_date" in await call_error(client, "add_task", title="x", due_time="10:00")

    failed = session.query(AuditLog).filter(AuditLog.ok.is_(False)).all()
    assert {e.action for e in failed} == {"add_task", "complete_task", "update_task"}


@pytest.mark.anyio
async def test_prompts(client):
    prompts = {p.name for p in (await client.list_prompts()).prompts}
    assert prompts == {"daily_brief", "weekly_review", "sort_mails", "news_report"}


@pytest.mark.anyio
async def test_calendar_and_today_events(client, session):
    today = local_today()
    day = f"{today:%Y%m%d}"
    feed = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//t//EN\n"
        f"BEGIN:VEVENT\nUID:l1\nSUMMARY:Vorlesung\nDTSTART;TZID=Europe/Berlin:{day}T140000\n"
        f"DTEND;TZID=Europe/Berlin:{day}T153000\nLOCATION:V38\nEND:VEVENT\n"
        f"BEGIN:VEVENT\nUID:h1\nSUMMARY:Feiertag\nDTSTART;VALUE=DATE:{day}\nEND:VEVENT\n"
        "END:VCALENDAR\n"
    ).encode()
    calendar.sync_feed(session, "uni", feed, today)

    result = await call(client, "get_calendar", days=3)
    events = result["events"]
    assert [e["title"] for e in events] == ["Feiertag", "Vorlesung"]
    assert events[0] == {
        "title": "Feiertag",
        "start": today.isoformat(),
        "end": today.isoformat(),
        "all_day": True,
        "location": None,
        "calendar": "uni",
    }
    assert events[1]["start"] == f"{today.isoformat()} 14:00"
    assert events[1]["end"] == f"{today.isoformat()} 15:30"

    day_view = await call(client, "get_today")
    assert [e["title"] for e in day_view["events"]] == ["Feiertag", "Vorlesung"]


@pytest.mark.anyio
async def test_training_tools(client, session):
    def when(days_ago: int) -> str:
        return f"{local_today() - timedelta(days=days_ago):%Y-%m-%d} 18:00:00"

    csv = "\n".join(
        [
            '"Date","Workout name","Exercise","Set","Weight","Reps","Distance","Duration",'
            '"Measurement unit","Notes"',
            f'"{when(8)}","Pull","Latzug mit engem Griff","1","65","10","","","kg",',
            f'"{when(1)}","Pull","Latzug mit engem Griff","1","70","10","","","kg",',
            f'"{when(1)}","Pull","Klimmzüge","1","","8","","","kg",',
        ]
    ).encode()
    gymday.import_csv(session, csv)

    summary = await call(client, "training_summary", weeks=4)
    assert summary["sessions"] == 2
    assert summary["split"]["pull"] == 2
    assert summary["recent"][0]["exercises"] == 2

    progress = await call(client, "exercise_progress", exercise="latzug")
    assert progress["exercise"] == "Latzug mit engem Griff"
    assert [p["top_weight_kg"] for p in progress["sessions"]] == [65, 70]

    bodyweight = await call(client, "exercise_progress", exercise="Klimmzüge")
    assert bodyweight["bodyweight"] is True
    assert bodyweight["sessions"][0]["max_reps"] == 8

    assert "No exercise" in await call_error(client, "exercise_progress", exercise="Kreuzheben")


@pytest.mark.anyio
async def test_sleep_summary(client, session):
    today = local_today()
    noon = at(today, "12:00")
    n = night()
    ingest(session, [n, record("st", "steps", noon, noon, count=8000)])
    summary = await call(client, "sleep_summary", days=7)
    [last] = summary["nights"]
    assert last["date"] == today.isoformat()
    # 23:00 to 07:00, or 06:00 / 08:00 after a night with a clock change.
    clock = [
        datetime.fromisoformat(n[k]).astimezone(local_tz()).strftime("%H:%M")
        for k in ("start", "end")
    ]
    assert (last["bedtime"], last["wake_time"]) == tuple(clock)
    assert last["asleep_minutes"] == 450
    assert summary["avg_steps"] == 8000
    assert summary["last_sync"] is not None


@pytest.mark.anyio
async def test_nutrition_summary_and_goal(client, session):
    today = local_today()
    meal = record("m", "nutrition", at(today, "12:00"), at(today, "12:00"))
    meal["data"] = {"meal_type": "lunch", "energy_kcal": 700, "protein_g": 45}
    ingest(session, [meal])

    goal = await call(client, "set_nutrition_goal", metric="protein_g", value=170)
    assert (goal["metric"], goal["value"]) == ("protein_g", 170)

    summary = await call(client, "nutrition_summary", days=7)
    assert summary["goals"] == {"protein_g": 170}
    [day] = summary["days"]
    assert day["meals_kcal"] == {"lunch": 700}
    assert day["protein_g"] == 45

    error = await call_error(client, "set_nutrition_goal", metric="kcal", value=-5)
    assert "greater than 0" in error
