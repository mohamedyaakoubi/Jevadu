"""The list of hackathons in the check of a submission (design 12.1, S3).

The list holds the hackathons of the collection and the ones added by hand (hedera/listed.py).
The past ones are grouped by the year of their last day, so that the days of each one are short
and its name stands out: "ETHGlobal Cannes (4 to 6 July)" under 2025, and "ETHGlobal Cannes 2026
(3 to 5 April)" under 2026, where one line used to say "ETHGlobal Cannes 2026, 3 April 2026 to 5
April 2026". A list of the browser cannot colour a part of a line, and a list built by hand would
lose the keyboard and the screen reader, so the groups and the short days do this work.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from hackathon_memory.hedera.listed import Listed

RUNNING = "Running now"
COMING = "Coming"


@dataclass(frozen=True)
class Choice:
    value: str  # what the form sends
    text: str  # the name, then its days in brackets


@dataclass(frozen=True)
class Group:
    label: str
    choices: tuple[Choice, ...]


def _day(value: date, with_year: bool) -> str:
    return f"{value.day} {value:%B}" + (f" {value.year}" if with_year else "")


def days_of(first: date | None, last: date | None, group_year: int | None = None) -> str:
    """The days of a hackathon in few words, without the year when its group says it:
    "4 to 16 September", "21 July to 8 August", "28 December 2023 to 5 January 2024"."""
    if last is None:
        return f"from {_day(first, True)}" if first is not None else "days not announced yet"
    if first is None:
        return f"until {_day(last, True)}"
    with_year = first.year != last.year or last.year != group_year
    if first == last:
        return _day(last, with_year)
    if first.year == last.year and first.month == last.month:
        return f"{first.day} to {_day(last, with_year)}"
    return f"{_day(first, first.year != last.year)} to {_day(last, with_year)}"


def groups(
    collected: Iterable[tuple[str, str, date, date]], by_hand: Iterable[Listed], today: date
) -> list[Group]:
    """The groups of the list: the hackathons running now, the coming ones, then one group for
    each year, the newest first. In a year, the newest last day comes first."""
    running: list[Choice] = []
    coming: list[Choice] = []
    past = [(last, name, value, first) for value, name, first, last in collected]
    for one in by_hand:
        if one.last is not None and one.last < today:
            past.append((one.last, one.name, one.key, one.first))
            continue
        choice = Choice(one.key, f"{one.name} ({days_of(one.first, one.last)})")
        started = one.first is not None and one.first <= today
        (running if started else coming).append(choice)
    years: dict[int, list[Choice]] = {}
    for last, name, value, first in sorted(past, key=lambda row: (-row[0].toordinal(), row[1])):
        choice = Choice(value, f"{name} ({days_of(first, last, last.year)})")
        years.setdefault(last.year, []).append(choice)
    found = [Group(label, tuple(each)) for label, each in ((RUNNING, running), (COMING, coming))]
    found += [Group(str(year), tuple(years[year])) for year in sorted(years, reverse=True)]
    return [group for group in found if group.choices]
