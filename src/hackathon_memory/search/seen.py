"""Projects that came back: the same project at two events or more (design 8.4).

Two projects are the same when they share a repository, or a Hedera ID on the same network that
the ledger found. An ID counts by the ID that the ledger gives the thing on that network, so that
an EVM address and the 0.0 ID of one contract are one ID (28 October 2026: a README that named a
contract by its address was not matched with a page that named its 0.0 ID). An ID that more than
three projects with other code name is a shared service, such as a popular token, and joins
nothing. So is an ID that two projects with other code name at one event: teams of one hackathon
that use one ID most likely use a service, such as a public payment address, and are not one
team. A returning name is only a hint and joins nothing.
Exact matching, with no AI.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

import psycopg

from hackathon_memory.db.public_services import public_keys

# The checks that found the ID as the kind the project gave: the ledger knows what it is.
CONFIRMED = ("proof_found", "window_not_known", "dates_do_not_fit", "found_but_empty")
SHARED_AFTER = 3  # projects with other code that may name one ID before it is a shared service

# The (project, network:ID) pairs that the ledger found as the kind the project gave. An ID is the
# one that the ledger gives the thing on that network where it found it (coalesce), and the name
# itself where it found nothing.
_FOUND = (
    "SELECT DISTINCT h.project_id, c.network || ':' || coalesce(f.ledger_id, h.entity_id) "
    "FROM hedera_ids h "
    "JOIN id_checks c ON c.hedera_id = h.id AND c.status = ANY(%s) "
    "LEFT JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network AND f.found"
)
# Every (project, network:ID) pair that a page or a README names, found or not, on each network
# it was asked on; an ID never asked counts on both networks. With the repository and the event of
# the project, and the name that the text writes.
_NAMED = (
    "SELECT DISTINCT h.project_id, n.network || ':' || coalesce(f.ledger_id, h.entity_id), "
    "p.repository_id, p.event_id, h.entity_id FROM hedera_ids h "
    "JOIN projects p ON p.id = h.project_id "
    "LEFT JOIN id_checks c ON c.hedera_id = h.id "
    "CROSS JOIN LATERAL (SELECT unnest(CASE WHEN c.network IS NULL "
    "THEN ARRAY['mainnet', 'testnet'] ELSE ARRAY[c.network] END) AS network) n "
    "LEFT JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = n.network AND f.found"
)


@dataclass(frozen=True)
class Member:
    project_id: int
    event: tuple[str, str]  # the site and the short name of the event
    repository_id: int | None


def shared_services(named: Iterable[tuple[str, int, object]]) -> set[str]:
    """The network:IDs that are shared services, which join nothing: those that more than
    SHARED_AFTER codes name in all, and those that two codes or more name at one event. On 18
    October 2026 three teams of one event, each with its own code, named one account of the main
    network, and the old rule made them one group. `named` holds (network:ID, code, event)
    triples; the code of a project is its repository, or the project itself when it has none."""
    codes: dict[str, set[int]] = defaultdict(set)
    at_event: dict[tuple[str, object], set[int]] = defaultdict(set)
    for key, code, event in named:
        codes[key].add(code)
        at_event[(key, event)].add(code)
    shared = {key for key, found in codes.items() if len(found) > SHARED_AFTER}
    return shared | {key for (key, _), found in at_event.items() if len(found) > 1}


def groups(
    members: Iterable[Member],
    ids: Iterable[tuple[int, str]],
    named: Iterable[tuple[int, str]] | None = None,
    public: Collection[str] = frozenset(),
) -> list[list[int]]:
    """The groups of projects that share a repository or a Hedera ID and stand at two events or
    more, each group in the order of its project ids. `ids` holds the (project, network:ID) pairs
    that the ledger found, which may join projects; `named` holds every pair that a page or a
    README names, found or not, and decides which IDs are shared services (by default `ids`);
    `public` the public services that their owners list, which join nothing either."""
    found = {member.project_id: member for member in members}
    ids = list(ids)
    shared = shared_services(
        (key, found[pid].repository_id or -pid, found[pid].event)
        for pid, key in (ids if named is None else named)
        if pid in found
    ) | set(public)
    parent = {pid: pid for pid in found}

    def root(pid: int) -> int:
        while parent[pid] != pid:
            parent[pid] = parent[parent[pid]]
            pid = parent[pid]
        return pid

    def join(together: list[int]) -> None:
        for other in together[1:]:
            parent[root(other)] = root(together[0])

    by_repository: dict[int, list[int]] = defaultdict(list)
    for member in found.values():
        if member.repository_id is not None:
            by_repository[member.repository_id].append(member.project_id)
    by_id: dict[str, list[int]] = defaultdict(list)
    for pid, key in ids:
        if pid in found and pid not in by_id[key]:
            by_id[key].append(pid)
    for together in by_repository.values():
        join(together)
    for key, together in by_id.items():
        if key not in shared:
            join(together)
    grouped: dict[int, list[int]] = defaultdict(list)
    for pid in sorted(found):
        grouped[root(pid)].append(pid)
    return [together for together in grouped.values()
            if len({found[pid].event for pid in together}) > 1]  # fmt: skip


def _collection(conn: psycopg.Connection) -> tuple[list[Member], list, list]:
    """Every project with its event and its repository, the (project, network:ID) pairs that the
    ledger found, and every pair that a page or a README names: each counts for a shared
    service."""
    members = [Member(pid, (site, slug), repository) for pid, site, slug, repository in
               conn.execute("SELECT p.id, e.site, e.slug, p.repository_id FROM projects p "
                            "JOIN events e ON e.id = p.event_id").fetchall()]  # fmt: skip
    ids = conn.execute(_FOUND, (list(CONFIRMED),)).fetchall()
    named = [(pid, key) for pid, key, _, _, _ in conn.execute(_NAMED).fetchall()]
    return members, ids, named


def came_back(conninfo: str) -> list[list[int]]:
    """The groups of projects that came back, read from the tables."""
    with psycopg.connect(conninfo) as conn:
        members, ids, named = _collection(conn)
        public = public_keys(conn)
    return groups(members, ids, named, public)


def links(
    members: Iterable[Member],
    ids: Iterable[tuple[int, str]],
    named: Iterable[tuple[int, str]],
    project_id: int,
    public: Collection[str] = frozenset(),
) -> list[tuple[int, str]]:
    """The projects that one project shares its repository or a Hedera ID with, by the rule of
    `groups` but with no chain, at its own event or at another: each as (project, "repository")
    or (project, "network:ID"), in the order of their numbers."""
    found = {member.project_id: member for member in members}
    own = found.get(project_id)
    if own is None:
        return []
    ids = list(ids)
    shared = shared_services(
        (key, found[pid].repository_id or -pid, found[pid].event)
        for pid, key in named
        if pid in found
    ) | set(public)
    linked: dict[int, str] = {}
    if own.repository_id is not None:
        for pid, member in found.items():
            if pid != project_id and member.repository_id == own.repository_id:
                linked[pid] = "repository"
    keys = {key for pid, key in ids if pid == project_id and key not in shared}
    for pid, key in sorted(ids):
        if pid != project_id and key in keys:
            linked.setdefault(pid, key)
    return sorted(linked.items())


def links_of(conninfo: str, project_id: int) -> list[tuple[int, str]]:
    """The links of one project, read from the tables."""
    with psycopg.connect(conninfo) as conn:
        members, ids, named = _collection(conn)
        public = public_keys(conn)
    return links(members, ids, named, project_id, public)


@dataclass(frozen=True)
class Matches:
    """What the collection says about the repository and the Hedera IDs of one submission."""

    same_repository: list[int]  # the projects with the same repository
    same_id: dict[str, list[int]]  # network:ID -> the projects whose ID the ledger found too
    shared: set[str]  # the network:IDs that are shared services, which join nothing
    # the IDs, on any network, that a project with other code names: as its text writes them,
    # and as the ledger gives them
    named_by_other_code: set[str]


def submission_matches(
    conninfo: str, repository: str, ids: Sequence[tuple[str, str, str]]
) -> Matches:
    """The projects that one submission shares its repository or an ID with, by the rule of
    `groups`. `ids` are the IDs of the submission that the ledger found as the kind its README
    gives, each as (network, the name that the README writes, the ID that the ledger gives the
    thing). The submission counts as one more user of each of them."""
    keys = [f"{network}:{thing}" for network, _, thing in ids]
    names = sorted({name for _, name, _ in ids} | {thing for _, _, thing in ids})
    with psycopg.connect(conninfo) as conn:
        row = conn.execute("SELECT id FROM repositories WHERE url = %s", (repository,)).fetchone()
        own_code = row[0] if row else None
        same_repository = [pid for (pid,) in conn.execute(
            "SELECT id FROM projects WHERE repository_id = %s ORDER BY id", (own_code,)
        ).fetchall()] if own_code is not None else []  # fmt: skip
        found = conn.execute(_FOUND + " WHERE coalesce(f.ledger_id, h.entity_id) = ANY(%s)",
                             (list(CONFIRMED), names)).fetchall()  # fmt: skip
        named = conn.execute(_NAMED + " WHERE h.entity_id = ANY(%s) "
                             "OR coalesce(f.ledger_id, h.entity_id) = ANY(%s)",
                             (names, names)).fetchall()  # fmt: skip
        public = public_keys(conn)
    other_code: set[str] = set()
    for _, key, repository_id, _, name in named:
        if own_code is None or repository_id != own_code:
            other_code |= {name, key.split(":", 1)[1]}
    users = [(key, repository_id or -pid, event) for pid, key, repository_id, event, _ in named]
    # The submission, with no event of the collection; 0 is no project's number.
    users += [(key, own_code or 0, None) for key in keys]
    shared = (shared_services(users) | public) & set(keys)
    same_id: dict[str, list[int]] = defaultdict(list)
    for pid, key in sorted(found):
        if key in keys and key not in shared and pid not in same_id[key]:
            same_id[key].append(pid)
    return Matches(same_repository, dict(same_id), shared, other_code)


def counted(found: list[list[int]]) -> dict[str, int]:
    """How many groups came back, and how many projects they hold."""
    return {"groups": len(found), "projects": sum(len(together) for together in found)}
