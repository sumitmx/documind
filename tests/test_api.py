"""End-to-end tests against the FastAPI app, with LLM calls mocked."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

import backend.projects as projects_module
import backend.services as services_module
from backend.api.server import app


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    # Force the JSON store regardless of the developer's shell environment, so
    # these tests stay hermetic even if DATABASE_URL happens to be exported.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    monkeypatch.setattr(projects_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(projects_module, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(projects_module, "INDEX_FILE", tmp_path / "data" / "index.json")


@pytest.fixture(autouse=True)
def mock_providers(monkeypatch):
    monkeypatch.setattr(services_module, "provider_configured", lambda provider: True)
    monkeypatch.setattr(services_module, "embed_texts", lambda provider, texts: [[1.0, 0.0] for _ in texts])
    monkeypatch.setattr(services_module, "answer_question", lambda provider, question, context: f"Answer: {question}")
    monkeypatch.setattr(
        services_module,
        "stream_answer_question",
        lambda provider, question, context: iter(f"Answer: {question}".split(" ")),
    )


@pytest.fixture
def client():
    return TestClient(app)


def upload_sample_document(client: TestClient, project_id: str) -> None:
    content = base64.b64encode(b"DocuMind answers grounded questions about your documents.").decode()
    response = client.post(f"/api/projects/{project_id}/documents", json={"name": "notes.txt", "content": content})
    assert response.status_code == 201


def test_list_projects_includes_general(client):
    response = client.get("/api/projects")

    assert response.status_code == 200
    identifiers = [project["id"] for project in response.json()["projects"]]
    assert "general" in identifiers


def test_create_project_then_it_appears_in_the_list(client):
    response = client.post("/api/projects", json={"name": "Interview Demo"})

    assert response.status_code == 201
    project_id = response.json()["project"]["id"]
    assert project_id == "interview-demo"

    listing = client.get("/api/projects").json()
    assert any(project["id"] == project_id for project in listing["projects"])


def test_create_project_rejects_blank_name(client):
    response = client.post("/api/projects", json={"name": "   "})

    assert response.status_code == 400
    assert "error" in response.json()


def test_upload_document_rejects_disallowed_extension(client):
    content = base64.b64encode(b"echo hi").decode()
    response = client.post("/api/projects/general/documents", json={"name": "script.sh", "content": content})

    assert response.status_code == 400


def test_upload_document_rejects_invalid_base64(client):
    response = client.post("/api/projects/general/documents", json={"name": "notes.txt", "content": "not-base64!!"})

    assert response.status_code == 400


def test_unknown_project_returns_an_error(client):
    response = client.get("/api/projects/does-not-exist/status")

    assert response.status_code == 400


def test_upload_then_index_then_ask_end_to_end(client):
    upload_sample_document(client, "general")

    index_response = client.post("/api/projects/general/index", json={"provider": "gemini"})
    assert index_response.status_code == 200
    assert index_response.json()["indexed"] is True

    chat = client.post("/api/projects/general/chats", json={}).json()["chat"]
    message_response = client.post(
        f"/api/projects/general/chats/{chat['id']}/messages",
        json={"question": "What does DocuMind do?", "provider": "gemini"},
    )

    assert message_response.status_code == 200
    body = message_response.text
    assert "event: token" in body
    assert "event: done" in body

    stored_chat = client.get(f"/api/projects/general/chats/{chat['id']}").json()["chat"]
    assert len(stored_chat["messages"]) == 2


def test_ask_before_indexing_streams_an_error_event(client):
    chat = client.post("/api/projects/general/chats", json={}).json()["chat"]

    response = client.post(
        f"/api/projects/general/chats/{chat['id']}/messages",
        json={"question": "Anything?", "provider": "gemini"},
    )

    assert response.status_code == 200
    assert "event: error" in response.text


def test_empty_question_is_rejected_before_streaming_starts(client):
    chat = client.post("/api/projects/general/chats", json={}).json()["chat"]

    response = client.post(
        f"/api/projects/general/chats/{chat['id']}/messages",
        json={"question": "   ", "provider": "gemini"},
    )

    assert response.status_code == 400
