"""Integration tests for ingest -> index -> retrieve -> answer, with LLM calls mocked."""

import pytest

import backend.services as services
from backend.projects import Project


@pytest.fixture
def project(tmp_path):
    documents_dir = tmp_path / "documents"
    documents_dir.mkdir()
    (documents_dir / "notes.txt").write_text(
        "DocuMind indexes project documents and answers grounded questions about them.",
        encoding="utf-8",
    )
    return Project(identifier="test", name="Test", documents_dir=documents_dir, index_file=tmp_path / "index.json")


@pytest.fixture(autouse=True)
def mock_providers(monkeypatch):
    # Force the JSON store regardless of the developer's shell environment, so
    # these tests stay hermetic even if DATABASE_URL happens to be exported.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(services, "provider_configured", lambda provider: True)
    monkeypatch.setattr(services, "embed_texts", lambda provider, texts: [[1.0, 0.0] for _ in texts])
    monkeypatch.setattr(services, "answer_question", lambda provider, question, context: f"Answer: {question}")
    monkeypatch.setattr(
        services,
        "stream_answer_question",
        lambda provider, question, context: iter([f"Answer: {question}"]),
    )


def test_rebuild_index_populates_the_store(project):
    result = services.rebuild_index(project, "gemini")

    assert result["indexed"] is True
    assert result["chunks"] >= 1
    assert result["provider"] == "gemini"


def test_rebuild_index_requires_documents(tmp_path):
    project = Project(identifier="empty", name="Empty", documents_dir=tmp_path / "documents", index_file=tmp_path / "index.json")
    project.documents_dir.mkdir()

    with pytest.raises(ValueError, match="No supported documents"):
        services.rebuild_index(project, "gemini")


def test_rebuild_index_requires_provider_configuration(project, monkeypatch):
    monkeypatch.setattr(services, "provider_configured", lambda provider: False)

    with pytest.raises(ValueError, match="Configure the"):
        services.rebuild_index(project, "gemini")


def test_ask_requires_indexing_first(project):
    with pytest.raises(ValueError, match="not been indexed"):
        services.ask(project, "What does DocuMind do?", "gemini")


def test_ask_returns_answer_sources_and_evaluation(project):
    services.rebuild_index(project, "gemini")

    result = services.ask(project, "What does DocuMind do?", "gemini")

    assert result["answer"] == "Answer: What does DocuMind do?"
    assert len(result["sources"]) >= 1
    assert "score" in result["evaluation"]


def test_ask_rejects_provider_mismatch_with_the_index(project):
    services.rebuild_index(project, "gemini")

    with pytest.raises(ValueError, match="indexed with gemini"):
        services.ask(project, "What does DocuMind do?", "openai")


def test_ask_stream_yields_sources_then_tokens_then_done(project):
    services.rebuild_index(project, "gemini")

    events = list(services.ask_stream(project, "What does DocuMind do?", "gemini"))
    kinds = [kind for kind, _ in events]

    assert kinds[0] == "sources"
    assert kinds[-1] == "done"
    assert "token" in kinds
    assert events[-1][1]["answer"] == "Answer: What does DocuMind do?"
