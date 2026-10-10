"""What a walk through the Hedera list of the showcase found, kept in one file.

The pages of the list are never saved. This file keeps three things for each project of the
list: the address of its page, the name of its event, and the ids of the sponsors that gave it a
prize (most projects have none). It holds no text of a page and nothing about a person.

The file is written after every page of the list, so a walk that stops can go on later from the
next page, and no page is asked for twice.

Two pages of the list share one row: a page shows 33 rows, and the last one is the first row of
the next page (seen on the real list on 10 October 2026). That row is taken once.
"""

from __future__ import annotations

import json
import os
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

from hackathon_memory.collect.ethglobal_list import ListedProject, ListPage, list_url
from hackathon_memory.collect.ethglobal_site import SITE, looks_like_a_project_page
from hackathon_memory.collect.polite import CollectorRefused

# 1 kept only the projects with a prize, and a count of the others. 2 keeps every project.
FOUND_FORMAT = 2


@dataclass(frozen=True)
class FoundProject:
    page: str  # the address of the project page
    event: str
    sponsors: tuple[str, ...]  # the ids of the sponsors that gave it a prize. Empty: no prize.
    list_page: int  # the page of the list that named it


@dataclass
class FoundList:
    started_at: str = ""
    updated_at: str = ""
    pages_read: int = 0  # the pages 1 to pages_read of the list were read
    complete: bool = False  # the last page of the list was reached
    projects: list[FoundProject] = field(default_factory=list)  # in the order of the list
    # How often a page did not start with the last row of the page before. On the real list it
    # always does. When it does not, the list moved while it was read, and a row may be missing.
    page_ends_not_shared: int = 0

    @property
    def listed(self) -> int:
        return len(self.projects)

    @property
    def listed_by_event(self) -> dict[str, int]:
        """How many projects each event has, in the order in which the list shows the events."""
        counts: dict[str, int] = {}
        for project in self.projects:
            counts[project.event] = counts.get(project.event, 0) + 1
        return counts

    @property
    def with_prize(self) -> list[FoundProject]:
        return [project for project in self.projects if project.sponsors]

    def add(self, page: ListPage, when: str) -> tuple[ListedProject, ...]:
        """Take in the next page of the list, and return its rows that are new.

        Pages come in order, each one once. The row that a page shares with the page before it
        is not new, and neither is a project that an earlier page already named.
        """
        if self.complete or page.number != self.pages_read + 1:
            raise ValueError("the pages of the list are added in order, each one once")
        rows = page.projects
        if page.number > 1 and rows:
            if self.projects and rows[0].page == self.projects[-1].page:
                rows = rows[1:]
            else:
                self.page_ends_not_shared += 1
        known = {project.page for project in self.projects}
        new: list[ListedProject] = []
        for row in rows:
            if row.page not in known:
                known.add(row.page)
                new.append(row)
                self.projects.append(FoundProject(row.page, row.event, row.sponsors, page.number))
        self.pages_read = page.number
        self.complete = not page.has_next
        self.updated_at = when
        return tuple(new)


class SponsorNotKnown(Exception):
    """The pages seen by hand do not tell which sponsor id is Hedera."""


def hedera_sponsor(found: FoundList, seen_by_hand: Collection[str]) -> str:
    """The id that the list uses for the sponsor Hedera.

    The list names a sponsor by an id, not by its name, so the id of Hedera cannot be read from
    it. It is not guessed either (the most common id is only a guess). The pages that a person
    saw with a Hedera prize decide: Hedera is the one id that every one of them has. When they
    point to no id, or to more than one, nobody knows, and SponsorNotKnown says so.
    """
    sponsors_of = {project.page: set(project.sponsors) for project in found.with_prize}
    seen = [sponsors_of[page] for page in seen_by_hand if page in sponsors_of]
    if not seen:
        raise SponsorNotKnown(
            "None of the pages seen by hand is in the walk with a prize, so nothing tells which "
            "sponsor id is Hedera."
        )
    shared = set.intersection(*seen)
    if len(shared) != 1:
        raise SponsorNotKnown(
            f"The {len(seen)} page(s) seen by hand that the walk knows share {len(shared)} "
            "sponsor ids, not exactly one, so the id of Hedera is not sure. Add a page that "
            "took a prize of Hedera only."
        )
    return next(iter(shared))


def winners_of(found: FoundList, sponsor: str) -> list[str]:
    """The pages of the projects that took a prize of this sponsor, in the order of the list."""
    return [project.page for project in found.projects if sponsor in project.sponsors]


def save_found(path: Path, found: FoundList) -> None:
    record = {
        "format": FOUND_FORMAT,
        "site": SITE,
        "list": list_url(1),
        "started_at": found.started_at,
        "updated_at": found.updated_at,
        "pages_read": found.pages_read,
        "complete": found.complete,
        "page_ends_not_shared": found.page_ends_not_shared,
        "projects": [
            {
                "page": project.page,
                "event": project.event,
                "sponsors": list(project.sponsors),
                "list_page": project.list_page,
            }
            for project in found.projects
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def load_found(path: Path) -> FoundList | None:
    """What an earlier walk found, or None when there was none.

    A file that cannot be read is not taken for "no walk yet": a new walk would then ask for
    pages that were already read. It is refused until somebody repairs it or moves it away.
    """
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        older = record["format"] == 1 and record["site"] == SITE
    except (OSError, ValueError, KeyError, TypeError):
        older = False
        record = None
    if older:
        raise CollectorRefused(
            f"The file of the walk is from an older walk that kept only the projects with a "
            f"prize: {path}. Move it away and walk again: the walk now keeps every project of "
            "the list."
        )
    try:
        if record["format"] != FOUND_FORMAT or record["site"] != SITE:
            raise ValueError("not a file of this walk")
        found = FoundList(
            started_at=str(record["started_at"]),
            updated_at=str(record["updated_at"]),
            pages_read=_count(record["pages_read"]),
            complete=_flag(record["complete"]),
            projects=[_project(item) for item in record["projects"]],
            page_ends_not_shared=_count(record["page_ends_not_shared"]),
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        raise CollectorRefused(
            f"The file of the walk through the list cannot be read: {path}. "
            "Repair it or move it away. It is not taken for an empty one."
        ) from None
    return found


def _count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("not a count")
    return value


def _flag(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("not yes or no")
    return value


def _project(item: dict) -> FoundProject:
    page, sponsors, event = item["page"], item["sponsors"], item["event"]
    if not isinstance(page, str) or not looks_like_a_project_page(page):
        raise ValueError("not a project page")
    if not isinstance(sponsors, list):
        raise ValueError("the sponsors are a list")
    if not all(isinstance(sponsor, str) and sponsor for sponsor in sponsors):
        raise ValueError("a sponsor is named by an id")
    if not isinstance(event, str) or not event:
        raise ValueError("a project names its event")
    return FoundProject(page, event, tuple(sponsors), _count(item["list_page"]))
