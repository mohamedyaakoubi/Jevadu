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
from hackathon_memory.check.story import OwnId, Story, merged, on_its_network, story_of
from hackathon_memory.parse.hedera_ids import ACCOUNT

KINDS_THAT_FIT = (PROOF_FOUND, DATES_DO_NOT_FIT, FOUND_BUT_EMPTY)
# The own IDs, as the first part of a query that joins `own` (design 8.4).
OWN = (
    "WITH own AS (SELECT entity_id FROM hedera_ids GROUP BY entity_id "
    "             HAVING count(DISTINCT project_id) = 1) "
)


@dataclass(frozen=True)
class IdToRead:
    entity_id: str  # as the page names it
    network: str
    kind: str  # what the ledger says it is
    ledger_id: str | None  # the id that the ledger gives it, such as 0.0.123 for an EVM address
    made_at: datetime | None = None  # when the ledger says it was made


class HistoryStore:
    """Keeps the histories in PostgreSQL. A short connection for each call."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def ids_to_read(self) -> list[IdToRead]:
        """The own IDs whose kind fits and whose history was not read yet."""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                OWN  # noqa: S608  (fixed text)
                + "SELECT DISTINCT h.entity_id, c.network, f.kind, f.ledger_id, f.created_at "
                "FROM hedera_ids h JOIN own USING (entity_id) "
                "JOIN id_checks c ON c.hedera_id = h.id "
                "JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network "
                "WHERE f.found AND c.status = ANY(%s) AND NOT EXISTS (SELECT 1 FROM "
                "  ledger_histories r WHERE r.entity_id = h.entity_id AND r.network = c.network) "
                "ORDER BY 1, 2",
                (list(KINDS_THAT_FIT),),
            ).fetchall()
        return [IdToRead(*row) for row in rows]

    def saved(
        self, entity_id: str, network: str, *, since: datetime
    ) -> tuple[History, datetime] | None:
        """The history of an ID that was read at `since` or later, with the moment it was read;
        None when it was not read since then."""
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT asked_at, cut FROM ledger_histories WHERE entity_id = %s AND network = %s "
                "AND asked_at >= %s",
                (entity_id, network, since),
            ).fetchone()
            if row is None:
                return None
            events = conn.execute(
                "SELECT stamp, service FROM ledger_events WHERE entity_id = %s AND network = %s",
                (entity_id, network),
            ).fetchall()
        return History(dict(events), row[1]), row[0]

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


def story_of_project(
    conn: psycopg.Connection,
    project_id: int,
    *,
    words: str,
    in_code: frozenset[str] | None,
    set_up: frozenset[str] = frozenset(),
) -> Story | None:
    """The ledger story of one project (design 7.5), from its own IDs whose kind fits, each on
    its network, and the events of those whose history was read; None when it has no such ID.
    `words` are the page's own words, `in_code` the services that its code calls, and `set_up`
    those that it only sets up for."""
    rows = conn.execute(
        OWN  # noqa: S608  (fixed text)
        + "SELECT DISTINCT h.project_id, h.entity_id, c.network, c.status, "
        "coalesce(r.kind, f.kind), r.asked_at, coalesce(r.cut, false) "
        "FROM hedera_ids h JOIN own USING (entity_id) "
        "JOIN id_checks c ON c.hedera_id = h.id "
        "LEFT JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network "
        "LEFT JOIN ledger_histories r ON r.entity_id = h.entity_id AND r.network = c.network "
        "WHERE h.project_id = %s AND c.status = ANY(%s)",
        (project_id, list(KINDS_THAT_FIT)),
    ).fetchall()
    if not rows:
        return None
    ids: dict[tuple[str, str], OwnId] = {}
    for _, entity, network, _, kind, asked_at, cut in on_its_network(rows):
        ids.setdefault((entity, network), OwnId(entity, network, kind, asked_at, cut))
    read = [one.entity_id for one in ids.values() if one.asked_at is not None]
    seen: list[tuple[str, datetime, str, bool]] = []
    for entity, network, stamp, at, service in conn.execute(
        "SELECT entity_id, network, stamp, at, service FROM ledger_events "
        "WHERE entity_id = ANY(%s)",
        (read,),
    ):
        one = ids.get((entity, network))
        if one is not None and one.asked_at is not None:
            seen.append((stamp, at, service, one.kind == ACCOUNT))
    starts_at, ends_on = conn.execute(
        "SELECT e.starts_at, e.ends_on FROM projects p JOIN events e ON e.id = p.event_id "
        "WHERE p.id = %s",
        (project_id,),
    ).fetchone() or (None, None)
    return story_of(tuple(ids.values()), merged(seen), words, in_code,
                    starts_at=starts_at, ends_on=ends_on, set_up=set_up)  # fmt: skip
