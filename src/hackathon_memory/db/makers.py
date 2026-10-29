"""Who made the projects' own things (migration 0021, design 7.5, 29 October 2026). A short
connection for each call."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg

from hackathon_memory.check.makers import THINGS
from hackathon_memory.db.history import OWN

# Each own thing that the ledger knows, with when it was made, not asked yet; and the account that
# paid for its creation when its history holds that moment (a contract's history begins with it).
_TO_ASK = (
    "SELECT DISTINCT f.entity_id, f.network, f.kind, coalesce(f.ledger_id, f.entity_id), "
    "f.created_at, (SELECT e.payer FROM ledger_events e WHERE e.entity_id = f.entity_id "
    "               AND e.network = f.network AND e.payer IS NOT NULL "
    "               AND abs(extract(epoch FROM e.at - f.created_at)) < 0.001 LIMIT 1) "
    "FROM hedera_ids h JOIN own USING (entity_id) "
    "JOIN ledger_facts f ON f.entity_id = h.entity_id "
    "WHERE f.found AND f.kind = ANY(%s) AND f.created_at IS NOT NULL "
    "AND f.made_by_asked_at IS NULL ORDER BY 1, 2"
)


@dataclass(frozen=True)
class ThingToAsk:
    entity_id: str  # as the project names it
    network: str
    kind: str
    ledger_id: str  # the ID that the mirror node gives it
    made_at: datetime
    payer_read: str | None  # the account that paid for its creation, when its history holds it


class MakerStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def to_ask(self, *, projects: set[int] | None = None) -> list[ThingToAsk]:
        only = " AND h.project_id = ANY(%s)" if projects is not None else ""
        query = OWN + _TO_ASK.replace(" ORDER BY", only + " ORDER BY")
        values: list[object] = [list(THINGS)] + ([sorted(projects)] if projects is not None else [])
        with psycopg.connect(self._conninfo) as conn:
            return [ThingToAsk(*row) for row in conn.execute(query, values)]  # noqa: S608

    def save(self, entity_id: str, network: str, made_by: str | None, asked_at: datetime) -> None:
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "UPDATE ledger_facts SET made_by = %s, made_by_asked_at = %s "
                "WHERE entity_id = %s AND network = %s",
                (made_by, asked_at, entity_id, network),
            )
