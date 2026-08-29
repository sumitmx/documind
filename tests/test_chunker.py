"""Tests for paragraph-aware chunking."""

from backend.ingest.chunker import chunk_document
from backend.ingest.loader import Document


def test_single_short_paragraph_produces_one_chunk():
    doc = Document(source="a.txt", text="A short paragraph.")
    chunks = chunk_document(doc)

    assert len(chunks) == 1
    assert chunks[0].source == "a.txt"
    assert chunks[0].index == 0
    assert chunks[0].text == "A short paragraph."


def test_chunks_stay_within_max_chars_plus_overlap_tolerance():
    text = "\n\n".join(f"Paragraph number {i} with some extra padding words." for i in range(200))
    doc = Document(source="big.txt", text=text)
    chunks = chunk_document(doc, max_chars=500, overlap=50)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 500 + 50 + 2 for chunk in chunks)


def test_chunk_indices_are_sequential():
    text = "\n\n".join(f"Paragraph {i}. " * 20 for i in range(30))
    doc = Document(source="seq.txt", text=text)
    chunks = chunk_document(doc, max_chars=300, overlap=30)

    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


def test_overlap_carries_tail_of_previous_chunk_into_the_next():
    paragraphs = [f"Paragraph {i} " + ("word " * 30) for i in range(10)]
    doc = Document(source="overlap.txt", text="\n\n".join(paragraphs))
    chunks = chunk_document(doc, max_chars=200, overlap=40)

    assert len(chunks) > 1
    assert chunks[0].text[-40:] in chunks[1].text


def test_oversized_paragraph_without_separators_is_hard_cut():
    doc = Document(source="wall.txt", text="x" * 5000)
    chunks = chunk_document(doc, max_chars=1000, overlap=100)

    assert len(chunks) >= 5
    assert all(len(chunk.text) <= 1000 + 100 + 2 for chunk in chunks)


def test_oversized_paragraph_prefers_sentence_boundaries():
    sentence = "This is one sentence. " * 100
    doc = Document(source="sentences.txt", text=sentence)
    chunks = chunk_document(doc, max_chars=400, overlap=0)

    assert len(chunks) > 1
    assert all(chunk.text for chunk in chunks)
