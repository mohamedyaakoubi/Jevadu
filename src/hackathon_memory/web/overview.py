"""The overview of the projects (design 12.1, S5), read from the newest dated result file of
evals/overview.py (design rule 6): the counts of the events that the filters choose, added up.

A share is shown only when enough projects stand behind it (20, a decision of 10 October 2026);
under that, only the count. Nothing here predicts or ranks: these are counts of facts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from hackathon_memory.check.life import ACTIVE, QUIET, STOPPED, TOO_EARLY, UNKNOWN
from hackathon_memory.search import filters
from hackathon_memory.web import evidence

WON = "hedera_prize"
SERVICE_WORDS = {
    "account": "Accounts",
    "topic": "Topics of the Consensus Service",
    "token": "Tokens of the Token Service",
    "contract": "Smart contracts",
}
LIFE_WORDS = {ACTIVE: "Active", QUIET: "Quiet", STOPPED: "Stopped",
              TOO_EARLY: "Too early to tell", UNKNOWN: "Unknown"}  # fmt: skip
PRIZE_ORDER = ("hedera_prize", "other_prize", "no_prize")


@dataclass(frozen=True)
class Bar:
    words: str
    count: int
    winners: int  # of them, the projects with a Hedera prize
    share: int | None  # of the projects behind the block, when there are enough
    width: float  # of the longest bar of its block, for the drawing


@dataclass(frozen=True)
class Block:
    key: str
    title: str
    tip: str
    note: str
    bars: tuple[Bar, ...]


@dataclass(frozen=True)
class EventRow:
    name: str
    year: int | None
    projects: int
    hedera_prize: int
    other_prize: int
    no_prize: int
    winner_entries: int


@dataclass(frozen=True)
class Overview:
    made_on: str
    projects: int
    events: tuple[EventRow, ...]
    blocks: tuple[Block, ...]
    came_back: Mapping[str, int]
    share_needs: int


def _bars(all_counts: Counter, won: Counter, order: Iterable[str], words: Mapping[str, str],
          behind: int, needs: int) -> tuple[Bar, ...]:  # fmt: skip
    keys = [key for key in order if all_counts.get(key)]
    longest = max((all_counts[key] for key in keys), default=0)
    return tuple(
        Bar(words.get(key, key), all_counts[key], won.get(key, 0),
            round(100 * all_counts[key] / behind) if behind >= needs else None,
            100 * all_counts[key] / longest if longest else 0.0)
        for key in keys
    )  # fmt: skip


def build(data: Mapping, chosen: set[tuple[str, str]] | None,
          names: Mapping[tuple[str, str], str]) -> Overview:  # fmt: skip
    """The counts of the chosen events (all of them when `chosen` is None), added up."""
    needs = int(data.get("share_needs", 20))
    events = [event for event in data.get("events", [])
              if chosen is None or (event["site"], event["slug"]) in chosen]  # fmt: skip
    total: dict[str, Counter] = {name: Counter() for name in
                                 ("prize", "proof", "proof_won", "life", "life_won", "services",
                                  "services_won", "themes", "themes_won")}  # fmt: skip
    projects = with_theme = 0
    for event in events:
        projects += event["projects"]
        with_theme += event["with_theme"]
        total["prize"].update(event["prize"])
        for name in ("proof", "life", "services", "themes"):
            total[name].update(event[name]["all"])
            total[f"{name}_won"].update(event[name][WON])
    won = total["prize"].get(WON, 0)
    winners = f"{won} of them took a Hedera prize." if won else "None of them took a Hedera prize."
    blocks = (
        Block("proof", "Hedera proof", "proof",
              f"What a program found for the Hedera IDs of {projects} projects. {winners}",
              _bars(total["proof"], total["proof_won"], filters.PROOF_ORDER,
                    filters.PROOF_WORDS, projects, needs)),
        Block("life", "Still worked on after the event?", "life",
              f"Signs of life in the code or on the ledger, for {projects} projects.",
              _bars(total["life"], total["life_won"], filters.LIFE_ORDER, LIFE_WORDS, projects,
                    needs)),
        Block("services", "What the ledger confirms they built with", "ledger",
              "Projects with at least one ID that the ledger knows as each kind. A project can "
              "count in several rows.",
              _bars(total["services"], total["services_won"], tuple(SERVICE_WORDS),
                    SERVICE_WORDS, projects, needs)),
        Block("themes", "Themes", "category",
              f"Only {with_theme} of the {projects} projects have a theme so far: the ones with a "
              "card written by a model.",
              _bars(total["themes"], total["themes_won"], sorted(total["themes"]), {},
                    with_theme, needs)),
    )  # fmt: skip
    rows = tuple(
        EventRow(names.get((e["site"], e["slug"]), e["slug"]), e["year"], e["projects"],
                 e["prize"].get("hedera_prize", 0), e["prize"].get("other_prize", 0),
                 e["prize"].get("no_prize", 0), e["winner_entries"])
        for e in events
    )  # fmt: skip
    return Overview(data.get("made_on", ""), projects, rows, blocks,
                    data.get("came_back", {}), needs)  # fmt: skip


def newest(folder: Path | None = None) -> dict | None:
    return evidence.newest("overview", folder)
