from datetime import date

from app.config import get_settings
from app.models.journal import JournalEntry
from app.models.notes import Note
from app.schemas.notes import NoteCreate
from app.services import embeddings, journal, notes
from app.services import search as search_service


def test_parse_response_supports_openai_and_ollama_shapes():
    assert embeddings.parse_response({"data": [{"embedding": [0.1, 0.2]}]}) == [0.1, 0.2]
    assert embeddings.parse_response({"embeddings": [[0.3, 0.4]]}) == [0.3, 0.4]
    assert embeddings.parse_response({"embedding": [0.5, 0.6]}) == [0.5, 0.6]
    assert embeddings.parse_response({}) is None


def test_semantic_search_finds_related_notes_without_word_overlap(session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_url", "http://embed.local/v1/embeddings")
    monkeypatch.setattr(settings, "embedding_model", "test-embed")

    vectors = {
        "bike": [1.0, 0.0, 0.0],
        "cycling": [0.95, 0.1, 0.0],
        "pasta": [0.0, 1.0, 0.0],
    }

    def fake_embed(text: str, timeout: float = 0):
        low = text.lower()
        for key, vec in vectors.items():
            if key in low:
                return vec
        return [0.0, 0.0, 1.0]

    monkeypatch.setattr(embeddings, "embed", fake_embed)

    n_bike = notes.create_note(
        session, NoteCreate(title="Bike maintenance", body="Oil the chain and check tire pressure.")
    )
    n_pasta = notes.create_note(
        session, NoteCreate(title="Pasta recipe", body="Boil salted water and add basil.")
    )
    session.flush()
    assert n_bike.embedding == [1.0, 0.0, 0.0]
    assert n_pasta.embedding == [0.0, 1.0, 0.0]

    # "cycling" shares no words with "Bike maintenance", yet pgvector cosine distance finds it.
    hits = notes.search(session, query="cycling")
    assert [h.note.id for h in hits] == [n_bike.id]


def test_backfill_populates_missing_note_and_journal_embeddings(session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_url", "")
    monkeypatch.setattr(settings, "embedding_model", "")

    note = notes.create_note(
        session, NoteCreate(title="Old note", body="Written before embeddings")
    )
    entry = journal.save(session, date(2026, 11, 1), mood=4, text="Good run in the morning")
    session.flush()
    assert note.embedding is None and entry.embedding is None

    monkeypatch.setattr(settings, "embedding_url", "http://embed.local/api/embed")
    monkeypatch.setattr(settings, "embedding_model", "nomic-embed-text")
    monkeypatch.setattr(embeddings, "embed", lambda text, timeout=0: [0.25, 0.75, 0.0])

    result = embeddings.backfill(session)
    assert result == {"notes": 1, "journal": 1}
    assert session.get(Note, note.id).embedding == [0.25, 0.75, 0.0]
    assert session.get(JournalEntry, date(2026, 11, 1)).embedding == [0.25, 0.75, 0.0]


def fake_vectors(monkeypatch, vectors: dict[str, list[float]]):
    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_url", "http://embed.local/v1/embeddings")
    monkeypatch.setattr(settings, "embedding_model", "test-embed")

    def fake_embed(text: str, timeout: float = 0):
        low = text.lower()
        return next((vec for key, vec in vectors.items() if key in low), [0.0, 0.0, 1.0])

    monkeypatch.setattr(embeddings, "embed", fake_embed)


def test_journal_search_by_words_and_by_meaning(client, session, monkeypatch):
    fake_vectors(monkeypatch, {"bike": [1.0, 0.0, 0.0], "cycling": [0.95, 0.1, 0.0]})
    journal.save(session, date(2026, 11, 2), text="Long bike tour to the lake")
    journal.save(session, date(2026, 11, 3), text="Cooked pasta with friends")
    journal.save(session, date(2026, 11, 4), text="Friends came over for dinner")
    session.flush()

    by_words = journal.search(session, "friends")
    assert [f.entry.local_date for f in by_words] == [date(2026, 11, 4), date(2026, 11, 3)]
    assert [f.entry.local_date for f in journal.search(session, "cycling")] == [date(2026, 11, 2)]

    found = client.get("/api/search", params={"q": "cycling"}).json()
    assert [(j["local_date"], j["snippet"]) for j in found["journal"]] == [
        ("2026-11-02", "Long bike tour to the lake")
    ]
    assert search_service.search(session, "pasta").journal[0].entry.local_date == date(2026, 11, 3)


def test_note_search_skips_vectors_of_another_model(session, monkeypatch):
    fake_vectors(monkeypatch, {"bike": [1.0, 0.0], "cycling": [0.95, 0.1, 0.0]})
    notes.create_note(session, NoteCreate(title="Bike maintenance", body="Oil the chain."))
    session.flush()
    # The stored vector has 2 dims, the query 3: no hit, and no error from pgvector.
    assert notes.search(session, query="cycling") == []


def test_backfill_redoes_vectors_of_another_size(session, monkeypatch):
    fake_vectors(monkeypatch, {"bike": [1.0, 0.0]})
    note = notes.create_note(session, NoteCreate(title="Bike", body="Oil the chain."))
    session.flush()
    fake_vectors(monkeypatch, {"bike": [1.0, 0.0, 0.0]})
    assert embeddings.backfill(session) == {"notes": 1, "journal": 0}
    assert note.embedding == [1.0, 0.0, 0.0]
    assert embeddings.backfill(session) == {"notes": 0, "journal": 0}
    assert embeddings.backfill(session, everything=True) == {"notes": 1, "journal": 0}


def test_failed_request_pauses_embedding(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_url", "http://127.0.0.1:9/v1/embeddings")
    monkeypatch.setattr(settings, "embedding_model", "test-embed")
    monkeypatch.setattr(embeddings, "_down_until", 0.0)
    calls = []

    def refuse(*args, **kwargs):
        calls.append(1)
        raise OSError("connection refused")

    monkeypatch.setattr(embeddings.urllib.request, "urlopen", refuse)
    assert embeddings.embed_query("hello") is None
    assert embeddings.embed_query("hello again") is None
    assert len(calls) == 1
