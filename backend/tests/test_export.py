import io
import json
import zipfile

from app.models.feeds import Feed
from app.models.finance import BankConnection
from app.services import export, journal
from app.services.clock import local_today

# Every table and column the export contains. Only what export.py lists is left out, so a new
# table or column fails here until somebody decided whether it may leave the server.
EXPORTED = {
    "areas": ["id", "slug", "name", "color", "sort_order", "archived", "created_at", "updated_at"],
    "audit_log": ["id", "created_at", "actor", "action", "arguments", "ok", "detail"],
    "bank_connections": [
        "id",
        "aspsp_name",
        "aspsp_country",
        "valid_until",
        "status",
        "last_sync_at",
        "last_error",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "bank_transaction_splits": ["id", "transaction_id", "category", "amount", "note"],
    "body_measurements": ["id", "metric", "local_date", "value", "created_at", "updated_at"],
    "body_weight": ["id", "source", "local_date", "kg", "measured_at", "created_at", "updated_at"],
    "briefs": ["id", "kind", "local_date", "title", "body", "actor", "created_at", "updated_at"],
    "calendar_events": [
        "id",
        "feed",
        "uid",
        "title",
        "location",
        "starts_at",
        "ends_at",
        "all_day",
        "raw",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "daily_metrics": [
        "local_date",
        "steps",
        "steps_source",
        "kcal_burned",
        "resting_hr",
        "hr_min",
        "hr_avg",
        "hr_max",
        "sleep_minutes",
        "updated_at",
    ],  # noqa: E501
    "depot_values": ["local_date", "value", "created_at", "updated_at"],
    "exercises": [
        "id",
        "name",
        "muscle_group",
        "bodyweight",
        "rep_min",
        "rep_max",
        "weight_step",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "feeds": [
        "id",
        "kind",
        "name",
        "stream",
        "deadline_pattern",
        "area",
        "created_at",
        "updated_at",
        "host",
    ],  # noqa: E501
    "finance_budgets": ["category", "amount", "created_at", "updated_at"],
    "finance_rules": ["id", "pattern", "category", "created_at", "updated_at"],
    "savings_goals": [
        "id",
        "name",
        "target_amount",
        "current_amount",
        "target_date",
        "archived",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "goals": ["id", "metric", "value", "valid_from", "created_at"],
    "habits": ["id", "name", "rule", "sort_order", "archived", "created_at", "updated_at"],
    "integration_state": [
        "name",
        "last_run_at",
        "last_success_at",
        "last_error",
        "stats",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "journal_entries": ["local_date", "mood", "energy", "text", "created_at", "updated_at"],
    "news_interests": ["term", "manual", "weight", "created_at", "updated_at"],
    "news_items": [
        "id",
        "feed",
        "stream",
        "item_key",
        "url",
        "title",
        "summary",
        "published_at",
        "terms",
        "feedback",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "nutrition_meals": [
        "id",
        "source",
        "local_date",
        "meal",
        "kcal",
        "protein_g",
        "carbs_g",
        "fat_g",
        "saturated_fat_g",
        "fiber_g",
        "sugar_g",
        "sodium_mg",
        "potassium_mg",
        "calcium_mg",
        "iron_mg",
        "raw",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "workout_templates": ["id", "name", "exercises", "weekdays", "created_at", "updated_at"],
    "bank_accounts": [
        "id",
        "connection_id",
        "identification_hash",
        "uid",
        "name",
        "iban",
        "currency",
        "balance",
        "balance_at",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "exercise_aliases": ["id", "alias", "exercise_id"],
    "habit_checks": ["habit_id", "local_date"],
    "sleep_sessions": [
        "id",
        "record_id",
        "source_app",
        "start_at",
        "end_at",
        "local_date",
        "in_bed_minutes",
        "asleep_minutes",
        "deep_minutes",
        "light_minutes",
        "rem_minutes",
        "awake_minutes",
        "stages",
    ],  # noqa: E501
    "tasks": [
        "id",
        "title",
        "notes",
        "area_id",
        "tags",
        "priority",
        "status",
        "due_date",
        "due_time",
        "scheduled_date",
        "completed_at",
        "recurrence",
        "recurrence_parent_id",
        "source",
        "external_id",
        "sort_order",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "training_sessions": [
        "id",
        "started_at",
        "workout_name",
        "duration_minutes",
        "health_record_id",
        "source",
        "client_id",
        "ended_at",
        "watch_record_id",
        "activity",
        "hr_avg",
        "hr_max",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "bank_transactions": [
        "id",
        "account_id",
        "external_id",
        "booking_date",
        "amount",
        "currency",
        "counterparty",
        "counterparty_iban",
        "purpose",
        "category",
        "category_source",
        "created_at",
    ],  # noqa: E501
    "emails": [
        "id",
        "account",
        "msg_key",
        "folder",
        "uidvalidity",
        "uid",
        "from_name",
        "from_addr",
        "subject",
        "received_at",
        "seen",
        "bulk",
        "priority",
        "needs_action",
        "category",
        "summary",
        "task_title",
        "triage",
        "triage_error",
        "task_id",
        "dismissed_at",
        "removed_at",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "exercise_sets": [
        "id",
        "session_id",
        "exercise_id",
        "set_index",
        "weight_kg",
        "reps",
        "rpe",
        "rir",
        "raw",
    ],  # noqa: E501
    "notes": [
        "id",
        "title",
        "body",
        "area_id",
        "tags",
        "pinned",
        "archived_at",
        "source",
        "external_id",
        "task_id",
        "created_at",
        "updated_at",
    ],  # noqa: E501
    "task_events": ["id", "task_id", "type", "actor", "payload", "created_at"],
}


def test_exported_tables_and_columns_are_known():
    assert export.columns() == EXPORTED


def test_a_feed_link_leaves_only_its_host(client, session):
    session.add(Feed(kind="calendar", name="ilias", url="https://ilias.example/cal?token=SECRET"))
    session.commit()
    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/export").content))
    raw = archive.read("feeds.json").decode()
    assert "SECRET" not in raw
    [feed] = json.loads(raw)
    assert feed["host"] == "ilias.example" and "url" not in feed


def test_export_has_the_data_but_no_secrets(client, session):
    journal.save(session, local_today(), mood=4, text="gut")
    session.add(BankConnection(aspsp_name="X", aspsp_country="DE", state="st", session_id="sid"))
    session.commit()
    response = client.get("/api/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "compass-export-" in response.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert "journal_entries.json" in names and "manifest.json" in names
    assert not names & {f"{t}.json" for t in export.SKIP_TABLES}
    [entry] = json.loads(archive.read("journal_entries.json"))
    assert entry["mood"] == 4 and entry["text"] == "gut"
    [conn] = json.loads(archive.read("bank_connections.json"))
    assert "session_id" not in conn and "state" not in conn
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["tables"]["journal_entries"] == 1


def test_verify_zip_accepts_valid_export_and_rejects_broken_archives(client, session):
    journal.save(session, local_today(), mood=4, text="gut")
    session.commit()
    raw = client.get("/api/export").content
    counts = export.verify_zip(raw)
    assert counts["journal_entries"] == 1

    import pytest

    with pytest.raises(ValueError, match="not a valid zip"):
        export.verify_zip(b"not a zip")

    # Tamper with a row count in the manifest.
    buf = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(raw), "r") as src,
        zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for name in src.namelist():
            content = src.read(name)
            if name == "manifest.json":
                m = json.loads(content)
                m["tables"]["journal_entries"] = 99
                content = json.dumps(m).encode()
            dst.writestr(name, content)
    with pytest.raises(ValueError, match="manifest says 99"):
        export.verify_zip(buf.getvalue())
