"""Integration tests for the Postgres/pgvector store.

Skipped automatically unless a reachable DATABASE_URL is available (e.g. via
`docker compose up -d`), so the default `pytest` run stays dependency-free.
"""

from __future__ import annotations

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://documind:documind@localhost:5432/documind")


def _database_reachable() -> bool:
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _database_reachable(), reason="Postgres is not reachable; run `docker compose up -d` first")


@pytest.fixture
def store():
    from backend.db.pg_vector_store import PgVectorStore

    instance = PgVectorStore(f"pytest-{uuid.uuid4().hex[:8]}", DATABASE_URL)
    yield instance
    instance.delete()


def test_status_before_save_reports_not_indexed(store):
    assert store.status()["indexed"] is False


def test_save_and_search_roundtrip(store):
    from backend.ingest.chunker import Chunk

    chunks = [
        Chunk(source="a.txt", index=0, text="Cats are small domesticated carnivorous mammals."),
        Chunk(source="a.txt", index=1, text="Dogs are loyal companions descended from wolves."),
    ]
    embeddings = [[1.0, 0.0], [0.0, 1.0]]

    result = store.save(chunks, embeddings, "gemini")
    assert result["indexed"] is True
    assert result["chunks"] == 2

    matches = store.search([0.9, 0.1], limit=1)
    assert matches[0]["text"].startswith("Cats")


def test_search_lexical_uses_postgres_full_text_search(store):
    from backend.ingest.chunker import Chunk

    chunks = [Chunk(source="b.txt", index=0, text="The invoicing workflow requires manager approval.")]
    store.save(chunks, None, "claude_cli")

    matches = store.search_lexical("invoicing manager approval", limit=4)
    assert matches
    assert matches[0]["text"].startswith("The invoicing")


def test_search_lexical_falls_back_to_first_chunk_per_document_when_no_terms_match(store):
    from backend.ingest.chunker import Chunk

    chunks = [
        Chunk(source="a.txt", index=0, text="Completely unrelated passage."),
        Chunk(source="a.txt", index=1, text="A second unrelated passage."),
        Chunk(source="b.txt", index=0, text="Some other document entirely."),
    ]
    store.save(chunks, None, "claude_cli")

    matches = store.search_lexical("xyzzy plugh quux", limit=4)

    assert sorted(match["source"] for match in matches) == ["a.txt", "b.txt"]
    assert all(match["score"] == 0 for match in matches)
    assert next(match for match in matches if match["source"] == "a.txt")["index"] == 0
