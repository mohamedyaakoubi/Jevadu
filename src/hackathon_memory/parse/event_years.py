"""The year of each event that no page dates, typed in by hand (design 4.6, migration 0012).

The events known only from an organiser's list of winners (the posts of Hedera, the page of the
Africa hackathon, the post of Hedera x AI, an archived page of Hedera18) give no start and no end,
so their year was missing from the filters and the overview. A person types it from the
organiser's own post. One line for each event: the site, the short name of the event in the
tables, and its year. A comment after "#" may say where the year was read.

    hedera.com  hello-future-2024  2024   # the title of Hedera's post of the winners

When the organiser's post gives the days of the event, a line also carries its first and its last
day, and they become the start and the end of the event (design 7.2):

    hedera.com  hello-future-2024  2024  2024-07-22  2024-08-20  # "Running from July 22 to ..."

An event with a known start or end keeps the year of its dates; the typed year is used only when
no date is known.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

FILE_NAME = "event-years.txt"
_SITE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,79}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_YEAR = re.compile(r"^(20[1-9][0-9])$")
_DAY = re.compile(r"^20[1-9][0-9]-[01][0-9]-[0-3][0-9]$")


class EventYearsError(Exception):
    """The file of the years of events has a line that cannot be read. Nothing of it is used."""


def _lines(path: Path) -> Iterator[tuple[str, list[str]]]:
    """Each line of the file that is not empty, without its comment: where it stands, for an
    error, and its parts. No file gives none."""
    if not path.exists():
        return
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if line:
            yield f"{path.name}, line {number}", line.split()


def read_event_years(path: Path) -> dict[tuple[str, str], int]:
    """The year of each event that the file names, by site and short name. No file gives none."""
    years: dict[tuple[str, str], int] = {}
    for where, parts in _lines(path):
        if (len(parts) not in (3, 5) or not _SITE.match(parts[0]) or not _SLUG.match(parts[1])
                or not _YEAR.match(parts[2])):  # fmt: skip
            raise EventYearsError(
                f"{where}: expected a site, the short name of an event and its year, like "
                "hedera.com hello-future-2024 2024, and maybe its first and its last day"
            )
        if len(parts) == 5:
            _days(where, parts)  # two days that do not make a time stop the whole file
        key = (parts[0], parts[1])
        if key in years:
            raise EventYearsError(f"{where}: the event {parts[1]} of {parts[0]} has a second line")
        years[key] = int(parts[2])
    return years


def _days(where: str, parts: list[str]) -> tuple[date, date]:
    try:
        first, last = date.fromisoformat(parts[3]), date.fromisoformat(parts[4])
    except ValueError:
        first = last = None
    if not (_DAY.match(parts[3]) and _DAY.match(parts[4]) and first and last and first <= last):
        raise EventYearsError(
            f"{where}: expected a first and a last day, like 2024-07-22 2024-08-20"
        )
    return first, last


def read_event_days(path: Path) -> dict[tuple[str, str], tuple[date, date]]:
    """The first and the last day of each event that a line gives them for, by site and short
    name. The file is read as for the years, so a line that cannot be read stops it too."""
    read_event_years(path)  # the same checks of every line
    return {(parts[0], parts[1]): _days(where, parts)
            for where, parts in _lines(path) if len(parts) == 5}  # fmt: skip
