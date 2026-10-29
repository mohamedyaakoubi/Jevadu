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

The whole time (28 October 2026, night): the strip also draws the days of the project's own things
long before and after the time of the table. A time of more than GAP days with no transaction is
cut out, and a hatched band of its own width marks the place, with its length under it: the days
around the event keep their width, and the event is drawn even when it has no transaction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from hackathon_memory.check.depth import Day, Strip
from hackathon_memory.check.history import CONSENSUS, CONTRACTS, FILES, HBAR, SCHEDULED, TOKENS
from hackathon_memory.check.story import Stop
from hackathon_memory.web.data import SERVICE_TRANSACTIONS, read_only

WIDTH = 400  # the units of the drawing, about the pixels of a card's column
LEFT = 72  # room for the short names of the services
SHORT_NAMES = {CONSENSUS: "Consensus", TOKENS: "Tokens", CONTRACTS: "Contracts",
               SCHEDULED: "Schedules", FILES: "Files", HBAR: "HBAR"}  # fmt: skip
TOP = 4
ROW = 20  # the height of one row
FOOT = 20  # room for the days under the rows
LINE = 16  # one more line under the rows, for the lengths of the times cut out
LIGHTEST = 0.25  # the shade of one transaction; the most transactions of a day get 1
MOST_DAYS_IN_VIEW = 7  # the widest the days get: a week across the strip
GAP = 30  # a time of more days than this with no transaction is cut out of the strip
CUT = 14  # the width of a time cut out, in units
LETTER = 7.2  # about the width of a letter of the marks (13 pixels), to keep them apart
HINT = ("Point at a square, or move to it with the keyboard, to see its day and its number. "
        "A click opens its first transaction on HashScan. Ctrl and the mouse wheel, or the "
        "buttons + and −, widen the days.")  # fmt: skip
LEGEND = ("A hatched band is a time of more than 30 days with no transaction, left out of the "
          "strip; its length stands under it.")  # fmt: skip


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
    event: bool = False  # the mark of the event; the others are the first and the last day


@dataclass(frozen=True)
class Tick:
    x: float  # the middle of its day, from the start of the days
    text: str  # its day, short: "7 Mar"


@dataclass(frozen=True)
class Cut:
    """A time with no transaction that the strip leaves out, or a time after a reading that the
    limit stopped, which was not read (29 October 2026)."""

    x: float
    width: float
    text: str  # how long it is, short: "1 yr 2 mo"
    note: str  # its first and last day, and how long, in words
    days: int = 0  # how many days it leaves out
    unread: bool = False  # it comes after a reading that the limit stopped


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
    days: int = 0  # the days drawn, one tick each
    ticks: tuple[Tick, ...] = ()
    most_zoom: float = 1.0  # how many times wider the days can get
    step: float = 0.0  # the width of one day
    cuts: tuple[Cut, ...] = ()
    # the lengths of the cuts that keep clear of each other, the longest cuts first
    cut_marks: tuple[Mark, ...] = ()
    legend: str = ""  # what a hatched band is, when the strip has one

    @property
    def names_share(self) -> float:
        """The part of the strip's width that the names take, in percent."""
        return round(self.left / self.width * 100, 4)


def in_words(day: date) -> str:
    return f"{day.day} {day:%B} {day.year}"


def short(day: date) -> str:
    return f"{day.day} {day:%b} {day.year}"


def transactions(service: str, count: int) -> str:
    words = SERVICE_TRANSACTIONS[service]
    return f"{count:,} {words if count != 1 else words[:-1]}"


def ink(count: int, most: int) -> float:
    """The shade of a day, on a log scale: one transaction is light, the busiest day is full."""
    if most <= 1:
        return 1.0
    return round(LIGHTEST + (1 - LIGHTEST) * math.log1p(count - 1) / math.log1p(most - 1), 3)


def runs(strip: Strip) -> list[tuple[date, date]]:
    """The runs of days that the strip draws, in order: the time of the table, and the days with a
    transaction before and after it. A run goes on while no more than GAP days without a
    transaction lie between two of its days."""
    outside = {one.day for _, days in strip.rows for one in days
               if one.day < strip.first or one.day > strip.last}  # fmt: skip
    found = sorted([(strip.first, strip.last), *((day, day) for day in outside)])
    joined = [found[0]]
    for first, last in found[1:]:
        if (first - joined[-1][1]).days - 1 <= GAP:
            joined[-1] = (joined[-1][0], max(joined[-1][1], last))
        else:
            joined.append((first, last))
    return joined


def length(days: int) -> tuple[str, str]:
    """How long a time without a transaction is, short and in words."""
    if days < 60:
        return f"{days} days", f"{days} days"
    years, months = divmod(round(days / 30.44), 12)
    parts = [(years, "yr", "year"), (months, "mo", "month")]
    shown = [(count, brief, word) for count, brief, word in parts if count]
    return (" ".join(f"{count} {brief}" for count, brief, _ in shown),
            " and ".join(f"{count} {word}{'s' if count != 1 else ''}"
                         for count, _, word in shown))  # fmt: skip


