"""Central paths and settings for the local DocuMind portal."""

from pathlib import Path

from dotenv import load_dotenv

# Loaded once here, at first import, rather than per-call in each adapter -
# calling load_dotenv() repeatedly re-populates os.environ from .env even
# after a test has monkeypatch.delenv()'d a variable for isolation.
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
DATA_DIR = PROJECT_ROOT / "data"
INDEX_FILE = DATA_DIR / "index.json"
PROJECTS_DIR = PROJECT_ROOT / "projects"
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

EMBEDDING_MODEL = "gemini-embedding-001"
CHAT_MODEL = "gemini-2.5-flash"
EMBEDDING_DIMENSIONS = 768
RETRIEVAL_COUNT = 4
