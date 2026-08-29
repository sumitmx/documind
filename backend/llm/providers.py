"""Provider-neutral routing for DocuMind's embedding and answer calls."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from backend.llm import gemini
from backend.llm import claude_cli
from backend.llm import openai_client

PROVIDER_LABELS = {"gemini": "Gemini", "openai": "OpenAI GPT", "claude_cli": "Claude Pro (CLI)"}


def validate_provider(provider: str) -> str:
    if provider not in PROVIDER_LABELS:
        raise ValueError("Choose Gemini, OpenAI GPT, or Claude Pro (CLI).")
    return provider


def provider_configured(provider: str) -> bool:
    provider = validate_provider(provider)
    if provider == "gemini":
        return gemini.gemini_configured()
    if provider == "openai":
        return openai_client.openai_configured()
    return claude_cli.claude_cli_available()


def configured_providers() -> dict[str, bool]:
    return {name: provider_configured(name) for name in PROVIDER_LABELS}


def embed_texts(provider: str, texts: Iterable[str]) -> list[list[float]]:
    provider = validate_provider(provider)
    if provider == "gemini":
        return gemini.embed_texts(texts)
    if provider == "openai":
        return openai_client.embed_texts(texts)
    raise ValueError("Claude CLI uses local lexical retrieval and does not create embeddings.")


def answer_question(provider: str, question: str, context: list[dict[str, object]]) -> str:
    provider = validate_provider(provider)
    if provider == "gemini":
        return gemini.answer_question(question, context)
    if provider == "openai":
        return openai_client.answer_question(question, context)
    return claude_cli.answer_question(question, context)


def stream_answer_question(provider: str, question: str, context: list[dict[str, object]]) -> Iterator[str]:
    provider = validate_provider(provider)
    if provider == "gemini":
        yield from gemini.stream_answer_question(question, context)
    elif provider == "openai":
        yield from openai_client.stream_answer_question(question, context)
    else:
        yield from claude_cli.stream_answer_question(question, context)
