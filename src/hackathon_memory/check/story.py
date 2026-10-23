"""The ledger story of a project (design 7.5): what its page names, what its code calls, and what
its own Hedera IDs did on the ledger, service by service.

The first measure (evals/ledger_story) and the card share its rules: the words that name a
service, the days around an event, the network of each own ID, and the events of a project, each
moment of consensus once. The card adds its table, the facts that stand out, and the time before
and after. No AI: the words are matched as they are written, the events come from the mirror node
(check/history.py), and the services of the code from its reading (parse/hedera_code.py).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from hackathon_memory.check.history import (
    CONSENSUS,
    CONTRACTS,
    FILES,
    HBAR,
    SCHEDULED,
    SERVICES,
    TOKENS,
)
from hackathon_memory.check.proof import ORDER
from hackathon_memory.parse.hedera_code import (
    CHAIN_ID,
    EVM_NETWORK,
    FEATURE,
    RELAY,
    SIGN,
    SYSTEM_CONTRACTS,
)
from hackathon_memory.parse.hedera_ids import ACCOUNT

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
# What the reading of the code finds (design 7.3), by the service that it shows. The signs of an
# EVM project on Hedera, such as its relay or its chain ID, show smart contracts.
CODE_SERVICES = {
    "Consensus Service (topics)": CONSENSUS,
    "Token Service": TOKENS,
    "Smart contracts": CONTRACTS,
    RELAY: CONTRACTS,
    CHAIN_ID: CONTRACTS,
    EVM_NETWORK: CONTRACTS,
    SYSTEM_CONTRACTS: CONTRACTS,
    "Scheduled transactions": SCHEDULED,
    "File Service": FILES,
    "Accounts and HBAR transfers": HBAR,
}


@dataclass(frozen=True)
class Event:
    at: datetime
    service: str
    of_an_account: bool  # seen only through an account, whose old history is not the project's


def named_services(words: str, names: dict[str, re.Pattern] = NAMES) -> set[str]:
    """The services that the page's words name."""
    return {service for service, pattern in names.items() if pattern.search(words)}


def words_found(text: str, names: dict[str, re.Pattern] = NAMES) -> dict[str, tuple[str, ...]]:
    """For each service that the text names, its words as the text writes them: each word once
    whatever its case, in the order of the text."""
    found: dict[str, tuple[str, ...]] = {}
    for service, pattern in names.items():
        seen: dict[str, str] = {}
        for match in pattern.finditer(text):
            seen.setdefault(match.group(0).casefold(), match.group(0))
        if seen:
            found[service] = tuple(seen.values())
    return found


def places_in(text: str, names: dict[str, re.Pattern] = NAMES) -> list[tuple[int, int, str]]:
    """Every place where the text names a service: (start, end, service), in the order of the
    text. Two places never overlap: where they would, the one that starts first counts."""
    found = sorted(
        (match.start(), match.end(), service)
        for service, pattern in names.items()
        for match in pattern.finditer(text)
    )
    kept: list[tuple[int, int, str]] = []
    for place in found:
        if not kept or place[0] >= kept[-1][1]:
            kept.append(place)
    return kept


def services_in_code(found: Iterable[tuple[str, str]]) -> frozenset[str]:
    """The services that a reading of the code shows, from what it found: (kind, name) pairs."""
    return frozenset(
        CODE_SERVICES[name]
        for kind, name in found
        if kind in (FEATURE, SIGN) and name in CODE_SERVICES
    )


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


@dataclass(frozen=True)
class OwnId:
    """An own ID of a project whose kind fits, on its network (design 7.5)."""

    entity_id: str
    network: str
    kind: str | None
    asked_at: datetime | None  # when its history was read; None while it is not read
    cut: bool = False  # the limit of events cut its history


@dataclass(frozen=True)
class ServiceLine:
    """One row of the table: a service on the page, in the code and on the ledger."""

    service: str
    words: tuple[str, ...]  # the words of the page that name it, as the page writes them
    in_code: bool  # the code calls it; False also when the code was not read
    count: int  # the transactions of the project's IDs in the time of the table
    places: tuple[int, ...] = ()  # for each word, how many places of the page say it

    @property
    def compared(self) -> bool:
        """False for HBAR: the page's words are not looked for."""
        return self.service in WORDS


