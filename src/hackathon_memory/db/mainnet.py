"""The own IDs that a team put on Hedera's main network (design 7.5), and what each transaction
of them cost and moved there (migration 0028, design 7.6).

The tag "Mainnet" of a project, and its filter, come from here (search/listing.py). The moments of
the transactions come from the histories of those IDs (db/history.py); the step `mainnet` asks the
mirror node about each moment once (pipeline/mainnet.py).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import psycopg

from hackathon_memory.check.mainnet import Detail, Rate
from hackathon_memory.check.mainnet_what import Thing
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


@dataclass(frozen=True)
class OwnThing:
    """An own ID on the main network, with what the step `mainnet_what` needs about it."""

    entity_id: str  # as its project names it
    ledger_id: str  # as the ledger names it: 0.0.X, or the ID of a transaction
    kind: str
    made_at: datetime | None
    made_by: str | None  # the account that made it, when the step `makers` found it
    repository: str | None  # the repository of a project that names it
    since: datetime | None  # WINDOW_BEFORE before the start of its first event
    todo: tuple[str, ...]  # the moments of its transactions that are not explained yet


# The facts of the own IDs on the main network: one row for each, with the repository of a
# project that names it, the start of its first event, and the moments not explained yet.
_OWN_THINGS = """
SELECT f.entity_id, coalesce(f.ledger_id, f.entity_id), f.kind, f.created_at, f.made_by,
       (SELECT min(r.url) FROM hedera_ids h JOIN projects p ON p.id = h.project_id
        JOIN repositories r ON r.id = p.repository_id
        WHERE h.entity_id = f.entity_id AND h.project_id = ANY(%s)),
       (SELECT min(e.starts_at) FROM hedera_ids h JOIN projects p ON p.id = h.project_id
        JOIN events e ON e.id = p.event_id
        WHERE h.entity_id = f.entity_id AND h.project_id = ANY(%s)) - %s,
       coalesce((SELECT array_agg(DISTINCT v.stamp ORDER BY v.stamp) FROM ledger_events v
                 JOIN mainnet_transactions t ON t.stamp = v.stamp
                 WHERE v.network = 'mainnet' AND v.entity_id = f.entity_id
                 AND t.explained_at IS NULL), '{}')
