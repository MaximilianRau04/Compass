from contextlib import nullcontext
from datetime import timedelta

import pytest
from mcp import Client

from app.mcp import db as mcp_db
from app.mcp.server import mcp
from app.models.oauth import AuditLog
from app.services.clock import local_today


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
    }
    assert tools["get_today"].annotations.read_only_hint is True
    assert tools["add_task"].annotations.destructive_hint is False


@pytest.mark.anyio
async def test_add_task_and_see_it_today(client, session):
    today = local_today()
    task = await call(
        client, "add_task", title="Paper lesen", scheduled_date=today.isoformat(), area="arbeit"
    )
    assert task["source"] == "claude"
    assert task["area"] == "arbeit"

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
    assert "Valid areas: uni, arbeit" in error
    assert "No task with id 999" in await call_error(client, "complete_task", task_id=999)
    task = await call(client, "add_task", title="exists")
    assert "Nothing to change" in await call_error(client, "update_task", task_id=task["id"])
    assert "needs a due_date" in await call_error(client, "add_task", title="x", due_time="10:00")

    failed = session.query(AuditLog).filter(AuditLog.ok.is_(False)).all()
    assert {e.action for e in failed} == {"add_task", "complete_task", "update_task"}


@pytest.mark.anyio
async def test_prompts(client):
    prompts = {p.name for p in (await client.list_prompts()).prompts}
    assert prompts == {"daily_brief", "weekly_review"}
