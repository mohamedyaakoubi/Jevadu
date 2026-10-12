"""Where the ledger facts and the result of the proof rule are kept (migration 0005).

The facts are kept for each id and network, with the time of the question (design 7.1). The
result of the rule is kept for each id of a project (design 7.2). The result is never typed in:
the check step computes it from the facts, and computes it again whenever it runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import psycopg
from psycopg.types.json import Jsonb

from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.proof import NO_ID_GIVEN

_FACTS = (
    "entity_id, network, asked_at, found, kind, ledger_id, created_at, deleted, "
    "first_activity_at, last_activity_at, activity_count, is_empty, details"
)


@dataclass(frozen=True)
class IdToCheck:
    """One id of one project, with what the check needs to know about its event."""

    hedera_id: int  # the row of the id
    project_id: int
    entity_id: str
    network: str | None  # None when the page leaves the network open
    said_kind: str | None
    event_starts_at: datetime | None
    event_ends_on: date | None


class LedgerStore:
    """Keeps ledger facts and proof results in PostgreSQL. A short connection for each call."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    # ----------------------------------------------------------------- the facts

    def facts(self, entity_id: str, network: str) -> LedgerFacts | None:
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                f"SELECT {_FACTS} FROM ledger_facts "  # noqa: S608  (fixed names)
                "WHERE entity_id = %s AND network = %s",
                (entity_id, network),
            ).fetchone()
        if row is None:
            return None
        return LedgerFacts(
            entity_id=row[0],
            network=row[1],
            asked_at=row[2],
            found=row[3],
            kind=row[4],
            ledger_id=row[5],
            created_at=row[6],
            deleted=row[7],
            first_activity_at=row[8],
            last_activity_at=row[9],
            activity_count=row[10],
            empty=row[11],
            details=row[12],
        )

    def save_facts(self, facts: LedgerFacts) -> None:
        """Keep the newest answer for an id on a network. An older answer is replaced, and what
        was asked about its use inside a window goes with it."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "DELETE FROM ledger_facts WHERE entity_id = %s AND network = %s",
                (facts.entity_id, facts.network),
            )
            conn.execute(
                f"INSERT INTO ledger_facts ({_FACTS}) "  # noqa: S608  (fixed names)
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    facts.entity_id,
                    facts.network,
                    facts.asked_at,
                    facts.found,
                    facts.kind,
                    facts.ledger_id,
                    facts.created_at,
                    facts.deleted,
                    facts.first_activity_at,
                    facts.last_activity_at,
                    facts.activity_count,
                    facts.empty,
                    Jsonb(facts.details),
                ),
            )

    def use(self, entity_id: str, network: str, since: datetime, until: datetime) -> bool | None:
        """Whether the thing was used inside this time, or None if that was never asked."""
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT used FROM ledger_use WHERE entity_id = %s AND network = %s "
                "AND since = %s AND until = %s",
                (entity_id, network, since, until),
            ).fetchone()
        return row[0] if row else None

    def save_use(
        self,
        entity_id: str,
        network: str,
        since: datetime,
        until: datetime,
        used: bool,
        asked_at: datetime,
    ) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "INSERT INTO ledger_use (entity_id, network, since, until, used, asked_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (entity_id, network, since, until) DO UPDATE "
                "SET used = EXCLUDED.used, asked_at = EXCLUDED.asked_at",
                (entity_id, network, since, until, used, asked_at),
            )

    # ----------------------------------------------------------------- the check

    def ids_to_check(self) -> list[IdToCheck]:
        """Every id of every project, in the order of the projects."""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT h.id, h.project_id, h.entity_id, h.network, h.said_kind, "
                "e.starts_at, e.ends_on FROM hedera_ids h "
                "JOIN projects p ON p.id = h.project_id JOIN events e ON e.id = p.event_id "
                "ORDER BY h.project_id, h.id"
            ).fetchall()
        return [IdToCheck(*row) for row in rows]

    def save_checks(
        self, project_id: int, checks: dict[int, dict[str, str]], project_status: str
    ) -> None:
        """Keep what the rule says about the ids of one project: for each id, a status for
        each network that was asked. The old results of the project are replaced."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "DELETE FROM id_checks WHERE hedera_id IN "
                "(SELECT id FROM hedera_ids WHERE project_id = %s)",
                (project_id,),
            )
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO id_checks (hedera_id, network, status) VALUES (%s, %s, %s)",
                    [
                        (hedera_id, network, status)
                        for hedera_id, by_network in checks.items()
                        for network, status in by_network.items()
                    ],
                )
            conn.execute(
                "UPDATE projects SET proof_status = %s WHERE id = %s", (project_status, project_id)
            )

    def mark_projects_with_no_id(self) -> int:
        """A project that gives no id says so. Returns how many projects that is."""
        with psycopg.connect(self._conninfo) as conn:
            return conn.execute(
                "UPDATE projects SET proof_status = %s WHERE NOT EXISTS "
                "(SELECT 1 FROM hedera_ids h WHERE h.project_id = projects.id)",
                (NO_ID_GIVEN,),
            ).rowcount

    def proof_counts(self) -> dict[str, int]:
        """How many projects have each proof status. A project that was not checked yet is
        counted under "not_checked"."""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT COALESCE(proof_status, 'not_checked'), count(*) FROM projects GROUP BY 1"
            ).fetchall()
        return dict(rows)
