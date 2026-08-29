"""FastAPI server for the DocuMind portal, with SSE-streamed chat answers."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import FRONTEND_DIR
from backend.conversations import ConversationStore
from backend.llm.providers import configured_providers, validate_provider
from backend.projects import Project, create_project, get_project, list_projects, project_summary
from backend.services import ask_stream, project_status, rebuild_index, remove_project

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_QUESTION_CHARS = 4000
ALLOWED_SUFFIXES = {".pdf", ".md", ".txt"}


class CreateProjectRequest(BaseModel):
    name: str = ""


class IndexRequest(BaseModel):
    provider: str = "gemini"


class MessageRequest(BaseModel):
    question: str = ""
    provider: str = "gemini"


class DocumentRequest(BaseModel):
    name: str = ""
    content: str = ""


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies before they are read into memory."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_BYTES * 2:
            return JSONResponse(status_code=413, content={"error": "The request body is too large."})
        return await call_next(request)


app = FastAPI(title="DocuMind Portal")
app.add_middleware(MaxBodySizeMiddleware)


@app.exception_handler(ValueError)
async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(RuntimeError)
async def handle_runtime_error(request: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": str(exc)})


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _library_files(directory: Path) -> list[dict[str, object]]:
    if not directory.exists():
        return []
    return [
        {"name": file.name, "size": file.stat().st_size}
        for file in sorted(directory.iterdir())
        if file.is_file() and file.suffix.lower() in ALLOWED_SUFFIXES
    ]


def _project_payload(project: Project) -> dict[str, object]:
    status = project_status(project)
    return status | {
        "project": {"id": project.identifier, "name": project.name},
        "library": _library_files(project.documents_dir),
        "providers": configured_providers(),
    }


def _projects_payload() -> list[dict[str, object]]:
    summaries = []
    for project in list_projects():
        status = project_status(project)
        summaries.append(project_summary(project, int(status["chunks"]), bool(status["indexed"]), status["provider"]))
    return summaries


def _save_document(payload: DocumentRequest, project: Project) -> dict[str, object]:
    original_name = Path(payload.name).name
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", original_name)
    if not safe_name or Path(safe_name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("Only PDF, Markdown, and text files can be uploaded.")
    try:
        content = base64.b64decode(payload.content, validate=True)
    except ValueError as error:
        raise ValueError("The uploaded document was invalid.") from error
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Documents must be between 1 byte and 25 MB.")

    project.documents_dir.mkdir(parents=True, exist_ok=True)
    destination = project.documents_dir / safe_name
    stem, suffix, counter = destination.stem, destination.suffix, 2
    while destination.exists():
        destination = project.documents_dir / f"{stem} ({counter}){suffix}"
        counter += 1
    destination.write_bytes(content)
    return _project_payload(project) | {"message": f"Added {destination.name}. Select Index library to make it searchable."}


@app.get("/api/projects")
def list_projects_route() -> dict[str, object]:
    return {"projects": _projects_payload()}


@app.post("/api/projects", status_code=201)
def create_project_route(payload: CreateProjectRequest) -> dict[str, object]:
    project = create_project(payload.name)
    return _project_payload(project) | {"projects": _projects_payload()}


@app.get("/api/projects/{project_id}/status")
def project_status_route(project_id: str) -> dict[str, object]:
    return _project_payload(get_project(project_id))


@app.post("/api/projects/{project_id}/index")
def index_route(project_id: str, payload: IndexRequest) -> dict[str, object]:
    project = get_project(project_id)
    provider = validate_provider(payload.provider)
    return _project_payload(project) | rebuild_index(project, provider)


@app.delete("/api/projects/{project_id}")
def delete_project_route(project_id: str) -> dict[str, object]:
    remove_project(get_project(project_id))
    return {"projects": _projects_payload()}


@app.post("/api/projects/{project_id}/documents", status_code=201)
def upload_document_route(project_id: str, payload: DocumentRequest) -> dict[str, object]:
    return _save_document(payload, get_project(project_id))


@app.get("/api/projects/{project_id}/chats")
def list_chats_route(project_id: str) -> dict[str, object]:
    return {"chats": ConversationStore(get_project(project_id)).list()}


@app.post("/api/projects/{project_id}/chats", status_code=201)
def create_chat_route(project_id: str) -> dict[str, object]:
    store = ConversationStore(get_project(project_id))
    chat = store.create()
    return {"chat": chat, "chats": store.list()}


@app.get("/api/projects/{project_id}/chats/{chat_id}")
def get_chat_route(project_id: str, chat_id: str) -> dict[str, object]:
    return {"chat": ConversationStore(get_project(project_id)).get(chat_id)}


@app.post("/api/projects/{project_id}/chats/{chat_id}/messages")
def send_message_route(project_id: str, chat_id: str, payload: MessageRequest) -> StreamingResponse:
    project = get_project(project_id)
    question = payload.question.strip()
    if not question:
        raise ValueError("Enter a question before sending it.")
    if len(question) > MAX_QUESTION_CHARS:
        raise ValueError("Questions must be 4,000 characters or fewer.")
    provider = validate_provider(payload.provider)
    store = ConversationStore(project)

    def event_stream():
        try:
            result: dict[str, object] = {}
            for kind, value in ask_stream(project, question, provider):
                if kind == "sources":
                    yield _sse("sources", {"sources": value})
                elif kind == "token":
                    yield _sse("token", {"text": value})
                elif kind == "done":
                    result = value
            chat = store.append_exchange(chat_id, question, str(result["answer"]), result["sources"], result["evaluation"])
            yield _sse("done", result | {"chat": chat, "chats": store.list()})
        except (ValueError, RuntimeError) as error:
            yield _sse("error", {"error": str(error)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


def main() -> None:
    import uvicorn

    print("DocuMind portal is available at http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
