"""Projects that came back: the same project at two events or more (design 8.4).

Two projects are the same when they share a repository, or a Hedera ID on the same network that
the ledger found. An ID that more than three projects with other code name is a shared service,
such as a popular token, and joins nothing. A returning name is only a hint and joins nothing.
Exact matching, with no AI.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import psycopg

# The checks that found the ID as the kind the project gave: the ledger knows what it is.
CONFIRMED = ("proof_found", "window_not_known", "dates_do_not_fit", "found_but_empty")
SHARED_AFTER = 3  # projects with other code that may name one ID before it is a shared service

# The (project, network:ID) pairs that the ledger found as the kind the project gave.
_FOUND = (
    "SELECT DISTINCT h.project_id, c.network || ':' || h.entity_id FROM hedera_ids h "
    "JOIN id_checks c ON c.hedera_id = h.id AND c.status = ANY(%s)"
)
# Every (project, network:ID) pair that a page or a README names, found or not, on each network
# it was asked on; an ID never asked counts on both networks. With the repository of the project.
_NAMED = (
    "SELECT DISTINCT h.project_id, n.network || ':' || h.entity_id, p.repository_id "
    "FROM hedera_ids h JOIN projects p ON p.id = h.project_id "
    "LEFT JOIN id_checks c ON c.hedera_id = h.id "
    "CROSS JOIN LATERAL (SELECT unnest(CASE WHEN c.network IS NULL "
    "THEN ARRAY['mainnet', 'testnet'] ELSE ARRAY[c.network] END) AS network) n"
)


@dataclass(frozen=True)
class Member:
    project_id: int
    event: tuple[str, str]  # the site and the short name of the event
    repository_id: int | None


def groups(
    members: Iterable[Member],
    ids: Iterable[tuple[int, str]],
    named: Iterable[tuple[int, str]] | None = None,
) -> list[list[int]]:
    """The groups of projects that share a repository or a Hedera ID and stand at two events or
    more, each group in the order of its project ids. `ids` holds the (project, network:ID) pairs
    that the ledger found, which may join projects; `named` holds every pair that a page or a
    README names, found or not, and decides which IDs are shared services (by default `ids`)."""
    found = {member.project_id: member for member in members}
    ids = list(ids)
    users: dict[str, set[int]] = defaultdict(set)
    for pid, key in ids if named is None else named:
        if pid in found:
            users[key].add(found[pid].repository_id or -pid)
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
        if len(users[key]) <= SHARED_AFTER:  # projects with other code that name it, in all
            join(together)
    grouped: dict[int, list[int]] = defaultdict(list)
    for pid in sorted(found):
        grouped[root(pid)].append(pid)
    return [together for together in grouped.values()
            if len({found[pid].event for pid in together}) > 1]  # fmt: skip


def came_back(conninfo: str) -> list[list[int]]:
    """The groups of projects that came back, read from the tables."""
    with psycopg.connect(conninfo) as conn:
        members = [Member(pid, (site, slug), repository) for pid, site, slug, repository in
                   conn.execute("SELECT p.id, e.site, e.slug, p.repository_id FROM projects p "
                                "JOIN events e ON e.id = p.event_id").fetchall()]  # fmt: skip
        ids = conn.execute(_FOUND, (list(CONFIRMED),)).fetchall()
        # Every project that names the ID counts for a shared service.
        named = [(pid, key) for pid, key, _ in conn.execute(_NAMED).fetchall()]
    return groups(members, ids, named)


@dataclass(frozen=True)
class Matches:
    """What the collection says about the repository and the Hedera IDs of one submission."""

    same_repository: list[int]  # the projects with the same repository
    same_id: dict[str, list[int]]  # network:ID -> the projects whose ID the ledger found too
    shared: set[str]  # the network:IDs that are shared services, which join nothing
    named_by_other_code: set[str]  # the IDs, on any network, that a project with other code names


def submission_matches(conninfo: str, repository: str, keys: Sequence[str]) -> Matches:
    """The projects that one submission shares its repository or an ID with, by the rule of
    `groups`. `keys` are the network:IDs of the submission that the ledger found as the kind
    its README gives. The submission counts as one more user of each of them."""
    entity_ids = sorted({key.split(":", 1)[1] for key in keys})
    with psycopg.connect(conninfo) as conn:
        row = conn.execute("SELECT id FROM repositories WHERE url = %s", (repository,)).fetchone()
        own_code = row[0] if row else None
        same_repository = [pid for (pid,) in conn.execute(
            "SELECT id FROM projects WHERE repository_id = %s ORDER BY id", (own_code,)
        ).fetchall()] if own_code is not None else []  # fmt: skip
        found = conn.execute(_FOUND + " WHERE h.entity_id = ANY(%s)",
                             (list(CONFIRMED), entity_ids)).fetchall()  # fmt: skip
        named = conn.execute(_NAMED + " WHERE h.entity_id = ANY(%s)", (entity_ids,)).fetchall()
    users: dict[str, set[int]] = defaultdict(set)
    other_code: set[str] = set()
    for pid, key, repository_id in named:
        users[key].add(repository_id or -pid)
        if own_code is None or repository_id != own_code:
            other_code.add(key.split(":", 1)[1])
    shared = set()
    for key in keys:
        users[key].add(own_code or 0)  # the submission itself; 0 is no project's number
        if len(users[key]) > SHARED_AFTER:
            shared.add(key)
    same_id: dict[str, list[int]] = defaultdict(list)
    for pid, key in sorted(found):
        if key in keys and key not in shared and pid not in same_id[key]:
            same_id[key].append(pid)
    return Matches(same_repository, dict(same_id), shared, other_code)


def counted(found: list[list[int]]) -> dict[str, int]:
    """How many groups came back, and how many projects they hold."""
    return {"groups": len(found), "projects": sum(len(together) for together in found)}
