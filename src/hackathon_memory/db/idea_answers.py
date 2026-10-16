"""What the search model answered about a typed idea, kept for one day (migration 0011).

The key is the fingerprint of the idea, never the idea: the order of its closest projects for one
set of filters, and its comparison with each project for the texts of that project that the model
read. Like the embedding of the idea (db/embeddings.py), a row lives one day. An exact cache: an
answer is given back only for exactly the same idea, filters, model, level and instructions, so it
can never speak about another idea (decided on 11 October 2026: no cache by similar meaning).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg

from hackathon_memory.db.embeddings import IDEA_LIFETIME


@dataclass(frozen=True)
class KeptOrder:
    pool: list[int]  # what the model read, the closest in meaning first
    ordered: list[int]  # its answer, the closest first


@dataclass(frozen=True)
class KeptComparison:
    same: str
    differs: str
    fields_used: list[str]


class AnswerStore:
    """Keeps the answers of the search model in PostgreSQL, one short connection each time."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def order(self, idea_sha256: str, scope: str, model: str, level: str, version: str,
              now: datetime | None = None) -> KeptOrder | None:  # fmt: skip
        """The order that the model gave less than a day ago, or None."""
        since = (now or datetime.now(UTC)) - IDEA_LIFETIME
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT pool, ordered FROM idea_orders WHERE idea_sha256 = %s AND scope = %s "
                "AND model = %s AND thinking_level = %s AND version = %s AND made_at > %s",
                (idea_sha256, scope, model, level, version, since),
            ).fetchone()
        return KeptOrder(list(row[0]), list(row[1])) if row else None

    def save_order(self, idea_sha256: str, scope: str, model: str, level: str, version: str,
                   kept: KeptOrder, now: datetime | None = None) -> None:  # fmt: skip
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "INSERT INTO idea_orders (idea_sha256, scope, model, thinking_level, version, "
                "pool, ordered, made_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (idea_sha256, scope, model, thinking_level, version) DO UPDATE SET "
                "pool = EXCLUDED.pool, ordered = EXCLUDED.ordered, made_at = EXCLUDED.made_at",
                (idea_sha256, scope, model, level, version, kept.pool, kept.ordered,
                 now or datetime.now(UTC)),
            )  # fmt: skip

    def comparisons(
        self,
        idea_sha256: str,
        inputs: Mapping[int, str],
        model: str,
        level: str,
        version: str,
        now: datetime | None = None,
    ) -> dict[int, KeptComparison]:
        """For each project of `inputs` (its id and the fingerprint of the texts that the model
        would read), the comparison made less than a day ago for exactly those texts."""
        if not inputs:
            return {}
        since = (now or datetime.now(UTC)) - IDEA_LIFETIME
        ids = list(inputs)
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT project_id, input_sha256, same, differs, fields_used FROM idea_comparisons "
                "WHERE idea_sha256 = %s AND project_id = ANY(%s) AND model = %s "
                "AND thinking_level = %s AND version = %s AND made_at > %s",
                (idea_sha256, ids, model, level, version, since),
            ).fetchall()
        return {
            project_id: KeptComparison(same, differs, list(used))
            for project_id, input_sha256, same, differs, used in rows
            if inputs.get(project_id) == input_sha256
        }

    def save_comparisons(self, idea_sha256: str, found: Mapping[int, tuple[str, KeptComparison]],
                         model: str, level: str, version: str,
                         now: datetime | None = None) -> None:  # fmt: skip
        """Keep each new comparison, by project: (the fingerprint of its texts, the comparison)."""
        if not found:
            return
        made_at = now or datetime.now(UTC)
        with psycopg.connect(self._conninfo) as conn:
            for project_id, (input_sha256, one) in found.items():
                conn.execute(
                    "INSERT INTO idea_comparisons (idea_sha256, project_id, model, thinking_level, "
                    "version, input_sha256, same, differs, fields_used, made_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (idea_sha256, project_id, model, thinking_level, version, "
                    "input_sha256) DO UPDATE SET same = EXCLUDED.same, "
                    "differs = EXCLUDED.differs, fields_used = EXCLUDED.fields_used, "
                    "made_at = EXCLUDED.made_at",
                    (idea_sha256, project_id, model, level, version, input_sha256, one.same,
                     one.differs, list(one.fields_used), made_at),
                )  # fmt: skip

    def forget_old(self, now: datetime | None = None) -> int:
        """Delete the answers about ideas typed a day ago or more. Returns how many rows."""
        before = (now or datetime.now(UTC)) - IDEA_LIFETIME
        with psycopg.connect(self._conninfo) as conn:
            orders = conn.execute("DELETE FROM idea_orders WHERE made_at <= %s", (before,))
            compared = conn.execute("DELETE FROM idea_comparisons WHERE made_at <= %s", (before,))
            return orders.rowcount + compared.rowcount


def scope_of(chosen: Mapping[str, str], names: Sequence[str]) -> str:
    """The filters of a search, always written the same way, for the key of a kept order."""
    return "&".join(f"{name}={chosen[name]}" for name in names if chosen.get(name))
