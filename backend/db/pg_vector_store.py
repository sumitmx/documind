"""Postgres + pgvector backed store, used when DATABASE_URL is configured."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql

from backend.ingest.chunker import Chunk

METADATA_TABLE = "documind_index_meta"


class PgVectorStore:
    """One physical table per project, sized to whatever embedding dimension it was last saved with."""

    def __init__(self, project_id: str, database_url: str) -> None:
        self.project_id = project_id
        self.database_url = database_url
        self.table_name = f"chunks_{re.sub(r'[^a-z0-9_]', '_', project_id.lower())}"

    def _connect(self) -> psycopg.Connection:
        conn = psycopg.connect(self.database_url, autocommit=False)
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        conn.execute(
            sql.SQL(
                "CREATE TABLE IF NOT EXISTS {} ("
                "project_id TEXT PRIMARY KEY, provider TEXT, chunk_count INT, created_at TIMESTAMPTZ)"
            ).format(sql.Identifier(METADATA_TABLE))
        )
        return conn

    def _table_exists(self, conn: psycopg.Connection) -> bool:
        result = conn.execute("SELECT to_regclass(%s)", (self.table_name,)).fetchone()
        return bool(result and result[0] is not None)

    def save(self, chunks: list[Chunk], embeddings: list[list[float]] | None, provider: str) -> dict[str, object]:
        if embeddings is not None and len(chunks) != len(embeddings):
            raise ValueError("Each text chunk must have exactly one embedding.")
        dimensions = len(embeddings[0]) if embeddings else 1
        table = sql.Identifier(self.table_name)

        with self._connect() as conn:
            conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(table))
            conn.execute(
                sql.SQL(
                    "CREATE TABLE {} (id SERIAL PRIMARY KEY, source TEXT NOT NULL, "
                    "chunk_index INT NOT NULL, text TEXT NOT NULL, embedding vector({}))"
                ).format(table, sql.Literal(dimensions))
            )
            rows = [
                (chunk.source, chunk.index, chunk.text, embeddings[position] if embeddings else None)
                for position, chunk in enumerate(chunks)
            ]
            with conn.cursor() as cursor:
                cursor.executemany(
                    sql.SQL("INSERT INTO {} (source, chunk_index, text, embedding) VALUES (%s, %s, %s, %s)").format(table),
                    rows,
                )
            conn.execute(
                sql.SQL(
                    "INSERT INTO {} (project_id, provider, chunk_count, created_at) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (project_id) DO UPDATE SET provider = EXCLUDED.provider, "
                    "chunk_count = EXCLUDED.chunk_count, created_at = EXCLUDED.created_at"
                ).format(sql.Identifier(METADATA_TABLE)),
                (self.project_id, provider, len(chunks), datetime.now(UTC)),
            )
            conn.commit()
        return self.status()

    def search(self, query_embedding: list[float], limit: int = 4) -> list[dict[str, object]]:
        table = sql.Identifier(self.table_name)
        with self._connect() as conn:
            if not self._table_exists(conn):
                return []
            rows = conn.execute(
                sql.SQL(
                    "SELECT source, chunk_index, text, 1 - (embedding <=> %s::vector) AS score FROM {} "
                    "ORDER BY embedding <=> %s::vector LIMIT %s"
                ).format(table),
                (query_embedding, query_embedding, limit),
            ).fetchall()
        return [{"source": row[0], "index": row[1], "text": row[2], "score": round(float(row[3]), 3)} for row in rows]

    def search_lexical(self, query: str, limit: int = 4) -> list[dict[str, object]]:
        terms = set(re.findall(r"[a-z0-9]{2,}", query.lower()))
        table = sql.Identifier(self.table_name)
        with self._connect() as conn:
            if not self._table_exists(conn):
                return []
            rows = []
            if terms:
                tsquery = " | ".join(terms)
                rows = conn.execute(
                    sql.SQL(
                        "SELECT source, chunk_index, text, "
                        "ts_rank(to_tsvector('english', text), to_tsquery('english', %s)) AS score FROM {} "
                        "WHERE to_tsvector('english', text) @@ to_tsquery('english', %s) "
                        "ORDER BY score DESC LIMIT %s"
                    ).format(table),
                    (tsquery, tsquery, limit),
                ).fetchall()
            if not rows:
                # No keyword overlap at all (a greeting, or a question that only shares
                # stop words with the library) - fall back to the opening chunk of each
                # document, so a vague first question still has something to work from.
                rows = conn.execute(
                    sql.SQL(
                        "SELECT DISTINCT ON (source) source, chunk_index, text, 0 AS score FROM {} "
                        "ORDER BY source, chunk_index ASC LIMIT %s"
                    ).format(table),
                    (limit,),
                ).fetchall()
        return [{"source": row[0], "index": row[1], "text": row[2], "score": round(float(row[3]), 3)} for row in rows]

    def delete(self) -> None:
        table = sql.Identifier(self.table_name)
        with self._connect() as conn:
            conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(table))
            conn.execute(
                sql.SQL("DELETE FROM {} WHERE project_id = %s").format(sql.Identifier(METADATA_TABLE)),
                (self.project_id,),
            )
            conn.commit()

    def status(self) -> dict[str, object]:
        with self._connect() as conn:
            meta = conn.execute(
                sql.SQL("SELECT provider, chunk_count, created_at FROM {} WHERE project_id = %s").format(sql.Identifier(METADATA_TABLE)),
                (self.project_id,),
            ).fetchone()
            if not meta or not self._table_exists(conn):
                return {"indexed": False, "chunks": 0, "documents": [], "created_at": None, "provider": None}
            documents = conn.execute(
                sql.SQL("SELECT DISTINCT source FROM {} ORDER BY source").format(sql.Identifier(self.table_name))
            ).fetchall()
        provider, chunk_count, created_at = meta
        return {
            "indexed": chunk_count > 0,
            "chunks": chunk_count,
            "documents": [row[0] for row in documents],
            "created_at": created_at.isoformat() if created_at else None,
            "provider": provider,
        }
