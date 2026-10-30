"""Public services that many projects use (migration 0022, design 8.4, 29 October 2026): a
contract, a topic or a token that its owner runs for everyone, such as a price oracle or a dollar
token. Each comes from its owner's own published list. A project that names one does not own it
(db/history.py, OWN), it joins no projects (search/seen.py), and its card says what it is."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import psycopg

# The public services that one project names, by the ID that the ledger gives the thing on its
# network, or by the EVM address, which is the same service on every network.
_OF_PROJECT = (
    "SELECT DISTINCT h.entity_id, s.name, s.source, s.read_on FROM hedera_ids h "
    "LEFT JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.found "
    "JOIN public_services s ON s.evm_address = lower(h.entity_id) "
    "     OR (s.network = f.network AND s.ledger_id = coalesce(f.ledger_id, h.entity_id)) "
    "WHERE h.project_id = %s ORDER BY 1"
)
# A public service as search/seen.py writes an ID: network:ID, in both forms.
_KEYS = (
    "SELECT network || ':' || ledger_id FROM public_services "
    "UNION SELECT network || ':' || evm_address FROM public_services WHERE evm_address IS NOT NULL"
)


@dataclass(frozen=True)
class NamedService:
    """A public service that a project names."""

    entity_id: str  # as the project names it
    name: str  # "the price oracle of Pyth"
    source: str  # the list that the service's maker publishes
    read_on: date


def public_services_of(conn: psycopg.Connection, project_id: int) -> tuple[NamedService, ...]:
    return tuple(NamedService(*row) for row in conn.execute(_OF_PROJECT, (project_id,)))


def public_keys(conn: psycopg.Connection) -> set[str]:
    """Every public service as network:ID, in both of its forms."""
    return {key for (key,) in conn.execute(_KEYS)}