@dataclass(frozen=True)
class Outside:
    """The transactions of a project's own things before or after the time of the table."""

    count: int
    day: date | None  # the first one before that time, or the last one after it
    by_service: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Story:
    """The ledger story of one project (design 7.5)."""

    ids: tuple[OwnId, ...]
    starts_on: date | None  # the time of the table; None when the days of the event are unknown
    ends_on: date | None
    code_read: bool
    lines: tuple[ServiceLine, ...]
    named_not_seen: tuple[str, ...]  # named by the page, and no transaction in that time
    seen_not_named: tuple[tuple[str, int], ...]  # at least AT_LEAST transactions, not named
    all_named_seen: bool  # the page names a service, and every one it names has a transaction
    before: Outside | None  # None: not counted, because its IDs are accounts only
    after: Outside | None

    @property
    def read(self) -> tuple[OwnId, ...]:
        return tuple(one for one in self.ids if one.asked_at is not None)

    @property
    def not_read(self) -> int:
        return len(self.ids) - len(self.read)

    @property
    def cut(self) -> int:
        return sum(one.cut for one in self.read)

    @property
    def read_on(self) -> tuple[date, date] | None:
        """The first and the last day on which its histories were read."""
        days = sorted(one.asked_at.date() for one in self.read if one.asked_at is not None)
        return (days[0], days[-1]) if days else None


def time_of(starts_at: datetime | None, ends_on: date | None) -> tuple[datetime, datetime] | None:
    """The time of the table: from 30 days before the first day of the event to 30 days after
    its last day (design 7.2, 7.4); None when the days of the event are not known."""
    if starts_at is None or ends_on is None:
        return None
    return starts_at - WINDOW_BEFORE, datetime.combine(ends_on, time.max, tzinfo=UTC) + LIFE_LINE


def _outside(events: Sequence[Event], *, first: bool) -> Outside:
    if not events:
        return Outside(0, None, ())
    by_service = Counter(event.service for event in events)
    moments = [event.at for event in events]
    day = (min(moments) if first else max(moments)).date()
    return Outside(len(events), day, tuple((s, by_service[s]) for s in SERVICES if by_service[s]))


def story_of(
    ids: Sequence[OwnId],
    events: Sequence[Event],
    words: str,
    in_code: frozenset[str] | None,
    *,
    starts_at: datetime | None,
    ends_on: date | None,
) -> Story:
    """The ledger story of one project. `ids` are its own IDs on their network, `events` the
    transactions of those that were read, each moment once (merged), `words` the page's own
    words, and `in_code` the services that its code calls, None when the code was not read.

    The table counts the transactions of every ID in the time around the event. Before and after
    that time, only the project's own things count, not its accounts: an account is often kept
    for years and across projects (evals/ledger_story/guideline.md)."""
    span = time_of(starts_at, ends_on)
    inside = [e for e in events if span is None or span[0] <= e.at <= span[1]]
    counts = Counter(event.service for event in inside)
    named = words_found(words)
    per_word = Counter(words[start:end].casefold() for start, end, _ in places_in(words))
    code = in_code or frozenset()
    lines = tuple(
        ServiceLine(service, named.get(service, ()), service in code, counts[service],
                    tuple(per_word[word.casefold()] for word in named.get(service, ())))
        for service in SERVICES
        if service in named or service in code or counts[service]
    )  # fmt: skip
    named_not_seen = tuple(service for service in WORDS if service in named and not counts[service])
    seen_not_named = tuple(
        (service, counts[service])
        for service in WORDS
        if counts[service] >= AT_LEAST and service not in named
    )
    before = after = None
    if span is not None and any(one.kind != ACCOUNT for one in ids):
        own = [event for event in events if not event.of_an_account]
        before = _outside([e for e in own if e.at < span[0]], first=True)
        after = _outside([e for e in own if e.at > span[1]], first=False)
    return Story(
        tuple(ids),
        span[0].date() if span else None,
        span[1].date() if span else None,
        in_code is not None,
        lines,
        named_not_seen,
        seen_not_named,
        bool(named) and not named_not_seen,
        before,
        after,
    )