FROM ledger_facts f WHERE f.network = 'mainnet' AND f.found AND f.entity_id = ANY(%s)
ORDER BY f.entity_id
"""


class MainnetStore:
    """Keeps what the transactions on the main network cost and moved. A short connection for
    each call."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def moments_to_read(self, *, projects: set[int] | None = None) -> list[str]:
        """The moments of the transactions of the own IDs on the main network that have no detail
        yet, oldest first; with `projects`, of these projects only."""
        with psycopg.connect(self._conninfo) as conn:
            wanted = (sorted(projects) if projects is not None
                      else [row[0] for row in conn.execute("SELECT id FROM projects")])  # fmt: skip
            ids = sorted({one for found in mainnet_ids(conn, wanted).values() for one in found})
            rows = conn.execute(
                "SELECT e.stamp FROM ledger_events e WHERE e.network = 'mainnet' "
                "AND e.entity_id = ANY(%s) AND NOT EXISTS (SELECT 1 FROM mainnet_transactions m "
                "WHERE m.stamp = e.stamp) GROUP BY e.stamp ORDER BY min(e.at), e.stamp",
                (ids,),
            ).fetchall()
        return [row[0] for row in rows]

    def save(self, detail: Detail, rate: Rate | None, asked_at: datetime) -> None:
        """What one transaction cost and moved, with the network's rate of its hour."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "INSERT INTO mainnet_transactions (stamp, at, name, ok, fee, moved, paid_by, "
                "tokens, cents, hbars, asked_at) VALUES (%s, to_timestamp(%s::numeric), %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (stamp) DO UPDATE SET name = "
                "EXCLUDED.name, ok = EXCLUDED.ok, fee = EXCLUDED.fee, moved = EXCLUDED.moved, "
                "paid_by = EXCLUDED.paid_by, tokens = EXCLUDED.tokens, cents = EXCLUDED.cents, "
                "hbars = EXCLUDED.hbars, asked_at = EXCLUDED.asked_at",
                (detail.stamp, detail.stamp, detail.name, detail.ok, detail.fee, detail.moved,
                 list(detail.paid_by), detail.tokens, rate.cents if rate else None,
                 rate.hbars if rate else None, asked_at),
            )  # fmt: skip

    # ------------------------------------------------------------- what they were (0029)

    def own_things(self, *, projects: set[int] | None = None) -> list[OwnThing]:
        """The own IDs on the main network, with the moments of their transactions that the step
        `mainnet_what` has not explained yet; with `projects`, of these projects only."""
        with psycopg.connect(self._conninfo) as conn:
            wanted = (sorted(projects) if projects is not None
                      else [row[0] for row in conn.execute("SELECT id FROM projects")])  # fmt: skip
            ids = sorted({one for found in mainnet_ids(conn, wanted).values() for one in found})
            rows = conn.execute(_OWN_THINGS, (wanted, wanted, WINDOW_BEFORE, ids)).fetchall()
        return [OwnThing(entity_id, ledger_id, kind, made_at, made_by, repository, since,
                         tuple(todo)) for entity_id, ledger_id, kind, made_at, made_by, repository,
                since, todo in rows]  # fmt: skip

    def explain(self, stamp: str, what: str | None, networks: Sequence[str],
                asked_at: datetime) -> None:  # fmt: skip
        """What one transaction did. The first explanation stays: a schedule names the moment
        that it ran before the account whose history holds that moment is read."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "UPDATE mainnet_transactions SET what = %s, networks = %s, explained_at = %s "
                "WHERE stamp = %s AND explained_at IS NULL",
                (what[:120] if what else None, list(networks), asked_at, stamp),
            )

    def makers(self) -> dict[str, str | None]:
        """The things already read, each with the account that made it."""
        with psycopg.connect(self._conninfo) as conn:
            return dict(conn.execute("SELECT entity_id, made_by FROM mainnet_things").fetchall())

    def mark_followed(self, account: str, how: str, asked_at: datetime) -> None:
        """Whether what an account made was read ("read") or not, as a service's ("service")."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "INSERT INTO mainnet_things (entity_id, kind, followed, asked_at) VALUES (%s, "
                "'account', %s, %s) ON CONFLICT (entity_id) DO UPDATE SET followed = "
                "EXCLUDED.followed",
                (account, how, asked_at),
            )

    def save_thing(self, thing: Thing, asked_at: datetime) -> None:
        """A thing on the main network, read now; a later reading replaces it."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "INSERT INTO mainnet_things (entity_id, kind, made_at, made_by, name, fields, "
                "names_from, scheduled, executed_at, held_by_others, messages, asked_at) VALUES "
                "(%s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s::numeric), %s, %s, %s) "
                "ON CONFLICT (entity_id) DO UPDATE SET kind = EXCLUDED.kind, made_at = "
                "EXCLUDED.made_at, made_by = EXCLUDED.made_by, name = EXCLUDED.name, fields = "
                "EXCLUDED.fields, names_from = coalesce(EXCLUDED.names_from, "
                "mainnet_things.names_from), scheduled = EXCLUDED.scheduled, executed_at = "
                "EXCLUDED.executed_at, held_by_others = EXCLUDED.held_by_others, messages = "
                "EXCLUDED.messages, asked_at = EXCLUDED.asked_at",
                (thing.entity_id, thing.kind, thing.made_at, thing.made_by,
                 thing.name[:160] if thing.name else None, list(thing.fields), thing.names_from,
                 thing.scheduled, thing.executed, thing.held_by_others, thing.messages, asked_at),
            )  # fmt: skip
