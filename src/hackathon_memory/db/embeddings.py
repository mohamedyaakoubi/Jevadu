"""Where the embeddings of the search are kept (design 8.1, migration 0008).

The embedding of a project is made again only when its text or its model changes. The embedding
of a typed idea is kept by the fingerprint of the idea for one day, and the idea itself nowhere.
The embedding of an example idea of the search screen is kept for good (example_ideas.py), and so
is the embedding of a README that a check of a submission made (`kept`, migration 0032, 7 November
2026: a check is kept until someone presses "Read again now").
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from hackathon_memory.example_ideas import EXAMPLE_IDEAS
from hackathon_memory.llm.embeddings import Embedding

PAGE = "page"  # the page as it is: the name, the short line and the two texts
IDEA_LIFETIME = timedelta(hours=24)
_ANY_TIME = datetime(2000, 1, 1, tzinfo=UTC)  # earlier than anything that the tool kept


@dataclass(frozen=True)
class PageText:
    """What is embedded of a project: its name as the title, and its words as the text."""

    project_id: int
    title: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(f"{self.title}\n{self.text}".encode()).hexdigest()


def idea_fingerprint(idea: str) -> str:
    """The fingerprint of an idea: the same words, in any case and spacing, give the same one."""
    return hashlib.sha256(" ".join(idea.lower().split()).encode()).hexdigest()


KEPT_IDEAS = frozenset(idea_fingerprint(idea) for idea in EXAMPLE_IDEAS)


def kept_since(sha256: str, now: datetime | None = None) -> datetime:
    """The oldest moment of what is still kept about an idea: any moment for an example idea,
    one day back for a typed one."""
    return _ANY_TIME if sha256 in KEPT_IDEAS else (now or datetime.now(UTC)) - IDEA_LIFETIME


class EmbeddingStore:
    """Keeps the embeddings in PostgreSQL. Opens a short connection for each operation."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def _connect(self) -> psycopg.Connection:
        conn = psycopg.connect(self._conninfo)
        register_vector(conn)
        return conn

    # ------------------------------------------------------------------ the projects

    def page_texts(self) -> list[PageText]:
        """The text of every project: its short line and its two texts, in their order."""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT p.id, p.name, p.short_line, "
                "coalesce(string_agg(s.body, E'\\n\\n' ORDER BY s.position), '') "
                "FROM projects p LEFT JOIN sections s ON s.project_id = p.id "
                "GROUP BY p.id ORDER BY p.id"
            ).fetchall()
        return [
            PageText(
                project_id,
                name,
                "\n\n".join(part for part in (short_line.strip(), bodies.strip()) if part),
            )
            for project_id, name, short_line, bodies in rows
        ]

    def known(self, model: str, kind: str = PAGE) -> dict[int, str]:
        """For each project with an embedding of this model, the fingerprint of its text."""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT project_id, text_sha256 FROM project_embeddings "
                "WHERE model = %s AND text_kind = %s",
                (model, kind),
            ).fetchall()
        return dict(rows)

    def save(
        self, project_id: int, model: str, sha256: str, embedding: Embedding, kind: str = PAGE
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO project_embeddings (project_id, text_kind, model, text_sha256, "
                "embedding, tokens, truncated) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (project_id, text_kind, model) DO UPDATE SET "
                "text_sha256 = EXCLUDED.text_sha256, embedding = EXCLUDED.embedding, "
                "tokens = EXCLUDED.tokens, truncated = EXCLUDED.truncated, made_at = now()",
                (
                    project_id,
                    kind,
                    model,
                    sha256,
                    Vector(embedding.values),
                    embedding.token_count,
                    embedding.truncated,
                ),
            )

    def nearest(
        self,
        values: list[float],
        model: str,
        *,
        limit: int,
        kind: str = PAGE,
        only: Sequence[int] | None = None,
    ) -> list[tuple[int, float]]:
        """The projects closest in meaning, with their cosine distance, closest first, from the
        projects of `only` when it is given. An exact search: every row is compared (design
        11.6)."""
        ids = None if only is None else list(only)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT project_id, embedding <=> %s AS distance FROM project_embeddings "
                "WHERE model = %s AND text_kind = %s "
                "AND (%s::bigint[] IS NULL OR project_id = ANY(%s)) "
                "ORDER BY distance, project_id LIMIT %s",
                (Vector(values), model, kind, ids, ids, limit),
            ).fetchall()
        return [(project_id, float(distance)) for project_id, distance in rows]

    def counts(self, model: str) -> dict[str, int]:
        with psycopg.connect(self._conninfo) as conn:
            made, cut = conn.execute(
                "SELECT count(*), count(*) FILTER (WHERE truncated) FROM project_embeddings "
                "WHERE model = %s",
                (model,),
            ).fetchone()
        return {"embeddings": made, "embeddings_of_a_cut_text": cut}

    # ------------------------------------------------------------------ the typed ideas

    def idea(self, sha256: str, model: str, now: datetime | None = None) -> list[float] | None:
        """The embedding of an idea typed less than a day ago, of an example idea, or of a README
        that a check keeps for good, or None."""
        since = kept_since(sha256, now)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT embedding FROM idea_embeddings "
                "WHERE idea_sha256 = %s AND model = %s AND (made_at > %s OR kept)",
                (sha256, model, since),
            ).fetchone()
        return [float(value) for value in row[0].to_list()] if row else None  # a pgvector Vector

    def save_idea(
        self,
        sha256: str,
        model: str,
        values: list[float],
        now: datetime | None = None,
        kept: bool = False,
    ) -> None:
        """Keep the embedding of an idea; with `kept`, for good. A row kept for good stays so."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO idea_embeddings (idea_sha256, model, embedding, made_at, kept) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (idea_sha256, model) DO UPDATE SET "
                "embedding = EXCLUDED.embedding, made_at = EXCLUDED.made_at, "
                "kept = idea_embeddings.kept OR EXCLUDED.kept",
                (sha256, model, Vector(values), now or datetime.now(UTC), kept),
            )

    def keep_idea(self, sha256: str, model: str) -> None:
        """Keep for good the embedding of an idea that was made for a day."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "UPDATE idea_embeddings SET kept = true "
                "WHERE idea_sha256 = %s AND model = %s AND NOT kept",
                (sha256, model),
            )

    def forget_old_ideas(self, now: datetime | None = None) -> int:
        """Delete the embeddings of ideas typed a day ago or more, never those of the example
        ideas, nor those kept for good. Returns how many."""
        before = (now or datetime.now(UTC)) - IDEA_LIFETIME
        with psycopg.connect(self._conninfo) as conn:
            return conn.execute(
                "DELETE FROM idea_embeddings "
                "WHERE made_at <= %s AND NOT kept AND NOT idea_sha256 = ANY(%s)",
                (before, list(KEPT_IDEAS)),
            ).rowcount
