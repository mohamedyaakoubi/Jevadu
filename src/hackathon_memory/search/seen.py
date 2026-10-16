"""Projects that came back: the same project at two events or more (design 8.4).

Two projects are the same when they share a repository, or a Hedera ID on the same network that
the ledger found. An ID that more than three projects with other code name is a shared service,
such as a popular token, and joins nothing. A returning name is only a hint and joins nothing.
Exact matching, with no AI.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
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


def counted(found: list[list[int]]) -> dict[str, int]:
    """How many groups came back, and how many projects they hold."""
    return {"groups": len(found), "projects": sum(len(together) for together in found)}
