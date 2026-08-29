"""OpenAI adapter for DocuMind's GPT answer and embedding option."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator

import backend.config  # noqa: F401  (loads .env once at import time)

DEFAULT_CHAT_MODEL = "gpt-4.1-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def openai_configured() -> bool:
    """Report configuration without exposing the secret itself."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key and key != "your-key-here")


def _client():
    if not openai_configured():
        raise RuntimeError("OPENAI_API_KEY is not configured. Add it to .env before using OpenAI GPT.")
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError("OpenAI support is not installed. Run .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt.") from error
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _chat_model() -> str:
    return os.getenv("OPENAI_CHAT_MODEL", DEFAULT_CHAT_MODEL).strip() or DEFAULT_CHAT_MODEL


def _embedding_model() -> str:
    return os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    values = list(texts)
    if not values:
        return []
    client = _client()
    response = client.embeddings.create(model=_embedding_model(), input=values)
    return [item.embedding for item in response.data]


INSTRUCTIONS = (
    "You are DocuMind, a friendly, precise document assistant. If the question is a greeting, "
    "thanks, or casual small talk rather than a real question about the documents, skip the "
    "formatting below and reply warmly in one short, natural sentence or two, inviting the user "
    "to ask about the indexed material — never treat small talk like a failed lookup. Otherwise, "
    "answer only from the supplied source excerpts. If the answer is not contained in them, say so "
    "plainly. Do not invent facts or sources. Keep the answer concise and refer to source filenames "
    "when helpful. Format the answer as polished Markdown: begin with a ## answer heading, use ### "
    "subheadings for distinct topics, and use concise bullet or numbered lists where they help. Use "
    "fenced code blocks for code. Do not expose chunk numbers or call the material excerpts in the answer."
)


def _build_input(question: str, context: list[dict[str, object]]) -> str:
    excerpts = "\n\n".join(
        f"[Source {item['source']} — chunk {item['index']}]\n{item['text']}"
        for item in context
    )
    return f"Question: {question}\n\nSource excerpts:\n{excerpts}"


def answer_question(question: str, context: list[dict[str, object]]) -> str:
    client = _client()
    response = client.responses.create(
        model=_chat_model(),
        instructions=INSTRUCTIONS,
        input=_build_input(question, context),
    )
    return (response.output_text or "I could not produce an answer from the indexed documents.").strip()


def stream_answer_question(question: str, context: list[dict[str, object]]) -> Iterator[str]:
    """Yield answer text incrementally as GPT generates it."""
    client = _client()
    with client.responses.stream(
        model=_chat_model(),
        instructions=INSTRUCTIONS,
        input=_build_input(question, context),
    ) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                yield event.delta
        stream.get_final_response()
