"""Where the history of each own Hedera ID is kept (migrations 0016 and 0018, check/history.py).

An own ID is named by one project only, or only by projects that share one repository: an ID
that several teams name is often a shared service (design 8.4), and its history would say nothing
about one team; the entries of one team's code at several hackathons share its IDs (28 October
2026). Only an ID whose kind
fits what its page says is read: the statuses of the proof rule "proof found", "the dates do not
fit" and "found, but empty" (design 7.2).

Since 25 October 2026 each event also keeps what it was, and a token the accounts that hold it
(DEPTH 1, design 7.5). A history read before has none of it: it is read again, whole, once. A
history is then read on from its newest event (design 7.3), unless the limit of events cut it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg

from hackathon_memory.check.depth import Depth, Done, depth_of
from hackathon_memory.check.history import Act, History
from hackathon_memory.check.proof import DATES_DO_NOT_FIT, FOUND_BUT_EMPTY, PROOF_FOUND
from hackathon_memory.check.setup import Setup
from hackathon_memory.check.story import OwnId, Story, merged, on_its_network, story_of
from hackathon_memory.parse.hedera_ids import ACCOUNT

KINDS_THAT_FIT = (PROOF_FOUND, DATES_DO_NOT_FIT, FOUND_BUT_EMPTY)
DEPTH = 1  # what a history keeps: 1 since 25 October 2026, each act and a token's holders
# The own IDs, as the first part of a query that joins `own` (design 8.4): named by one project,
# or only by projects with one same repository.
OWN = (
    "WITH own AS (SELECT h.entity_id FROM hedera_ids h JOIN projects p ON p.id = h.project_id "
    "             GROUP BY h.entity_id HAVING count(DISTINCT h.project_id) = 1 "
    "             OR (count(DISTINCT p.repository_id) = 1 "
    "                 AND bool_and(p.repository_id IS NOT NULL))) "
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

    def ids_to_read(
        self, *, again: bool = False, projects: set[int] | None = None
    ) -> list[IdToRead]:
        """The own IDs whose kind fits and whose history was not read yet; with `again`, also
        those read before the depth of use; with `projects`, of these projects only."""
        older = " AND r.depth >= %s" if again else ""
        only = " AND h.project_id = ANY(%s)" if projects is not None else ""
        values: list[object] = [list(KINDS_THAT_FIT)]
        values += [DEPTH] if again else []
        values += [sorted(projects)] if projects is not None else []
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                OWN  # noqa: S608  (fixed text)
                + "SELECT DISTINCT h.entity_id, c.network, f.kind, f.ledger_id, f.created_at "
                "FROM hedera_ids h JOIN own USING (entity_id) "
                "JOIN id_checks c ON c.hedera_id = h.id "
                "JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network "
                "WHERE f.found AND c.status = ANY(%s) AND NOT EXISTS (SELECT 1 FROM "
                "  ledger_histories r WHERE r.entity_id = h.entity_id AND r.network = c.network"
                + older
                + ")"
                + only
                + " ORDER BY 1, 2",
                values,
            ).fetchall()
        return [IdToRead(*row) for row in rows]

    def ids_to_read_on(
        self, *, read_before: datetime, projects: set[int] | None = None
    ) -> list[tuple[IdToRead, datetime | None]]:
        """The own IDs whose history was read with the depth of use before `read_before` and not
        cut by the limit, each with the moment of its newest event: a reading goes on from there
        (design 7.3). A single transaction never changes, so it is not read on."""
        only = " AND h.project_id = ANY(%s)" if projects is not None else ""
        values: list[object] = [list(KINDS_THAT_FIT), DEPTH, read_before]
        values += [sorted(projects)] if projects is not None else []
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                OWN  # noqa: S608  (fixed text)
                + "SELECT DISTINCT h.entity_id, c.network, r.kind, f.ledger_id, f.created_at, "
                "(SELECT max(e.at) FROM ledger_events e "
                " WHERE e.entity_id = r.entity_id AND e.network = r.network) "
                "FROM hedera_ids h JOIN own USING (entity_id) "
                "JOIN id_checks c ON c.hedera_id = h.id "
                "JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network "
                "JOIN ledger_histories r ON r.entity_id = h.entity_id AND r.network = c.network "
                "WHERE f.found AND c.status = ANY(%s) AND r.depth >= %s AND NOT r.cut "
                "AND r.kind <> 'transaction' AND r.asked_at < %s" + only + " ORDER BY 1, 2",
                values,
            ).fetchall()
        return [(IdToRead(*row[:5]), row[5]) for row in rows]

    def saved(
        self, entity_id: str, network: str, *, since: datetime
    ) -> tuple[History, datetime] | None:
        """The history of an ID that was read at `since` or later with the depth of use, with
        the moment it was read; None when it was not read since then."""
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT asked_at, cut, holders, holders_cut FROM ledger_histories "
                "WHERE entity_id = %s AND network = %s AND asked_at >= %s AND depth >= %s",
                (entity_id, network, since, DEPTH),
            ).fetchone()
            if row is None:
                return None
            events = conn.execute(
                "SELECT stamp, service, name, ok, payer, parties FROM ledger_events "
                "WHERE entity_id = %s AND network = %s",
                (entity_id, network),
            ).fetchall()
        acts = {stamp: Act(name, ok, payer, tuple(parties or ()))
                for stamp, _, name, ok, payer, parties in events}  # fmt: skip
        holders = tuple(row[2]) if row[2] is not None else None
        history = History({stamp: service for stamp, service, *_ in events}, row[1], acts,
                          holders, row[3])  # fmt: skip
        return history, row[0]

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
                "INSERT INTO ledger_histories (entity_id, network, kind, asked_at, events, cut, "
                "depth, holders, holders_cut) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (entity_id, network, kind, asked_at, len(history.events), history.cut, DEPTH,
                 list(history.holders) if history.holders is not None else None,
                 history.holders_cut),
            )  # fmt: skip
            _insert_events(conn, entity_id, network, history)

    def read_on(self, entity_id: str, network: str, history: History, asked_at: datetime) -> int:
        """Add the events of a history read on (design 7.3) to the kept one, and return how many
        were new. A token's holders take the place of the old ones."""
        with psycopg.connect(self._conninfo) as conn:
            new = _insert_events(conn, entity_id, network, history)
            conn.execute(
                "UPDATE ledger_histories SET asked_at = %s, cut = cut OR %s, "
                "events = (SELECT count(*) FROM ledger_events e "
                "          WHERE e.entity_id = %s AND e.network = %s), "
                "holders = coalesce(%s, holders), holders_cut = %s "
                "WHERE entity_id = %s AND network = %s",
                (asked_at, history.cut, entity_id, network,
                 list(history.holders) if history.holders is not None else None,
                 history.holders_cut, entity_id, network),
            )  # fmt: skip
        return new


