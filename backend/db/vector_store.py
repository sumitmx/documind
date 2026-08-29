"""A compact, local vector index persisted as JSON for a single-user portal."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from backend.config import INDEX_FILE
from backend.ingest.chunker import Chunk


def _first_chunk_per_source(records: list[dict[str, object]]) -> list[dict[str, object]]:
    earliest: dict[str, dict[str, object]] = {}
    for record in records:
        source = record["source"]
        if source not in earliest or record["index"] < earliest[source]["index"]:
            earliest[source] = record
    return [earliest[source] for source in sorted(earliest)]


class VectorStore:
    def __init__(self, path: Path = INDEX_FILE) -> None:
        self.path = path

    def load(self) -> dict[str, object]:
        if not self.path.exists():
            return {"created_at": None, "chunks": []}
        with self.path.open(encoding="utf-8") as file:
            return json.load(file)

    def save(self, chunks: list[Chunk], embeddings: list[list[float]] | None, provider: str) -> dict[str, object]:
        if embeddings is not None and len(chunks) != len(embeddings):
            raise ValueError("Each text chunk must have exactly one embedding.")

        payload: dict[str, object] = {
            "created_at": datetime.now(UTC).isoformat(),
            "provider": provider,
            "chunks": [
                {
                    "source": chunk.source,
                    "index": chunk.index,
                    "text": chunk.text,
                    "embedding": embeddings[position] if embeddings is not None else None,
                }
                for position, chunk in enumerate(chunks)
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False)
        temporary.replace(self.path)
        return payload

    def search(self, query_embedding: list[float], limit: int = 4) -> list[dict[str, object]]:
        records = self.load().get("chunks", [])
        if not records:
            return []

        matrix = np.asarray([record["embedding"] for record in records], dtype=np.float32)
        query = np.asarray(query_embedding, dtype=np.float32)
        denominator = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
        scores = (matrix @ query) / np.maximum(denominator, 1e-12)
        selected = np.argsort(scores)[::-1][:limit]
        return [
            {
                "source": records[position]["source"],
                "index": records[position]["index"],
                "text": records[position]["text"],
                "score": round(float(scores[position]), 3),
            }
            for position in selected
        ]

    def search_lexical(self, query: str, limit: int = 4) -> list[dict[str, object]]:
        """Rank chunks locally for the Claude CLI path, without an embedding API."""
        records = self.load().get("chunks", [])
        if not records:
            return []
        terms = set(re.findall(r"[a-z0-9]{2,}", query.lower()))

        scored = []
        for record in records:
            text = str(record["text"]).lower()
            # A relevance percentage represents unique query terms present,
            # rather than how often a term repeats in a passage.
            matched_terms = sum(1 for term in terms if term in text)
            if matched_terms:
                scored.append((matched_terms / len(terms), record))
        scored.sort(key=lambda item: item[0], reverse=True)

        if not scored:
            # No keyword overlap at all (a greeting, or a question that only shares
            # stop words with the library) - fall back to the opening chunk of each
            # document, so a vague first question still has something to work from.
            scored = [(0.0, record) for record in _first_chunk_per_source(records)]

        return [
            {"source": record["source"], "index": record["index"], "text": record["text"], "score": round(score, 3)}
            for score, record in scored[:limit]
        ]

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)

    def status(self) -> dict[str, object]:
        payload = self.load()
        chunks = payload.get("chunks", [])
        documents = sorted({chunk["source"] for chunk in chunks})
        return {
            "indexed": bool(chunks),
            "chunks": len(chunks),
            "documents": documents,
            "created_at": payload.get("created_at"),
            "provider": payload.get("provider"),
        }
