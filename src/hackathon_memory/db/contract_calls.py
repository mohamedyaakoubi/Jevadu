"""What the calls of the projects' own contracts reached among Hedera's system contracts
(migration 0020, design 7.5, 28 October 2026). A short connection for each call."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg

from hackathon_memory.check.story import time_of
from hackathon_memory.check.system_calls import ContractCalls
from hackathon_memory.db.history import KINDS_THAT_FIT, OWN

# Each own contract whose kind fits, on a network where it fits, with the days of the event of
# each project that names it.
_CONTRACTS = (
    "SELECT DISTINCT h.entity_id, c.network, coalesce(f.ledger_id, h.entity_id), e.starts_at, "
    "e.ends_on FROM hedera_ids h JOIN own USING (entity_id) "
    "JOIN id_checks c ON c.hedera_id = h.id "
    "JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network "
    "JOIN projects p ON p.id = h.project_id JOIN events e ON e.id = p.event_id "
    "WHERE f.found AND f.kind = 'contract' AND c.status = ANY(%s)"
)


@dataclass(frozen=True)
class ContractToRead:
    entity_id: str  # as the project names it: an ID or an EVM address
    network: str
    ledger_id: str  # the ID that the mirror node gives it
    starts_at: datetime  # the time of the ledger story of a project that names it
    ends_at: datetime


class ContractCallStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def to_read(
        self,
        *,
        projects: set[int] | None = None,
        older_than: timedelta | None = None,
        now: datetime | None = None,
    ) -> list[ContractToRead]:
        """The own contracts to read, each in the time of the story of each project that names
        it: those not read in that time yet, and those read before that time was over; with
        `older_than`, of the latter only those read longer ago than that. A contract read after
        its time is never read again: its calls in that time cannot change. A project whose days
        of the event are not known has no such time."""
        now = now or datetime.now(UTC)
        only = " AND h.project_id = ANY(%s)" if projects is not None else ""
        values: list[object] = [list(KINDS_THAT_FIT)]
        values += [sorted(projects)] if projects is not None else []
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(OWN + _CONTRACTS + only, values).fetchall()  # noqa: S608
            kept = {(entity, network, starts, ends): asked for entity, network, starts, ends, asked
                    in conn.execute("SELECT entity_id, network, starts_at, ends_at, asked_at "
                                    "FROM contract_calls")}  # fmt: skip
        todo: dict[tuple, ContractToRead] = {}
        for entity, network, ledger_id, starts_at, ends_on in rows:
            span = time_of(starts_at, ends_on)
            if span is None:
                continue
            asked = kept.get((entity, network, *span))
            open_then = asked is not None and asked < span[1]
            old = older_than is None or (asked is not None and now - asked >= older_than)
            if asked is None or (open_then and old):
                todo[(entity, network, *span)] = ContractToRead(entity, network, ledger_id, *span)
        return sorted(todo.values(), key=lambda one: (one.entity_id, one.network, one.starts_at))

    def save(self, calls: ContractCalls, asked_at: datetime) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "INSERT INTO contract_calls (entity_id, network, starts_at, ends_at, read, cut, "
                "reached, asked_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (entity_id, network, starts_at, ends_at) DO UPDATE SET "
                "read = excluded.read, cut = excluded.cut, reached = excluded.reached, "
                "asked_at = excluded.asked_at",
                (calls.entity_id, calls.network, calls.starts_at, calls.ends_at, calls.read,
                 calls.cut, json.dumps(calls.reached), asked_at),
            )  # fmt: skip
