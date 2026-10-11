"""The last day of each event, typed in by hand (design 7.2 and 10).

The proof rule needs the end of an event: its window runs from 30 days before the start to 14
days after the end. No project page gives the end. So a person types it into a small file, from
the page of the event, which a person may read in a browser.

One line for each event: the short name that the project pages give the event, and its last
day. A comment after "#" may say where the day was read.

    ethonline2024  2024-09-13   # the page of the event, read on 11 October 2026

The file lives in the data folder, next to the other files typed by hand, and is read by the
parse step every time it runs.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

FILE_NAME = "event-ends.txt"
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class EventEndsError(Exception):
    """The file of the ends of events has a line that cannot be read. Nothing of it is used."""


def read_event_ends(path: Path) -> dict[str, date]:
    """The last day of each event that the file names. No file gives no day."""
    if not path.exists():
        return {}
    ends: dict[str, date] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        where = f"{path.name}, line {number}"
        if len(parts) != 2 or not _SLUG.match(parts[0]) or not _DAY.match(parts[1]):
            raise EventEndsError(
                f"{where}: expected the short name of an event and its last day, like "
                "ethonline2024 2024-09-13"
            )
        slug, day = parts
        try:
            end = date.fromisoformat(day)
        except ValueError:
            raise EventEndsError(f"{where}: {day} is not a day of the calendar") from None
        if slug in ends:
            raise EventEndsError(f"{where}: the event {slug} has a second line")
        ends[slug] = end
    return ends
