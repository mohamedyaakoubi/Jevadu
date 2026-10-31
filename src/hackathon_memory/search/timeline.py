"""The timeline of projects that came back (design 8.7, 31 October 2026): the projects linked
across hackathons, oldest first, whatever they won, each with what it won, what its page said, what
its own Hedera IDs did around its event and its code at the end of its event, and between two of
them, how they are linked and how their code changed as GitHub counts it
(collect/github_history.py).

The groups are those of "seen before" (search/seen.py): the same repository or the same Hedera ID.
The code of two entries is compared only when they have the same repository; with two repositories,
or one with none, each entry shows its own code and the step says why nothing is compared. The
ledger's part is each project's own depth of use (design 7.5), from the ledger, whose times nobody
can change. The code's part rests on the dates of commits, which a team sets: the card says so.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
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

# What is known of the change of the code from one entry to the next.
COMPARED = "compared"  # GitHub's count of the change
SAME_COMMIT = "same_commit"  # the same commit at the end of both events
NOT_ASKED = "not_asked"  # an answer of GitHub is missing: the next reading asks for it
NO_COMMIT = "no_commit"  # GitHub gives no commit at the end of one of the two events
NOT_GIVEN = "not_given"  # GitHub gave no comparison of the two commits
OTHER_REPOSITORY = "other_repository"  # two repositories: nothing to compare
NO_REPOSITORY = "no_repository"  # one of the two has no known repository


@dataclass(frozen=True)
class Group:
    """Projects linked across events (search/seen.py), oldest event first."""

    project_ids: tuple[int, ...]
    last_days: tuple[date, ...]  # the last day of each one's event, in the same order
    repositories: tuple[str | None, ...]  # each one's repository, in the same order

    @property
    def repository(self) -> str | None:
        """The one repository of every project, or None when they differ or one has none."""
        found = set(self.repositories)
        return next(iter(found)) if len(found) == 1 and None not in found else None


def returning_groups(conninfo: str, projects: Iterable[int] | None = None) -> list[Group]:
    """Each group of projects linked across events (search/seen.py), with those of its projects
    whose event has a known last day, two or more; with `projects`, only the groups that hold one
    of them."""
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
        dated = sorted((rows[pid][1], pid) for pid in group if pid in rows and rows[pid][1])
        if len(dated) < 2:
            continue
        found.append(Group(tuple(pid for _, pid in dated), tuple(day for day, _ in dated),
                           tuple(rows[pid][0] for _, pid in dated)))  # fmt: skip
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
    repository: str | None
    commit: Version | None  # the newest commit on or before the last day; None: not asked

    @property
    def did_text(self) -> str:
        """What its own IDs did, in a few words: the first kinds, then how many more."""
        if not self.did:
            return "no transaction of its own Hedera IDs"
        shown = ", ".join(f"{count:,} {words}" for words, count in self.did[:SHOWN_KINDS])
        rest = sum(count for _, count in self.did[SHOWN_KINDS:]) + self.more
        return shown + (f", and {rest:,} more" if rest else "")


@dataclass(frozen=True)
class Step:
    """From one entry of the timeline to the next: how the two are linked, and what is known of
    the change of their code."""

    link: str | None  # "repository" or "network:ID" when the two are linked directly, else None
    state: str  # one of the states above
    change: github_history.Change | None = None  # GitHub's count, when compared
    page: str | None = None  # GitHub's page of the comparison, when compared


@dataclass(frozen=True)
class Timeline:
    entries: tuple[Entry, ...]
    steps: tuple[Step, ...]  # from each entry to the next

    @property
    def repository(self) -> str | None:
        """The one repository of every entry, or None when they differ or one has none."""
        found = {entry.repository for entry in self.entries}
        return next(iter(found)) if len(found) == 1 and None not in found else None


def _prize(sponsor: str | None, track: str | None, award: str | None) -> str:
    words = ": ".join(one for one in (sponsor, track) if one) or award or "a prize"
    return f"{words}, {award}" if award and track and award != track else words


def _step(store: RawStore, one: Entry, two: Entry, linked: Mapping[int, str]) -> Step:
    """What the timeline can say from `one` to `two`, from the saved answers of GitHub."""
    link = linked.get(two.project_id)
    if one.repository is None or two.repository is None:
        return Step(link, NO_REPOSITORY)
    if one.repository != two.repository:
        return Step(link, OTHER_REPOSITORY)
    first, second = one.commit, two.commit
    if first is None or second is None:
        return Step(link, NOT_ASKED)
    if not (first.sha and second.sha):
        return Step(link, NO_COMMIT)
    if first.sha == second.sha:
        return Step(link, SAME_COMMIT)
    repository = one.repository
    change = github_history.saved_change(store, repository, first.sha, second.sha)
    if change is not None:
        return Step(link, COMPARED, change,
                    github_history.compare_page(repository, first.sha, second.sha))  # fmt: skip
    if github_history.asked_change(store, repository, first.sha, second.sha):
        return Step(link, NOT_GIVEN)
    return Step(link, NOT_ASKED)


def timeline_of(conninfo: str, store: RawStore, project_id: int,
                depth_of: Callable[[int], Depth | None]) -> Timeline | None:  # fmt: skip
    """The timeline of the projects linked to `project_id` across events, or None when it did not
    come back, or when the last day of its event is not known. `depth_of` gives the depth of use
    of a project (from its card)."""
    groups = returning_groups(conninfo, [project_id])
    if not groups or project_id not in groups[0].project_ids:
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
    for pid, day, repository in zip(group.project_ids, group.last_days, group.repositories,
                                    strict=True):  # fmt: skip
        name, event, starts, line = rows[pid]
        depth = depth_of(pid)
        commit = github_history.saved_until(store, repository, day) if repository else None
        entries.append(Entry(pid, name, event, starts.date() if starts else None, day,
                             tuple(prizes[pid]), line or "", depth.did if depth else (),
                             depth.more_count if depth else 0, repository, commit))  # fmt: skip
    links = seen.links_within(conninfo, ids)
    steps = tuple(_step(store, one, two, dict(links.get(one.project_id, [])))
                  for one, two in pairwise(entries))  # fmt: skip
    return Timeline(tuple(entries), steps)
