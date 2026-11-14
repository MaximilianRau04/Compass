import io
import json
import zipfile

from app.models.finance import BankConnection
from app.services import export, journal
from app.services.clock import local_today


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
