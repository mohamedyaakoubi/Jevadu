"""The ledger story of a project (design 7.5): what its page names, and what its own Hedera IDs
did on the ledger, service by service.

The rules that the first measure (evals/ledger_story) and the card share: the words that name a
service, the days around an event, the network of each own ID, and the events of a project, each
moment of consensus once. No AI: the words are matched as they are written, and the events come
from the mirror node (check/history.py).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from hackathon_memory.check.history import CONSENSUS, CONTRACTS, FILES, SCHEDULED, TOKENS
from hackathon_memory.check.proof import ORDER

WINDOW_BEFORE = timedelta(days=30)  # design 7.2: the window starts 30 days before the event
LIFE_LINE = timedelta(days=30)  # design 7.4: a sign of life is later than 30 days after the end
AT_LEAST = 3  # the events of a service that make it "done" when the page does not name it
# The words that name a service (evals/ledger_story/guideline.md, "What the page names"). HBAR
# is left out: nearly every project moves HBAR to set itself up.
WORDS = {
    CONSENSUS: ("consensus service", "HCS", "Hedera topic", "HCS topic", "consensus topic",
                "topic ID"),
    TOKENS: ("token service", "HTS", "Hedera token"),
    CONTRACTS: ("smart contract", "Solidity"),
    SCHEDULED: ("scheduled transaction", "schedule service", "HSS"),
    FILES: ("file service", "HFS"),
}  # fmt: skip


def name_patterns(words: dict[str, tuple[str, ...]]) -> dict[str, re.Pattern]:
    """One pattern for each service: any of its words, as whole words, in any case."""
    return {
        service: re.compile("|".join(rf"\b{re.escape(word)}\b" for word in found), re.IGNORECASE)
        for service, found in words.items()
    }


NAMES = name_patterns(WORDS)


@dataclass(frozen=True)
class Event:
    at: datetime
    service: str
    of_an_account: bool  # seen only through an account, whose old history is not the project's


def named_services(words: str, names: dict[str, re.Pattern] = NAMES) -> set[str]:
    """The services that the page's words name."""
    return {service for service, pattern in names.items() if pattern.search(words)}


def on_its_network(rows: Sequence[tuple]) -> list[tuple]:
    """The rows (project, ID, network, status, ...) of each ID on its network only: where its
    status is the best. A page that names no network has its ID asked on both, and the same
    number is another thing on each; the better status of the two counts (design 7.1, 7.2)."""
    best: dict[tuple[int, str], int] = {}
    for row in rows:
        key, rank = (row[0], row[1]), ORDER.index(row[3])
        best[key] = min(best.get(key, rank), rank)
    return [row for row in rows if ORDER.index(row[3]) == best[(row[0], row[1])]]


def merged(events: Sequence[tuple[str, datetime, str, bool]]) -> tuple[Event, ...]:
    """The events of one project, each moment of consensus once. A moment that an account and a
    topic both show belongs to the topic: it is then an event of the project's own things."""
    by_stamp: dict[str, Event] = {}
    for stamp, at, service, of_an_account in events:
        kept = by_stamp.get(stamp)
        if kept is None or (kept.of_an_account and not of_an_account):
            by_stamp[stamp] = Event(at, service, of_an_account)
    return tuple(sorted(by_stamp.values(), key=lambda event: event.at))
