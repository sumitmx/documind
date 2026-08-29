"""Deterministic evidence-grounding evaluation for RAG answers."""

from __future__ import annotations

import re

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or",
    "that", "the", "this", "to", "with", "you", "your", "we", "was", "were", "will", "would", "can", "could",
}


def _terms(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]{3,}", text.lower()) if word not in STOP_WORDS}


def _coverage(needles: set[str], haystack: set[str]) -> float:
    return len(needles & haystack) / len(needles) if needles else 1.0


def evaluate_grounding(question: str, answer: str, sources: list[dict[str, object]]) -> dict[str, object]:
    """Estimate evidence alignment without presenting it as factual certainty.

    It uses no additional model call: relevance comes from retrieval scores and
    support comes from lexical overlap between the response and its passages.
    """
    source_text = "\n".join(str(source.get("text", "")) for source in sources)
    source_terms = _terms(source_text)
    retrieval_scores = [max(0.0, min(1.0, float(source.get("score", 0)))) for source in sources]
    average_retrieval = sum(retrieval_scores) / len(retrieval_scores) if retrieval_scores else 0.0
    top_retrieval = max(retrieval_scores, default=0.0)
    retrieval_quality = (top_retrieval * 0.6) + (average_retrieval * 0.4)
    question_coverage = _coverage(_terms(question), source_terms)
    answer_coverage = _coverage(_terms(answer), source_terms)
    score = round(100 * ((retrieval_quality * 0.45) + (question_coverage * 0.25) + (answer_coverage * 0.30)))
    score = max(0, min(100, score))
    label = "Strong" if score >= 80 else "Moderate" if score >= 60 else "Limited"
    return {
        "score": score,
        "label": label,
        "source_count": len(sources),
        "description": "Evidence-grounding confidence, not a guarantee of factual accuracy.",
    }
