from contextlib import nullcontext
from datetime import datetime, timedelta

import pytest
from mcp import Client

from app.config import get_settings
from app.ingestion import calendar, workouts
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
        "daily_data",
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
        "search",
        "completed_tasks",
        "add_task_note",
        "mail_to_task",
        "get_journal",
        "write_journal",
        "monthly_review",
        "get_training_session",
        "log_sleep",
        "list_habits",
        "check_habit",
        "list_savings_goals",
        "save_savings_goal",
        "split_transaction",
    }
    assert tools["get_today"].annotations.read_only_hint is True
    assert tools["add_task"].annotations.destructive_hint is False
    assert tools["log_sleep"].annotations.destructive_hint is False
    assert tools["check_habit"].annotations.destructive_hint is False
    assert tools["save_savings_goal"].annotations.destructive_hint is False
    assert tools["split_transaction"].annotations.destructive_hint is False
    for name in (
        "get_calendar",
        "training_summary",
        "get_training_session",
        "list_habits",
        "list_savings_goals",
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
    task = await call(client, "quick_add", text="morgen 14 Uhr Blatt 3 abgeben #study !hoch")
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
    assert "Valid areas: study, work" in error
    assert "No task with id 999" in await call_error(client, "complete_task", task_id=999)
    task = await call(client, "add_task", title="exists")
    assert "Nothing to change" in await call_error(client, "update_task", task_id=task["id"])
    assert "needs a due_date" in await call_error(client, "add_task", title="x", due_time="10:00")
    assert "at most 20000" in await call_error(client, "add_task", title="x", notes="n" * 20_001)

    failed = session.query(AuditLog).filter(AuditLog.ok.is_(False)).all()
    assert {e.action for e in failed} == {"add_task", "complete_task", "update_task"}


@pytest.mark.anyio
async def test_prompts(client):
    prompts = {p.name for p in (await client.list_prompts()).prompts}
    assert prompts == {
        "daily_brief",
        "weekly_review",
        "sort_mails",
        "news_report",
        "health_analysis",
    }


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
    workouts.import_csv(session, csv)

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
async def test_daily_data_joins_the_areas_per_day(client, session):
    today = local_today()
    yesterday = today - timedelta(days=1)
    meal = record("m", "nutrition", at(yesterday, "12:00"), at(yesterday, "12:00"))
    meal["data"] = {"meal_type": "lunch", "energy_kcal": 2100, "protein_g": 150}
    ingest(
        session,
        [night(), meal, record("st", "steps", at(today, "12:00"), at(today, "12:00"), count=8000)],
    )
    csv = "\n".join(
        [
            '"Date","Workout name","Exercise","Set","Weight","Reps","Distance","Duration",'
            '"Measurement unit","Notes"',
            f'"{yesterday:%Y-%m-%d} 18:00:00","Legs","Kniebeuge","1","100","5","","","kg",',
            f'"{yesterday:%Y-%m-%d} 18:00:00","Legs","Kniebeuge","2","100","5","","","kg",',
        ]
    ).encode()
    workouts.import_csv(session, csv)

    data = await call(client, "daily_data", days=7)
    rows = {r["date"]: r for r in data["days"]}
    assert len(rows) == 7 and data["until"] == today.isoformat()
    last, before = rows[today.isoformat()], rows[yesterday.isoformat()]
    assert (last["asleep_minutes"], last["steps"], last["kcal"]) == (450, 8000, None)
    assert before["training"] == ["Legs (legs)"]
    assert (before["sets"], before["volume_kg"], before["kcal"], before["protein_g"]) == (
        2,
        1000.0,
        2100,
        150,
    )


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


def test_the_instructions_name_the_configured_time_zone():
    instructions = mcp.instructions
    assert f"local dates in {get_settings().timezone}." in instructions
    assert "{" not in instructions


@pytest.mark.anyio
async def test_search_finds_tasks_notes_events_and_mails(client, session):
    from tests.test_search import event, mail

    done = await call(client, "add_task", title="Thesis outline", tags=["uni"])
    await call(client, "complete_task", task_id=done["id"])
    await call(client, "add_task", title="Thesis: write the introduction")
    await call(client, "add_note", title="Thesis ideas", body="Compare two planners.")
    event(session, "Thesis meeting", days=2)
    mail(session, "Your thesis registration", summary="Register until Friday.")

    found = await call(client, "search", query="thesis")
    assert [t["status"] for t in found["tasks"]] == ["open", "done"]
    assert [n["title"] for n in found["notes"]] == ["Thesis ideas"]
    assert [e["title"] for e in found["events"]] == ["Thesis meeting"]
    assert [m["summary"] for m in found["mails"]] == ["Register until Friday."]
    assert "Untrusted" in found["note"]

    nothing = await call(client, "search", query="zeppelin")
    assert (nothing["tasks"], nothing["notes"], nothing["events"], nothing["mails"]) == (
        [],
        [],
        [],
        [],
    )
    assert "at least 2 characters" in await call_error(client, "search", query="t")


@pytest.mark.anyio
async def test_add_task_note_appends_a_dated_paragraph(client):
    today = local_today().isoformat()
    task = await call(client, "add_task", title="Exposé", notes="Outline agreed with the chair.")

    noted = await call(client, "add_task_note", task_id=task["id"], text="  Chapter 1 drafted. ")
    assert noted["notes"] == f"Outline agreed with the chair.\n\n{today}: Chapter 1 drafted."
    noted = await call(client, "add_task_note", task_id=task["id"], text="Next: related work.")
    assert noted["notes"].endswith(f"{today}: Chapter 1 drafted.\n\n{today}: Next: related work.")

    empty = await call(client, "add_task", title="No notes yet")
    noted = await call(client, "add_task_note", task_id=empty["id"], text="Started.")
    assert noted["notes"] == f"{today}: Started."

    detail = await call(client, "get_task", task_id=task["id"])
    assert [e["type"] for e in detail["history"]] == ["created", "updated", "updated"]
    assert "No task with id" in await call_error(client, "add_task_note", task_id=0, text="x")
    full = await call(client, "add_task", title="Full", notes="x" * 19_990)
    error = await call_error(client, "add_task_note", task_id=full["id"], text="one more line")
    assert "longer than 20000" in error


@pytest.mark.anyio
async def test_completed_tasks_lists_what_got_done(client, session):
    from app.models.tasks import Task

    today = local_today()
    first = await call(client, "add_task", title="Sheet 3", area="study")
    second = await call(client, "add_task", title="Call the bank", area="personal")
    old = await call(client, "add_task", title="Long ago")
    await call(client, "add_task", title="Still open")
    for task in (first, second, old):
        await call(client, "complete_task", task_id=task["id"])
    noon = datetime.combine(today, datetime.min.time(), tzinfo=local_tz()) + timedelta(hours=12)
    session.get(Task, first["id"]).completed_at = noon - timedelta(days=1)
    session.get(Task, second["id"]).completed_at = noon
    session.get(Task, old["id"]).completed_at = noon - timedelta(days=7)
    session.flush()

    done = await call(client, "completed_tasks")
    assert (done["since"], done["until"]) == (
        (today - timedelta(days=6)).isoformat(),
        today.isoformat(),
    )
    assert [t["title"] for t in done["tasks"]] == ["Call the bank", "Sheet 3"]
    assert done["tasks"][0]["completed"] == f"{today.isoformat()} 12:00"
    assert done["by_day"] == {
        today.isoformat(): 1,
        (today - timedelta(days=1)).isoformat(): 1,
    }

    assert (await call(client, "completed_tasks", days=8))["count"] == 3
    study = await call(client, "completed_tasks", area="study")
    assert [t["title"] for t in study["tasks"]] == ["Sheet 3"]
    assert (await call(client, "completed_tasks", days=1))["count"] == 1


@pytest.mark.anyio
async def test_mail_to_task_creates_one_task_and_handles_the_mail(client, session):
    from tests.test_search import mail

    e = mail(
        session,
        "Registration for the exam",
        summary="Register until Friday.",
        task_title="Register for the exam",
        priority="high",
    )
    task = await call(client, "mail_to_task", mail_id=e.id)
    assert (task["title"], task["source"]) == ("Register for the exam", "email")
    assert "Register until Friday." in task["notes"]

    again = await call(client, "mail_to_task", mail_id=e.id)
    assert again["id"] == task["id"]
    assert (await call(client, "list_important_mails"))["mails"] == []
    detail = await call(client, "get_task", task_id=task["id"])
    assert [(h["type"], h["actor"]) for h in detail["history"]] == [("created", "claude")]

    assert "No mail with id" in await call_error(client, "mail_to_task", mail_id=0)


@pytest.mark.anyio
async def test_get_training_session_returns_exercises_and_sets(client, session):
    from decimal import Decimal

    from app.models.training import Exercise, ExerciseSet, TrainingSession

    ex = Exercise(name="Bench Press", bodyweight=False)
    session.add(ex)
    session.flush()
    ts = TrainingSession(
        started_at=datetime(2026, 11, 10, 17, 0, tzinfo=local_tz()),
        workout_name="Push A",
        source="compass",
    )
    session.add(ts)
    session.flush()
    session.add_all(
        [
            ExerciseSet(
                session_id=ts.id,
                exercise_id=ex.id,
                set_index=1,
                weight_kg=Decimal("80"),
                reps=8,
                rir=2,
            ),
            ExerciseSet(
                session_id=ts.id,
                exercise_id=ex.id,
                set_index=2,
                weight_kg=Decimal("80"),
                reps=7,
                rir=1,
            ),
        ]
    )
    session.flush()

    detail = await call(client, "get_training_session", session_id=ts.id)
    assert (detail["id"], detail["workout"], detail["sets"]) == (ts.id, "Push A", 2)
    assert len(detail["exercises_detail"]) == 1
    assert detail["exercises_detail"][0]["exercise"] == "Bench Press"
    assert [
        (s["set_index"], s["weight_kg"], s["reps"], s["rir"])
        for s in detail["exercises_detail"][0]["sets"]
    ] == [
        (1, 80.0, 8, 2),
        (2, 80.0, 7, 1),
    ]
    assert "No training session with id" in await call_error(
        client, "get_training_session", session_id=999999
    )


@pytest.mark.anyio
async def test_log_sleep_records_manual_night_and_rejects_overlap(client, session):
    tz = local_tz()
    wake = datetime.combine(local_today(), datetime.min.time(), tzinfo=tz) + timedelta(hours=7)
    bed = wake - timedelta(hours=8)

    night = await call(
        client,
        "log_sleep",
        start_at=bed.isoformat(),
        end_at=wake.isoformat(),
        awake_minutes=20,
    )
    assert night["in_bed_minutes"] == 480
    assert night["asleep_minutes"] == 460
    assert night["awake_minutes"] == 20

    assert "overlaps" in await call_error(
        client,
        "log_sleep",
        start_at=bed.isoformat(),
        end_at=wake.isoformat(),
    )


@pytest.mark.anyio
async def test_habits_mcp_lists_and_checks_manual_habits(client, session):
    from app.services import habits

    manual = habits.create(session, "Read 20 pages")
    auto = habits.create(session, "Journal", rule="journal")
    session.flush()

    listed = await call(client, "list_habits")
    assert [h["name"] for h in listed["habits"]] == ["Read 20 pages", "Journal"]
    assert listed["habits"][0]["done_today"] is False

    ticked = await call(client, "check_habit", habit_id=manual.id, done=True)
    assert (ticked["done_today"], ticked["streak"]) == (True, 1)

    unticked = await call(client, "check_habit", habit_id=manual.id, done=False)
    assert (unticked["done_today"], unticked["streak"]) == (False, 0)

    assert "from the data" in await call_error(client, "check_habit", habit_id=auto.id, done=True)
    assert "No active habit" in await call_error(client, "check_habit", habit_id=999999, done=True)


@pytest.mark.anyio
async def test_finance_savings_goals_and_splits_mcp(client, session):
    from decimal import Decimal

    from app.models.finance import BankAccount, BankTransaction

    goal = await call(
        client, "save_savings_goal", name="Vacation", target_amount=2000, current_amount=500
    )
    assert (goal["name"], goal["progress_pct"]) == ("Vacation", 25.0)
    updated = await call(client, "save_savings_goal", goal_id=goal["id"], current_amount=1000)
    assert updated["progress_pct"] == 50.0
    listed = await call(client, "list_savings_goals")
    assert [g["name"] for g in listed["goals"]] == ["Vacation"]

    acc = BankAccount(identification_hash="h1", name="Giro")
    session.add(acc)
    session.flush()
    tx = BankTransaction(
        account_id=acc.id,
        external_id="split-1",
        booking_date=local_today(),
        amount=Decimal("-80.00"),
        counterparty="Shop",
    )
    session.add(tx)
    session.flush()

    msg = await call(
        client,
        "split_transaction",
        transaction_id=tx.id,
        splits=[
            {"category": "shopping", "amount": 50},
            {"category": "groceries", "amount": 30},
        ],
    )
    assert "shopping: 50.00" in msg["result"] and "groceries: 30.00" in msg["result"]
