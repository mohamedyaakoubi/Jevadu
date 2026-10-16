"""Counts of facts for a list of projects (design 12.1, S5).

The charts of the website count the projects of the list on the screen, a search or the whole
collection, and the overview job counts each event (evals/overview.py); both count here, in the
same way. Only facts read by programs are counted (design rule 2): the prize and the kind of entry
from the pages, the result of the proof rule, the life of the project, the kinds of Hedera ID
that the ledger confirms, and the category of a card, which is a reading with evidence. Nothing
ranks or predicts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from hackathon_memory.search.filters import Facts

WON = "hedera_prize"


@dataclass
class Tally:
    """The counts of a list of projects: for all of them, and for those with a Hedera prize."""

    projects: int = 0
    winners: int = 0
    winner_entries: int = 0
    with_theme: int = 0
    prize: Counter = field(default_factory=Counter)
    proof: Counter = field(default_factory=Counter)
    proof_won: Counter = field(default_factory=Counter)
    life: Counter = field(default_factory=Counter)
    life_won: Counter = field(default_factory=Counter)
    services: Counter = field(default_factory=Counter)
    services_won: Counter = field(default_factory=Counter)
    themes: Counter = field(default_factory=Counter)
    themes_won: Counter = field(default_factory=Counter)
    events: Counter = field(default_factory=Counter)  # projects of each event, by its number
    events_won: Counter = field(default_factory=Counter)


def tally(rows: Iterable[Facts]) -> Tally:
    """Count the facts of the projects given."""
    found = Tally()
    for row in rows:
        won = row.prize == WON
        found.projects += 1
        found.winners += won
        found.winner_entries += row.entry_kind == "winner_entry"
        found.with_theme += bool(row.category)
        found.prize[row.prize] += 1
        found.events[row.event] += 1
        found.events_won[row.event] += won
        for counts, value in ((found.proof, row.proof), (found.life, row.life),
                              (found.themes, row.category)):  # fmt: skip
            if value:
                counts[value] += 1
        found.services.update(row.kinds)
        if won:
            found.proof_won[row.proof] += 1
            found.life_won[row.life] += 1
            found.services_won.update(row.kinds)
            if row.category:
                found.themes_won[row.category] += 1
    return found
