"""Selects the local JSON store or the Postgres/pgvector store per DATABASE_URL."""

from __future__ import annotations

import os

from backend.db.pg_vector_store import PgVectorStore
from backend.db.vector_store import VectorStore
from backend.projects import Project


def get_vector_store(project: Project) -> VectorStore | PgVectorStore:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return PgVectorStore(project.identifier, database_url)
    return VectorStore(project.index_file)
