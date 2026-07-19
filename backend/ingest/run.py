"""Load and chunk everything in docs/, and report what happened."""

from backend.ingest.chunker import chunk_document
from backend.ingest.loader import load_docs


def main() -> None:
    docs = load_docs("docs")
    if not docs:
        print("No documents found in docs/ — add a .pdf or .md file.")
        return

    all_chunks = []
    for doc in docs:
        chunks = chunk_document(doc)
        all_chunks.extend(chunks)
        print(f"{doc.source:40} {len(doc.text):>7} chars -> {len(chunks):>3} chunks")

    print(f"\ntotal: {len(all_chunks)} chunks")

    first = all_chunks[0]
    print(f"\n--- {first.source} chunk {first.index} ({len(first.text)} chars) ---")
    print(first.text[:400])


if __name__ == "__main__":
    main()
