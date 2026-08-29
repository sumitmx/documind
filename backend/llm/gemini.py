"""Small Gemini adapter used by indexing and question answering."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator

from google import genai
from google.genai import types
from google.genai.errors import APIError

from backend.config import CHAT_MODEL, EMBEDDING_DIMENSIONS, EMBEDDING_MODEL

EMBED_BATCH_SIZE = 100  # Gemini's embed_content endpoint rejects more than 100 texts per call.


def _client() -> genai.Client:
    if not gemini_configured():
        raise RuntimeError("GEMINI_API_KEY is not configured. Add it to .env before indexing or chatting.")
    return genai.Client()


def gemini_configured() -> bool:
    """Report configuration without exposing the key itself."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return bool(key and key != "your-key-here")


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """Create one normalized-length vector for each supplied piece of text."""
    values = list(texts)
    if not values:
        return []

    # Keep the client strongly referenced for the full request. Calling through
    # a temporary client can let its cleanup close the underlying HTTP client
    # before the model call finishes.
    client = _client()
    try:
        results: list[list[float]] = []
        for start in range(0, len(values), EMBED_BATCH_SIZE):
            batch = values[start : start + EMBED_BATCH_SIZE]
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=batch,
                config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
            )
            results.extend(embedding.values for embedding in response.embeddings)
        return results
    except APIError as error:
        raise RuntimeError(f"Gemini embedding request failed: {error.message or error}") from error


def _build_prompt(question: str, context: list[dict[str, object]]) -> str:
    excerpts = "\n\n".join(
        f"[Source {item['source']} — chunk {item['index']}]\n{item['text']}"
        for item in context
    )
    return f"""You are DocuMind, a friendly, precise document assistant.

If the question is a greeting, thanks, or casual small talk rather than a real
question about the documents, skip the formatting below and reply warmly in
one short, natural sentence or two, inviting the user to ask about the
indexed material — never treat small talk like a failed lookup.

Otherwise, answer the question using only the source excerpts below. If the
answer is not contained in them, say so plainly. Do not invent facts or
sources. Keep the answer concise, and refer to source filenames when helpful.
Format the answer as polished Markdown: begin with a `##` answer heading, use
`###` subheadings for distinct topics, and use concise bullet or numbered
lists where they help. Use fenced code blocks for code. Do not expose chunk
numbers or call the material "excerpts" in the answer.

Question: {question}

Source excerpts:
{excerpts}
"""


def answer_question(question: str, context: list[dict[str, object]]) -> str:
    """Answer using retrieved chunks only; citations are rendered by the caller."""
    client = _client()
    try:
        response = client.models.generate_content(model=CHAT_MODEL, contents=_build_prompt(question, context))
    except APIError as error:
        raise RuntimeError(f"Gemini request failed: {error.message or error}") from error
    return (response.text or "I could not produce an answer from the indexed documents.").strip()


def stream_answer_question(question: str, context: list[dict[str, object]]) -> Iterator[str]:
    """Yield answer text incrementally as Gemini generates it."""
    client = _client()
    try:
        for chunk in client.models.generate_content_stream(model=CHAT_MODEL, contents=_build_prompt(question, context)):
            if chunk.text:
                yield chunk.text
    except APIError as error:
        raise RuntimeError(f"Gemini request failed: {error.message or error}") from error
