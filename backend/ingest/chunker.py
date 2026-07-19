"""Split document text into overlapping chunks."""

from dataclasses import dataclass

from backend.ingest.loader import Document

MAX_CHARS = 2000      # ~500 tokens
OVERLAP_CHARS = 200   # ~10%, so ideas spanning a boundary survive


@dataclass
class Chunk:
    source: str
    index: int    # position within the document, for citations
    text: str

def _split_oversized(text: str, max_chars: int) -> list[str]:
    """Break text that is too big for one chunk, on the best boundary available."""
    for sep in ("\n", ". "):
        if sep not in text:
            continue
        parts, out, current = text.split(sep), [], ""
        for part in parts:
            if current and len(current) + len(part) + len(sep) > max_chars:
                out.append(current)
                current = part
            else:
                current = f"{current}{sep}{part}" if current else part
        if current:
            out.append(current)
        if all(len(o) <= max_chars for o in out):
            return out

    # No usable boundary — a wall of text. Cut it.
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]



def chunk_document(doc: Document, max_chars: int = MAX_CHARS,
                   overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    paragraphs = [p.strip() for p in doc.text.split("\n\n") if p.strip()]

    units: list[str] = []
    for para in paragraphs:
        units.extend(_split_oversized(para, max_chars) if len(para) > max_chars else [para])


    chunks: list[str] = []
    current = ""

    for para in units:
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = current[-overlap:] + "\n\n" + para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        chunks.append(current)

    return [Chunk(source=doc.source, index=i, text=t)
            for i, t in enumerate(chunks)]
