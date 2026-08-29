"""Tests for the local JSON-backed vector store."""

import pytest

from backend.db.vector_store import VectorStore
from backend.ingest.chunker import Chunk


def make_chunks(texts: list[str], source: str = "doc.txt") -> list[Chunk]:
    return [Chunk(source=source, index=i, text=text) for i, text in enumerate(texts)]


def test_status_before_any_save_reports_not_indexed(tmp_path):
    store = VectorStore(tmp_path / "index.json")
    status = store.status()

    assert status["indexed"] is False
    assert status["chunks"] == 0
    assert status["documents"] == []


def test_save_and_load_roundtrip(tmp_path):
    store = VectorStore(tmp_path / "index.json")
    store.save(make_chunks(["alpha text", "beta text"]), [[1.0, 0.0], [0.0, 1.0]], "gemini")

    status = store.status()
    assert status["indexed"] is True
    assert status["chunks"] == 2
    assert status["provider"] == "gemini"
    assert status["documents"] == ["doc.txt"]


def test_save_rejects_mismatched_chunk_and_embedding_counts(tmp_path):
    store = VectorStore(tmp_path / "index.json")
    with pytest.raises(ValueError):
        store.save(make_chunks(["one", "two"]), [[1.0, 0.0]], "gemini")


def test_search_ranks_by_cosine_similarity(tmp_path):
    store = VectorStore(tmp_path / "index.json")
    chunks = make_chunks(["about cats", "about dogs", "about cars"])
    store.save(chunks, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], "gemini")

    results = store.search([0.9, 0.1, 0.0], limit=2)

    assert len(results) == 2
    assert results[0]["text"] == "about cats"
    assert results[0]["score"] >= results[1]["score"]


def test_search_lexical_ranks_by_term_overlap(tmp_path):
    store = VectorStore(tmp_path / "index.json")
    chunks = make_chunks(
        [
            "the invoicing workflow requires manager approval",
            "the weather today is sunny and warm",
        ]
    )
    store.save(chunks, None, "claude_cli")

    results = store.search_lexical("invoicing manager approval", limit=4)

    assert len(results) == 1
    assert results[0]["text"].startswith("the invoicing")
    assert results[0]["score"] == 1.0


def test_search_lexical_falls_back_to_first_chunk_per_document_when_no_terms_match(tmp_path):
    store = VectorStore(tmp_path / "index.json")
    store.save(
        make_chunks(["completely unrelated passage", "a second unrelated passage"], source="a.txt")
        + make_chunks(["some other document entirely"], source="b.txt"),
        None,
        "claude_cli",
    )

    results = store.search_lexical("xyzzy plugh quux", limit=4)

    assert [result["source"] for result in results] == ["a.txt", "b.txt"]
    assert results[0]["index"] == 0
    assert all(result["score"] == 0 for result in results)


def test_search_on_empty_store_returns_no_matches(tmp_path):
    store = VectorStore(tmp_path / "index.json")

    assert store.search([1.0, 0.0], limit=4) == []
    assert store.search_lexical("anything", limit=4) == []
