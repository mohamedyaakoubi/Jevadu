"""The timeline of a team that came back (design 8.7, 31 October 2026): its projects at several
hackathons with one repository, oldest first, each with what it won, what its page said and what
its own Hedera IDs did around its event, and between two of them, how its code changed as GitHub
counts it (collect/github_history.py).

The groups are those of "seen before" (search/seen.py) whose projects all have one repository; a
group linked by a Hedera ID alone has no code to compare. The ledger's part is each project's own
depth of use (design 7.5), from the ledger, whose times nobody can change. The code's part rests
on the dates of commits, which a team sets: the card says so.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

import psycopg

from hackathon_memory.check.depth import Depth
from hackathon_memory.collect import github_history
from hackathon_memory.collect.github_commits import Version
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.search import seen

SHOWN_KINDS = 3  # the kinds of transaction named in a line of the timeline; the rest are counted


@dataclass(frozen=True)
class Group:
    """A team that came back: its projects with one repository, oldest event first."""

    repository: str
    project_ids: tuple[int, ...]
    last_days: tuple[date, ...]  # the last day of each one's event, in the same order


def groups_with_one_repository(conninfo: str, projects: Iterable[int] | None = None) -> list[Group]:
    """Each group of projects linked across events (search/seen.py) whose projects all have the
    same repository and a known last day, two or more; with `projects`, only the groups that hold
    one of them."""
    groups = seen.came_back(conninfo)
    wanted = set(projects) if projects is not None else None
    members = [pid for group in groups for pid in group]
    if not members:
        return []
    with psycopg.connect(conninfo) as conn:
        rows = {pid: (url, ends) for pid, url, ends in conn.execute(
            "SELECT p.id, r.url, e.ends_on FROM projects p JOIN events e ON e.id = p.event_id "
            "LEFT JOIN repositories r ON r.id = p.repository_id WHERE p.id = ANY(%s)",
            (members,)).fetchall()}  # fmt: skip
    found = []
    for group in groups:
        if wanted is not None and not wanted.intersection(group):
            continue
        urls = {rows[pid][0] for pid in group if pid in rows}
        dated = sorted((rows[pid][1], pid) for pid in group if pid in rows and rows[pid][1])
        if len(urls) != 1 or None in urls or len(dated) < 2:
            continue
        found.append(Group(urls.pop(), tuple(pid for _, pid in dated),
                           tuple(day for day, _ in dated)))  # fmt: skip
    return found


@dataclass(frozen=True)
class Entry:
    """One project of the timeline."""

    project_id: int
    name: str
    event: str
    starts: date | None
    ends: date
    prizes: tuple[str, ...]  # each prize it won, in the words of its page
    short_line: str
    did: tuple[tuple[str, int], ...]  # what its own IDs did around its event, most first
    more: int  # the transactions of the kinds not named in `did`
    commit: Version | None  # the newest commit on or before the last day of its event

    @property
    def did_text(self) -> str:
        """What its own IDs did, in a few words: the first kinds, then how many more."""
        if not self.did:
            return "no transaction of its own Hedera IDs"
        shown = ", ".join(f"{count:,} {words}" for words, count in self.did[:SHOWN_KINDS])
        rest = sum(count for _, count in self.did[SHOWN_KINDS:]) + self.more
        return shown + (f", and {rest:,} more" if rest else "")


@dataclass(frozen=True)
class Timeline:
    repository: str
    entries: tuple[Entry, ...]
    changes: tuple[github_history.Change | None, ...]  # from each entry to the next; None: not read

    def compare_page(self, index: int) -> str | None:
        """GitHub's page of the comparison from entry `index` to the next, when both are known."""
        one, two = self.entries[index].commit, self.entries[index + 1].commit
        if not (one and two and one.sha and two.sha):
            return None
        return github_history.compare_page(self.repository, one.sha, two.sha)


SAME = github_history.Change("identical", 0, 0, 0, 0)  # no commit between the two last days


def _prize(sponsor: str | None, track: str | None, award: str | None) -> str:
    words = ": ".join(one for one in (sponsor, track) if one) or award or "a prize"
    return f"{words}, {award}" if award and track and award != track else words


def timeline_of(conninfo: str, store: RawStore, project_id: int,
                depth_of: Callable[[int], Depth | None]) -> Timeline | None:  # fmt: skip
    """The timeline of the team of `project_id`, or None when it did not come back with one
    repository. `depth_of` gives the depth of use of a project (from its card)."""
    groups = groups_with_one_repository(conninfo, [project_id])
    if not groups:
        return None
    group = groups[0]
    ids = list(group.project_ids)
    with psycopg.connect(conninfo) as conn:
        rows = {pid: rest for pid, *rest in conn.execute(
            "SELECT p.id, p.name, e.name, e.starts_at, p.short_line FROM projects p "
            "JOIN events e ON e.id = p.event_id WHERE p.id = ANY(%s)",
            (ids,)).fetchall()}  # fmt: skip
        prizes: dict[int, list[str]] = defaultdict(list)
        for pid, sponsor, track, award in conn.execute(
            "SELECT project_id, sponsor, track, award FROM prizes WHERE project_id = ANY(%s) "
            "ORDER BY project_id, position", (ids,)):  # fmt: skip
            prizes[pid].append(_prize(sponsor, track, award))
    entries = []
    for pid, day in zip(group.project_ids, group.last_days, strict=True):
        name, event, starts, line = rows[pid]
        depth = depth_of(pid)
        entries.append(Entry(pid, name, event, starts.date() if starts else None, day,
                             tuple(prizes[pid]), line or "", depth.did if depth else (),
                             depth.more_count if depth else 0,
                             github_history.saved_until(store, group.repository, day)))  # fmt: skip
    changes: list[github_history.Change | None] = []
    for one, two in pairwise(entries):
        first, second = one.commit, two.commit
        if not (first and second and first.sha and second.sha):
            changes.append(None)
        elif first.sha == second.sha:
            changes.append(SAME)
        else:
            changes.append(github_history.saved_change(store, group.repository, first.sha,
                                                       second.sha))  # fmt: skip
    return Timeline(group.repository, tuple(entries), tuple(changes))
