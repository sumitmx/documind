"""Load raw text out of the files in docs/."""

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class Document:
    source: str   # filename, kept so citations can point back to it
    text: str


def _read_pdf(path: Path) -> str:
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def _read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


LOADERS = {".pdf": _read_pdf, ".md": _read_markdown, ".txt": _read_markdown}


def load_docs(directory: str = "docs") -> list[Document]:
    docs = []
    for path in sorted(Path(directory).iterdir()):
        loader = LOADERS.get(path.suffix.lower())
        if loader is None:
            continue
        text = loader(path).strip()
        if text:
            docs.append(Document(source=path.name, text=text))
    return docs