def _insert_events(conn: psycopg.Connection, entity_id: str, network: str, history: History) -> int:
    """Write the events of a history that the table does not hold yet; how many were new."""
    rows = []
    for stamp, service in history.events.items():
        act = history.acts.get(stamp) or Act(None, None, None)
        rows.append((entity_id, network, stamp, datetime.fromtimestamp(float(stamp), tz=UTC),
                     service, act.name, act.ok, act.payer, list(act.parties)))  # fmt: skip
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO ledger_events (entity_id, network, stamp, at, service, name, ok, payer, "
            "parties) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            rows,
        )
        # psycopg 3.3.6 (_cursor_base.py, _executemany_gen_no_pipeline): with no RETURNING the
        # count adds up the rows of every statement, and a row left out by ON CONFLICT counts 0.
        return max(cursor.rowcount, 0)


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


def depth_of_project(
    conn: psycopg.Connection,
    project_id: int,
    story: Story | None,
    *,
    in_code: frozenset[str] | None,
    set_up: frozenset[str] = frozenset(),
    has_package: bool = False,
) -> Depth | None:
    """The depth of use of one project (design 7.5), from the own IDs of its ledger story and
    what their transactions were; None when there is nothing to say. With no own ID, it says only
    what stays on paper: a Hedera package with no call, and IDs that other projects name too."""
    rows = conn.execute("SELECT DISTINCT entity_id FROM hedera_ids WHERE project_id = %s",
                        (project_id,)).fetchall()  # fmt: skip
    named = {row[0] for row in rows}
    (confirmed,) = conn.execute(
        "SELECT count(*) FROM hedera_ids h JOIN id_checks c ON c.hedera_id = h.id "
        "WHERE h.project_id = %s AND c.status = ANY(%s)",
        (project_id, list(KINDS_THAT_FIT)),
    ).fetchone()
    own_ids = story.ids if story is not None else ()
    shared_only = bool(confirmed) and not own_ids
    starts_at, ends_on = conn.execute(
        "SELECT e.starts_at, e.ends_on FROM projects p JOIN events e ON e.id = p.event_id "
        "WHERE p.id = %s",
        (project_id,),
    ).fetchone() or (None, None)
    if not own_ids and not shared_only and not has_package:
        return None
    read = [one for one in own_ids if one.asked_at is not None]
    entities = [one.entity_id for one in read]
    kinds = {(one.entity_id, one.network): one.kind or "" for one in read}
    done: list[Done] = []
    depths: dict[tuple[str, str], int] = {}
    holders: dict[tuple[str, str], tuple[str, ...] | None] = {}
    if entities:
        for entity, network, depth, kept in conn.execute(
            "SELECT entity_id, network, depth, holders FROM ledger_histories "
            "WHERE entity_id = ANY(%s)",
            (entities,),
        ):
            if (entity, network) in kinds:
                depths[(entity, network)] = depth
                holders[(entity, network)] = tuple(kept) if kept is not None else None
        for entity, network, stamp, at, service, name, ok, payer, parties in conn.execute(
            "SELECT entity_id, network, stamp, at, service, name, ok, payer, parties "
            "FROM ledger_events WHERE entity_id = ANY(%s)",
            (entities,),
        ):
            kind = kinds.get((entity, network))
            if kind is not None:
                act = Act(name, ok, payer, tuple(parties or ()))
                done.append(Done(stamp, at, service, entity, kind, network, act))
    all_read = len(read) == len(own_ids) and all(depths.get(key, 0) >= DEPTH for key in kinds)
    # how each own ID is set up, as the check of the IDs kept it (design 7.5)
    wanted = {(one.entity_id, one.network) for one in own_ids}
    setups = [Setup(entity, network, kind, details or {}, asked_at)
              for entity, network, kind, details, asked_at in conn.execute(
                  "SELECT entity_id, network, kind, details, asked_at FROM ledger_facts "
                  "WHERE found AND entity_id = ANY(%s)", ([one.entity_id for one in own_ids],))
              if (entity, network) in wanted]  # fmt: skip
    return depth_of(own_ids, done, holders, named, starts_at=starts_at, ends_on=ends_on,
                    in_code=in_code, set_up=set_up, has_package=has_package,
                    shared_only=shared_only, read=all_read, setups=setups)  # fmt: skip
