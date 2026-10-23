"""Where the history of each own Hedera ID is kept (migration 0016, check/history.py).

An own ID is named by one project only: an ID that several projects name is often a shared
service (design 8.4), and its history would say nothing about one team. Only an ID whose kind
fits what its page says is read: the statuses of the proof rule "proof found", "the dates do not
fit" and "found, but empty" (design 7.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg

from hackathon_memory.check.history import History
from hackathon_memory.check.proof import DATES_DO_NOT_FIT, FOUND_BUT_EMPTY, PROOF_FOUND

KINDS_THAT_FIT = (PROOF_FOUND, DATES_DO_NOT_FIT, FOUND_BUT_EMPTY)


@dataclass(frozen=True)
class IdToRead:
    entity_id: str  # as the page names it
    network: str
    kind: str  # what the ledger says it is
    ledger_id: str | None  # the id that the ledger gives it, such as 0.0.123 for an EVM address


class HistoryStore:
    """Keeps the histories in PostgreSQL. A short connection for each call."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def ids_to_read(self) -> list[IdToRead]:
        """The own IDs whose kind fits and whose history was not read yet."""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "WITH own AS (SELECT entity_id FROM hedera_ids GROUP BY entity_id "
                "             HAVING count(DISTINCT project_id) = 1) "
                "SELECT DISTINCT h.entity_id, c.network, f.kind, f.ledger_id "
                "FROM hedera_ids h JOIN own USING (entity_id) "
                "JOIN id_checks c ON c.hedera_id = h.id "
                "JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network "
                "WHERE f.found AND c.status = ANY(%s) AND NOT EXISTS (SELECT 1 FROM "
                "  ledger_histories r WHERE r.entity_id = h.entity_id AND r.network = c.network) "
                "ORDER BY 1, 2",
                (list(KINDS_THAT_FIT),),
            ).fetchall()
        return [IdToRead(*row) for row in rows]

    def save(
        self, entity_id: str, network: str, kind: str, history: History, asked_at: datetime
    ) -> None:
        """Keep one history, in place of an older one of the same ID."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "DELETE FROM ledger_histories WHERE entity_id = %s AND network = %s",
                (entity_id, network),
            )
            conn.execute(
                "INSERT INTO ledger_histories (entity_id, network, kind, asked_at, events, cut) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (entity_id, network, kind, asked_at, len(history.events), history.cut),
            )
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO ledger_events (entity_id, network, stamp, at, service) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [(entity_id, network, stamp, datetime.fromtimestamp(float(stamp), tz=UTC),
                      service) for stamp, service in history.events.items()],
                )  # fmt: skip