def apart(marks: list[Mark], width: float) -> tuple[Mark, ...]:
    """The marks that keep clear of every mark before them in the list, by the width of their
    letters, in the order of their places. A mark of the middle stays inside the drawing."""
    kept: list[tuple[float, float, Mark]] = []
    for mark in marks:
        size = len(mark.text) * LETTER
        if mark.anchor == "middle":
            mark = Mark(round(min(max(mark.x, size / 2), width - size / 2), 2), mark.text,
                        mark.anchor, mark.event)  # fmt: skip
        start = {"start": mark.x, "middle": mark.x - size / 2, "end": mark.x - size}[mark.anchor]
        if all(start + size + LETTER <= left or right + LETTER <= start for left, right, _ in kept):
            kept.append((start, start + size, mark))
    return tuple(mark for _, _, mark in sorted(kept, key=lambda one: one[0]))


def strip_view(strip: Strip | None) -> StripView | None:
    """The shapes of a strip of days, or None when it has no transaction to draw."""
    if strip is None or not strip.rows:
        return None
    width = WIDTH - LEFT
    parts = runs(strip)
    drawn = sum((last - first).days + 1 for first, last in parts)
    step = (width - CUT * (len(parts) - 1)) / drawn
    starts: list[float] = []
    place = 0.0
    for first, last in parts:
        starts.append(place)
        place += ((last - first).days + 1) * step + CUT

    def x_of(day: date) -> float:  # from the start of the days
        for (first, last), start in zip(parts, starts, strict=True):
            if first <= day <= last:
                return start + (day - first).days * step
        raise ValueError(f"{day} is not drawn")

    rows = []
    for number, (service, days) in enumerate(strip.rows):
        side = round(max(step - 1, 1.5), 2)
        squares = tuple(
            Square(round(x_of(one.day), 2), side, ink(one.count, strip.most),
                   f"{in_words(one.day)}: {transactions(service, one.count)}", one.network,
                   one.first)
            for one in days
        )  # fmt: skip
        rows.append(Row(service, SHORT_NAMES[service], TOP + number * ROW, squares))
    bottom = TOP + len(rows) * ROW
    event_x = x_of(strip.event_first)
    event_width = ((strip.event_last - strip.event_first).days + 1) * step
    cuts = []
    used: set[Stop] = set()  # the stopped readings that a band comes after
    for number in range(len(parts) - 1):
        (first, last), after = parts[number], parts[number + 1][0]
        empty = (after - last).days - 1
        brief, words = length(empty)
        x = starts[number] + ((last - first).days + 1) * step
        since, until = in_words(last + timedelta(days=1)), in_words(after - timedelta(days=1))
        # a reading that the limit stopped before this time: its transactions then were not read
        stopped = [stop for stop in strip.cut_off if stop.day < after]
        used.update(stopped)
        if stopped:
            note = (f"Not read: {read_only(stopped)}. The time from {since} to {until} ({words}) "
                    "is left out of the strip.")  # fmt: skip
        else:
            note = f"No transaction for {words}, from {since} to {until}: left out of the strip."
        cuts.append(Cut(round(x, 2), CUT, brief, note, empty, bool(stopped)))
    first_day, last_day = parts[0][0], parts[-1][1]
    marks = apart([Mark(event_x + event_width / 2, "the event", "middle", event=True),
                   Mark(0, short(first_day), "start"), Mark(width, short(last_day), "end")],
                  width)  # fmt: skip
    every_day = [first + timedelta(days=number) for first, last in parts
                 for number in range((last - first).days + 1)]  # fmt: skip
    ticks = tuple(Tick(round(x_of(day) + step / 2, 2), f"{day.day} {day:%b}") for day in every_day)
    active = len({one.day for _, days in strip.rows for one in days})
    unread = [cut for cut in cuts if cut.unread]
    empty_ones, unread_ones = len(cuts) - len(unread), len(unread)
    said = ([f"{empty_ones} time{'s' if empty_ones != 1 else ''} of more than {GAP} days with no "
             "transaction"] if empty_ones else [])  # fmt: skip
    said += [f"{unread_ones} time{'s' if unread_ones != 1 else ''} not read"] if unread else []
    left_out = f"; {' and '.join(said)} left out" if said else ""
    summary = (f"The days of its transactions from {in_words(first_day)} to "
               f"{in_words(last_day)}: {active} day{'s' if active != 1 else ''} with a "
               f"transaction{left_out}. The same numbers are in the table under it.")  # fmt: skip
    legend = LEGEND if cuts and not unread else ""
    if unread:
        after_them = tuple(stop for stop in strip.cut_off if stop in used)
        days = "that day" if len({stop.day for stop in after_them}) == 1 else "those days"
        others = ", and the others are times with no transaction" if empty_ones else ""
        legend = ("A hatched band is a time of more than 30 days left out of the strip; its "
                  f"length stands under it. {read_only(after_them)}, so a band after {days} is a "
                  f"time that was not read{others}.")  # fmt: skip
    table = tuple(sorted((TableRow(one.day, service, one.count)
                          for service, days in strip.rows for one in days),
                         key=lambda row: (row.day, row.service)))  # fmt: skip
    return StripView(WIDTH, int(bottom + FOOT + (LINE if cuts else 0)), LEFT, width, tuple(rows),
                     bottom, round(event_x, 2), round(event_width, 2), marks, summary, HINT,
                     table, drawn, ticks, round(max(2.0, drawn / MOST_DAYS_IN_VIEW), 2),
                     round(step, 4), tuple(cuts),
                     apart([Mark(cut.x + cut.width / 2, cut.text, "middle")
                            for cut in sorted(cuts, key=lambda one: -one.days)],
                           width), legend)  # fmt: skip


__all__ = ["Day", "StripView", "strip_view"]
