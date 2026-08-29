"""Tests for the deterministic evidence-grounding evaluator."""

from backend.evaluation import evaluate_grounding


def test_high_overlap_and_high_retrieval_scores_strong():
    sources = [
        {"text": "The invoicing workflow requires manager approval before submission.", "score": 0.95},
        {"text": "Approval requests route through the finance queue automatically.", "score": 0.9},
    ]
    result = evaluate_grounding(
        "What does the invoicing workflow require?",
        "The invoicing workflow requires manager approval before submission to the finance queue.",
        sources,
    )

    assert result["label"] == "Strong"
    assert result["score"] >= 80
    assert result["source_count"] == 2


def test_no_term_overlap_scores_limited():
    sources = [{"text": "Completely unrelated passage about kitchen appliances.", "score": 0.4}]
    result = evaluate_grounding("What is the invoicing policy?", "I have no idea about that topic.", sources)

    assert result["label"] == "Limited"


def test_no_sources_yields_zero_score():
    result = evaluate_grounding("Any question", "Any answer", [])

    assert result["source_count"] == 0
    assert result["score"] == 0
    assert result["label"] == "Limited"


def test_out_of_range_retrieval_score_is_clamped_before_use():
    sources = [{"text": "identical text identical text", "score": 5.0}]
    result = evaluate_grounding("identical text", "identical text", sources)

    assert result["score"] == 100
    assert result["label"] == "Strong"


def test_description_notes_it_is_not_a_factual_guarantee():
    result = evaluate_grounding("q", "a", [])
    assert "not a guarantee" in result["description"].lower()
