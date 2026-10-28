"""The drawing of the strip of days of a card (design 7.5, 25 October 2026).

check/depth.py counts the transactions of a project's own IDs for each service and each day of
the time of its ledger story. This module turns those counts into the shapes of a small SVG: one
row for each service, one square for each day with a transaction, its shade by the number of
transactions on a log scale, and the days of the event as a band behind the rows. The shapes are
made on the server, as the graph's are (web/graph.py), so the page needs no chart library.

One colour: the shade tells how many, and every square also has a border in the full colour, so
that a light square still stands out from the page (WCAG 1.4.11, non-text contrast). The number
of each square is in its note and in the table under the strip.

The drawing is about as wide as the column of a card (WIDTH), so that its words keep their size:
at 640 units in a column of about 370 pixels they shrank to 6 pixels (seen on 25 October 2026).
The rows carry short names; the table under the strip gives the full ones.

The days widen (design 12.1, S2, 28 October 2026): the names of the rows are a drawing of their own
that stays in place, and the days are a second drawing, whose shapes are placed from the start of
the days, inside a band that scrolls sideways. The page's script stretches only their places and
widths, so the words keep their size; it shows one short date of every few days when they are wide
enough (ticks), up to MOST_DAYS_IN_VIEW days across the strip.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from hackathon_memory.check.depth import Day, Strip
from hackathon_memory.check.history import CONSENSUS, CONTRACTS, FILES, HBAR, SCHEDULED, TOKENS
from hackathon_memory.web.data import SERVICE_TRANSACTIONS

WIDTH = 400  # the units of the drawing, about the pixels of a card's column
LEFT = 72  # room for the short names of the services
SHORT_NAMES = {CONSENSUS: "Consensus", TOKENS: "Tokens", CONTRACTS: "Contracts",
               SCHEDULED: "Schedules", FILES: "Files", HBAR: "HBAR"}  # fmt: skip
TOP = 4
ROW = 20  # the height of one row
FOOT = 20  # room for the days under the rows
LIGHTEST = 0.25  # the shade of one transaction; the most transactions of a day get 1
MOST_DAYS_IN_VIEW = 7  # the widest the days get: a week across the strip
HINT = ("Point at a square, or move to it with the keyboard, to see its day and its number. "
        "A click opens its first transaction on HashScan. Ctrl and the mouse wheel, or the "
        "buttons + and \u2212, widen the days.")  # fmt: skip


@dataclass(frozen=True)
class Square:
    x: float
    width: float
    ink: float  # the shade, from LIGHTEST to 1
    note: str  # its day, its service and its number, in words
    network: str
    first: str  # the moment of its first transaction


@dataclass(frozen=True)
class Row:
    service: str
    name: str  # its short name
    y: float
    squares: tuple[Square, ...]


@dataclass(frozen=True)
class Mark:
    x: float
    text: str
    anchor: str  # start, middle or end


@dataclass(frozen=True)
class Tick:
    x: float  # the middle of its day, from the start of the days
    text: str  # its day, short: "7 Mar"


@dataclass(frozen=True)
class TableRow:
    day: date
    service: str
    count: int


@dataclass(frozen=True)
class StripView:
    width: int  # the names and the days
    height: int
    left: int  # the names
    days_width: int  # the days, whose shapes are placed from 0
    rows: tuple[Row, ...]
    rows_bottom: float
    event_x: float
    event_width: float
    marks: tuple[Mark, ...]
    summary: str
    hint: str
    table: tuple[TableRow, ...]
    days: int = 0  # the days of the strip, one tick each
    ticks: tuple[Tick, ...] = ()
    most_zoom: float = 1.0  # how many times wider the days can get

    @property
    def names_share(self) -> float:
        """The part of the strip's width that the names take, in percent."""
        return round(self.left / self.width * 100, 4)


def in_words(day: date) -> str:
    return f"{day.day} {day:%B} {day.year}"


def transactions(service: str, count: int) -> str:
    words = SERVICE_TRANSACTIONS[service]
    return f"{count:,} {words if count != 1 else words[:-1]}"


def ink(count: int, most: int) -> float:
    """The shade of a day, on a log scale: one transaction is light, the busiest day is full."""
    if most <= 1:
        return 1.0
    return round(LIGHTEST + (1 - LIGHTEST) * math.log1p(count - 1) / math.log1p(most - 1), 3)


def strip_view(strip: Strip | None) -> StripView | None:
    """The shapes of a strip of days, or None when it has no transaction to draw."""
    if strip is None or not strip.rows:
        return None
    step = (WIDTH - LEFT) / strip.days

    def x_of(day: date) -> float:  # from the start of the days
        return (day - strip.first).days * step

    rows = []
    for number, (service, days) in enumerate(strip.rows):
        width = round(max(step - 1, 1.5), 2)
        squares = tuple(
            Square(round(x_of(one.day), 2), width, ink(one.count, strip.most),
                   f"{in_words(one.day)}: {transactions(service, one.count)}", one.network,
                   one.first)
            for one in days
        )  # fmt: skip
        rows.append(Row(service, SHORT_NAMES[service], TOP + number * ROW, squares))
    bottom = TOP + len(rows) * ROW
    event_x = x_of(strip.event_first)
    event_width = ((strip.event_last - strip.event_first).days + 1) * step
    marks = (
        Mark(0, in_words(strip.first), "start"),
        Mark(round(event_x + event_width / 2, 2), "the event", "middle"),
        Mark(WIDTH - LEFT, in_words(strip.last), "end"),
    )
    every_day = (strip.first + timedelta(days=number) for number in range(strip.days))
    ticks = tuple(Tick(round((number + 0.5) * step, 2), f"{day.day} {day:%b}")
                  for number, day in enumerate(every_day))  # fmt: skip
    active = len({one.day for _, days in strip.rows for one in days})
    summary = (f"The days of its transactions from {in_words(strip.first)} to "
               f"{in_words(strip.last)}: {active} day{'s' if active != 1 else ''} with a "
               "transaction. The same numbers are in the table under it.")  # fmt: skip
    table = tuple(sorted((TableRow(one.day, service, one.count)
                          for service, days in strip.rows for one in days),
                         key=lambda row: (row.day, row.service)))  # fmt: skip
    return StripView(WIDTH, int(bottom + FOOT), LEFT, WIDTH - LEFT, tuple(rows), bottom,
                     round(event_x, 2), round(event_width, 2), marks, summary, HINT, table,
                     strip.days, ticks,
                     round(max(2.0, strip.days / MOST_DAYS_IN_VIEW), 2))  # fmt: skip


__all__ = ["Day", "StripView", "strip_view"]
