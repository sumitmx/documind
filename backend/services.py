"""Application workflows joining ingestion, embeddings, storage, and retrieval."""

from __future__ import annotations

from collections.abc import Iterator

from backend.config import RETRIEVAL_COUNT
from backend.db.store import get_vector_store
from backend.evaluation import evaluate_grounding
from backend.ingest.chunker import chunk_document
from backend.ingest.loader import load_docs
from backend.llm.providers import answer_question, embed_texts, provider_configured, stream_answer_question, validate_provider
from backend.projects import GENERAL_PROJECT_ID, Project, delete_project


def project_status(project: Project) -> dict[str, object]:
    return get_vector_store(project).status()


def remove_project(project: Project) -> None:
    if project.identifier == GENERAL_PROJECT_ID:
        raise ValueError("The general library can't be removed.")
    get_vector_store(project).delete()
    delete_project(project.identifier)


def rebuild_index(project: Project, provider: str) -> dict[str, object]:
    provider = validate_provider(provider)
    if not provider_configured(provider):
        raise ValueError(f"Configure the {provider.title()} API key before indexing.")
    documents = load_docs(project.documents_dir)
    if not documents:
        raise ValueError("No supported documents were found in this project. Upload a PDF, Markdown, or text file first.")
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    embeddings = None if provider == "claude_cli" else embed_texts(provider, (chunk.text for chunk in chunks))
    store = get_vector_store(project)
    store.save(chunks, embeddings, provider)
    return store.status()


def _retrieve(project: Project, question: str, provider: str) -> list[dict[str, object]]:
    provider = validate_provider(provider)
    store = get_vector_store(project)
    if not store.status()["indexed"]:
        raise ValueError("Your library has not been indexed yet. Select Index library first.")
    index_provider = store.status()["provider"]
    if index_provider != provider:
        raise ValueError(f"Your library is indexed with {index_provider}. Select that provider or reindex with {provider}.")
    matches = store.search_lexical(question, RETRIEVAL_COUNT) if provider == "claude_cli" else store.search(embed_texts(provider, [question])[0], RETRIEVAL_COUNT)
    if not matches:
        raise ValueError("No relevant document passages were found.")
    return matches


def ask(project: Project, question: str, provider: str) -> dict[str, object]:
    provider = validate_provider(provider)
    matches = _retrieve(project, question, provider)
    answer = answer_question(provider, question, matches)
    return {"answer": answer, "sources": matches, "evaluation": evaluate_grounding(question, answer, matches)}


def ask_stream(project: Project, question: str, provider: str) -> Iterator[tuple[str, object]]:
    """Yield ("sources", matches), then ("token", text) deltas, then ("done", result)."""
    provider = validate_provider(provider)
    matches = _retrieve(project, question, provider)
    yield "sources", matches

    parts: list[str] = []
    for token in stream_answer_question(provider, question, matches):
        parts.append(token)
        yield "token", token

    answer = "".join(parts).strip() or "I could not produce an answer from the indexed documents."
    result = {"answer": answer, "sources": matches, "evaluation": evaluate_grounding(question, answer, matches)}
    yield "done", result
