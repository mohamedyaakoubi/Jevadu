"""The own IDs that a team put on Hedera's main network (design 7.5).

The tag "Mainnet" of a project, and its filter, come from here (search/listing.py).
"""

from __future__ import annotations

from collections.abc import Sequence

import psycopg

from hackathon_memory.check.story import WINDOW_BEFORE
from hackathon_memory.db.history import OWN

# The own IDs that a team put on the main network (design 7.5, 28 October 2026): an ID that its
# page, its README or its code names on the main network, that the main network knows as that
# kind, made in the time of the event or later (from WINDOW_BEFORE before its start). An ID named
# with no network does not count: nearly every number of an account also exists on the main
# network as somebody else's. The own rule is OWN of db/history.py.
_MAINNET = """
SELECT DISTINCT h.project_id, h.entity_id FROM hedera_ids h JOIN own USING (entity_id)
JOIN projects p ON p.id = h.project_id JOIN events e ON e.id = p.event_id
JOIN id_checks c ON c.hedera_id = h.id AND c.network = 'mainnet' AND c.status IN (
    'proof_found', 'window_not_known', 'dates_do_not_fit', 'found_but_empty')
JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = 'mainnet'
WHERE h.project_id = ANY(%s) AND h.network = 'mainnet' AND f.created_at >= e.starts_at - %s
"""


def mainnet_ids(conn: psycopg.Connection, ids: Sequence[int]) -> dict[int, set[str]]:
    """For each project among `ids` whose team put an own ID on the main network, those IDs, as
    its page, its README or its code names them."""
    found: dict[int, set[str]] = {}
    rows = conn.execute(OWN + _MAINNET, (list(ids), WINDOW_BEFORE)).fetchall()  # noqa: S608
    for project_id, entity_id in rows:
        found.setdefault(project_id, set()).add(entity_id)
    return found
