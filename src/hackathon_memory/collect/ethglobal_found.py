"""What a walk through the Hedera list of the showcase found, kept in one file.

The pages of the list are never saved: they show projects that the site was not asked about. This
file keeps only what the next step needs. For a project of the list that took a prize: its
address, its event and the ids of the sponsors. For all the others: how many there are for each
event, and nothing more. It holds no text of a page and nothing about a person.

The file is written after every page of the list, so a walk that stops can go on later from the
next page, and no page is asked for twice.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from hackathon_memory.collect.ethglobal_list import ListPage, list_url
from hackathon_memory.collect.ethglobal_site import SITE, looks_like_a_project_page
from hackathon_memory.collect.polite import CollectorRefused

FOUND_FORMAT = 1


@dataclass(frozen=True)
class PrizeProject:
    page: str  # the address of the project page
    event: str
    sponsors: tuple[str, ...]  # the ids of the sponsors that gave it a prize
    list_page: int  # the page of the list that named it


@dataclass
class FoundList:
    started_at: str = ""
    updated_at: str = ""
    pages_read: int = 0  # the pages 1 to pages_read of the list were read
    complete: bool = False  # the last page of the list was reached
    listed_by_event: dict[str, int] = field(default_factory=dict)  # every project of the list
    with_prize: list[PrizeProject] = field(default_factory=list)

    @property
    def listed(self) -> int:
        return sum(self.listed_by_event.values())

    def add(self, page: ListPage, when: str) -> None:
        """Take in the next page of the list. Pages come in order, each one once."""
        if self.complete or page.number != self.pages_read + 1:
            raise ValueError("the pages of the list are added in order, each one once")
        known = {project.page for project in self.with_prize}
        for project in page.projects:
            self.listed_by_event[project.event] = self.listed_by_event.get(project.event, 0) + 1
            if project.sponsors and project.page not in known:
                self.with_prize.append(
                    PrizeProject(project.page, project.event, project.sponsors, page.number)
                )
        self.pages_read = page.number
        self.complete = not page.has_next
        self.updated_at = when


def save_found(path: Path, found: FoundList) -> None:
    record = {
        "format": FOUND_FORMAT,
        "site": SITE,
        "list": list_url(1),
        "started_at": found.started_at,
        "updated_at": found.updated_at,
        "pages_read": found.pages_read,
        "complete": found.complete,
        "listed_by_event": found.listed_by_event,
        "with_prize": [
            {
                "page": project.page,
                "event": project.event,
                "sponsors": list(project.sponsors),
                "list_page": project.list_page,
            }
            for project in found.with_prize
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
        if record["format"] != FOUND_FORMAT or record["site"] != SITE:
            raise ValueError("not a file of this walk")
        found = FoundList(
            started_at=str(record["started_at"]),
            updated_at=str(record["updated_at"]),
            pages_read=_count(record["pages_read"]),
            complete=_flag(record["complete"]),
            listed_by_event={
                str(event): _count(number) for event, number in record["listed_by_event"].items()
            },
            with_prize=[_prize_project(item) for item in record["with_prize"]],
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
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


def _prize_project(item: dict) -> PrizeProject:
    page, sponsors = item["page"], item["sponsors"]
    if not isinstance(page, str) or not looks_like_a_project_page(page):
        raise ValueError("not a project page")
    if not isinstance(sponsors, list) or not sponsors:
        raise ValueError("a project with a prize names a sponsor")
    if not all(isinstance(sponsor, str) and sponsor for sponsor in sponsors):
        raise ValueError("a sponsor is named by an id")
    return PrizeProject(page, str(item["event"]), tuple(sponsors), _count(item["list_page"]))
