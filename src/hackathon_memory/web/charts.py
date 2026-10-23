"""The charts of the page (design 12.1, S5): the counts of the list on the screen, a search or the
whole collection with its filters, read now from the tables and counted by search/counts.py, the
same way as the dated overview job (evals/overview.py). A share is shown only when 20 projects or
more stand behind it (a decision of 10 October 2026); nothing ranks or predicts.

What the projects with a Hedera prize use is set next to what the others use, as two shares of
the projects whose code was read. It says what winners used, not why they won.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from hackathon_memory.check.life import ACTIVE, QUIET, STOPPED, TOO_EARLY, UNKNOWN
from hackathon_memory.search import filters
from hackathon_memory.search.counts import Tally

SHARE_NEEDS = 20
EVENTS_SHOWN = 15
PACKAGES_SHOWN = 10
PROOF_LABELS = {
    "proof_found": "Proof found",
    "window_not_known": "Event end not known yet",
    "dates_do_not_fit": "Dates don't fit",
    "found_but_empty": "Empty ID",
    "another_kind": "Wrong kind of ID",
    "cannot_be_checked": "Can't be checked",
    "not_found": "ID not found",
    "no_id_given": "No ID given",
    filters.NOT_CHECKED: "Not checked yet",
}
LIFE_LABELS = {ACTIVE: "Active", QUIET: "Quiet", STOPPED: "Stopped",
               TOO_EARLY: "Too early to tell", UNKNOWN: "Unknown"}  # fmt: skip
SERVICE_LABELS = {
    "account": "Accounts",
    "topic": "Topics (Consensus Service)",
    "token": "Tokens (Token Service)",
    "contract": "Smart contracts",
    "schedule": "Scheduled transactions",
}


@dataclass(frozen=True)
class Bar:
    words: str
    count: int
    winners: int  # of them, the projects with a Hedera prize
    share: int | None  # of the projects behind the chart, when there are enough


@dataclass(frozen=True)
class Chart:
    key: str
    title: str
    tip: str
    note: str
    bars: tuple[Bar, ...]

    def data(self) -> str:
        """The numbers for Chart.js, as JSON."""
        return json.dumps({"labels": [bar.words for bar in self.bars],
                           "all": [bar.count for bar in self.bars],
                           "won": [bar.winners for bar in self.bars]})  # fmt: skip

    def summary(self) -> str:
        """The numbers in words, for a screen reader."""
        return "; ".join(f"{bar.words} {bar.count}" for bar in self.bars)


@dataclass(frozen=True)
class Pair:
    """One row of a comparison: how many projects with a Hedera prize have the fact, and how
    many of the others, each out of its own group."""

    words: str
    won: int
    won_of: int
    other: int
    other_of: int

    @property
    def won_share(self) -> int:
        return round(100 * self.won / self.won_of)

    @property
    def other_share(self) -> int:
        return round(100 * self.other / self.other_of)


@dataclass(frozen=True)
class Comparison:
    """Two shares side by side. It has rows only when each group holds SHARE_NEEDS projects."""

    key: str
    title: str
    tip: str
    note: str
    pairs: tuple[Pair, ...]

    def data(self) -> str:
        """The numbers for Chart.js, as JSON: two series of shares."""
        won = [pair.won_share for pair in self.pairs]
        other = [pair.other_share for pair in self.pairs]
        return json.dumps({"labels": [pair.words for pair in self.pairs], "unit": "%",
                           "series": [{"label": "With a Hedera prize", "color": "won", "data": won},
                                      {"label": "Without a Hedera prize", "color": "all",
                                       "data": other}]})  # fmt: skip

    def summary(self) -> str:
        """The numbers in words, for a screen reader."""
        return "; ".join(f"{pair.words}: {pair.won_share}% with a Hedera prize, "
                         f"{pair.other_share}% without" for pair in self.pairs)  # fmt: skip


@dataclass(frozen=True)
class EventRow:
    name: str
    year: str
    link: str | None
    projects: int
    winners: int


@dataclass(frozen=True)
class Charts:
    projects: int
    winners: int
    charts: tuple[Chart, ...]
    events: tuple[EventRow, ...]
    winners_use: Comparison | None = None

    def chart(self, key: str) -> Chart | None:
        """The chart of this key, to place it on its tab."""
        return next((one for one in self.charts if one.key == key), None)


def _bars(counts: Counter, won: Counter, order: Iterable[str], words: Mapping[str, str],
          behind: int) -> tuple[Bar, ...]:  # fmt: skip
    return tuple(
        Bar(words.get(key, key), counts[key], won.get(key, 0),
            round(100 * counts[key] / behind) if behind >= SHARE_NEEDS else None)
        for key in order if counts.get(key)
    )  # fmt: skip


def build(found: Tally, events: Mapping[str, tuple[str, str, str | None]]) -> Charts:
    """The charts of the projects counted in `found`. `events` gives the name, the year and the
    page of each event, by its number."""
    total = found.projects
    winners = (f"{found.winners} of them won a Hedera prize." if found.winners
               else "None of them won a Hedera prize.")  # fmt: skip
    others = total - found.with_theme
    if others and others == found.winner_entries:
        without = "Entries from a winners' list have none: no page to read."
    else:
        without = f"{others} have none." if others else ""
    busiest = [event for event, _ in found.events.most_common(EVENTS_SHOWN)]
    charts = (
        Chart("proof", "Hedera proof", "proof",
              f"The check of the Hedera IDs of these {total} projects. {winners}",
              _bars(found.proof, found.proof_won, filters.PROOF_ORDER, PROOF_LABELS, total)),
        Chart("life", "Activity after the event", "life",
              f"Commits or on-chain activity after the event, for these {total} projects.",
              _bars(found.life, found.life_won, filters.LIFE_ORDER, LIFE_LABELS, total)),
        Chart("services", "Hedera services used, confirmed by the ledger", "ledger",
              "Projects with at least one ID of each kind that the ledger confirms. A project can "
              "count in several rows.",
              _bars(found.services, found.services_won, tuple(SERVICE_LABELS), SERVICE_LABELS,
                    total)),
        Chart("themes", "Categories", "category",
              f"{found.with_theme} of these {total} projects have a category, chosen by Gemini "
              f"from their page. {without}".strip(),
              _bars(found.themes, found.themes_won,
                    sorted(found.themes, key=lambda key: (-found.themes[key], key)), {},
                    found.with_theme)),
        Chart("events", "Events", "event",
              f"The {min(len(busiest), EVENTS_SHOWN)} events with the most of these projects.",
              _bars(found.events, found.events_won, busiest,
                    {event: events.get(event, (event, "", None))[0] for event in busiest},
                    total)),
        *_code_charts(found),
    )  # fmt: skip
    rows = tuple(
        EventRow(*events.get(event, (event, "", None)), found.events[event],
                 found.events_won[event])
        for event in sorted(found.events, key=lambda e: (-found.events[e], events.get(e, (e,))[0]))
    )  # fmt: skip
    return Charts(total, found.winners, charts, rows, _winners_use(found))


def _most(counts: Counter) -> list[str]:
    """The keys, the largest count first, then by name."""
    return sorted(counts, key=lambda key: (-counts[key], key))


def _code_charts(found: Tally) -> tuple[Chart, Chart]:
    """What the reading of the code found (design 7.3), among the projects whose code was read."""
    read = found.code_read
    among = (f"of the {read} projects whose code was read" if read
             else "No project of this list has code that was read")  # fmt: skip
    services = Chart(
        "code_services", "Hedera services in the code", "code-services",
        f"Projects whose code calls each Hedera service, {among}. A project can count in several "
        "rows." if read else f"{among}.",
        _bars(found.code_services, found.code_services_won, _most(found.code_services), {}, read),
    )  # fmt: skip
    packages = Chart(
        "code_packages", "Hedera SDKs and libraries in the code", "code-packages",
        f"The Hedera packages that the code names most often, {among}." if read else f"{among}.",
        _bars(found.code_packages, found.code_packages_won,
              _most(found.code_packages)[:PACKAGES_SHOWN], {}, read),
    )  # fmt: skip
    return services, packages


def _winners_use(found: Tally) -> Comparison:
    """The Hedera services in the code of the projects with a Hedera prize, next to the others."""
    won_of = found.code_read_won
    other_of = found.code_read - won_of
    title, tip = "What winners use, next to the others", "winners-use"
    if won_of < SHARE_NEEDS or other_of < SHARE_NEEDS:
        note = (f"Too few projects to compare in this list: {won_of} with a Hedera prize and "
                f"{other_of} without have code that was read, and each side needs "
                f"{SHARE_NEEDS}.")  # fmt: skip
        return Comparison("winners_use", title, tip, note, ())
    note = (f"Among the projects whose code was read, {won_of} with a Hedera prize and {other_of} "
            "without: the share of each group whose code calls each Hedera service. It shows "
            "what winners used, not why they won.")  # fmt: skip
    pairs = tuple(
        Pair(key, found.code_services_won[key], won_of,
             found.code_services[key] - found.code_services_won[key], other_of)
        for key in _most(found.code_services)
    )  # fmt: skip
    return Comparison("winners_use", title, tip, note, pairs)
