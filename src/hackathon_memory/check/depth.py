"""The depth of use of a project's own Hedera IDs (design 7.5, 25 October 2026).

The ledger story says which Hedera services a project's own IDs used around its event. The
depth of use says what that use was, as facts that the ledger gives and that a person weighs:

* what its IDs did: the kinds of transaction in plain words, with their numbers, and how many
  failed;
* who took part: the accounts other than the IDs that the project names, and the accounts that
  hold its tokens now. The tool cannot tell a user from an account that a team made for a test;
* on how many days: during the event, and in the 30 days before and after it;
* the signs that stay on paper: a topic with no message, a token held only by accounts that the
  project names, a contract never called after its deployment, own accounts that only moved
  HBAR, a Hedera package in the code with no call to a Hedera service, and IDs that other
  projects name too.

It also gives the strip of days that the card draws (Strip). No score, no rank and no word such
as "meaningful": the code counts, and a person reads (design 3.3). The time is the time of the
ledger story's table (check/story.py).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from hackathon_memory.check.history import HBAR, NETWORK_ACCOUNTS, SERVICES, Act
from hackathon_memory.check.setup import Setup, read_on, setup_words
from hackathon_memory.check.story import OwnId, time_of
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, TOKEN, TOPIC

MOST_KINDS = 6  # the kinds of transaction named; the others are counted together
MESSAGE, DEPLOYED, CALLED = "CONSENSUSSUBMITMESSAGE", "CONTRACTCREATEINSTANCE", "CONTRACTCALL"

# The kinds of transaction in plain words, one and many (design 7.5). A kind that the list does
# not hold is one of the "other transactions".
KIND_WORDS = {
    MESSAGE: ("message to a topic", "messages to a topic"),
    "CONSENSUSCREATETOPIC": ("topic made", "topics made"),
    "CONSENSUSUPDATETOPIC": ("topic changed", "topic changes"),
    "TOKENCREATION": ("token made", "tokens made"),
    "TOKENMINT": ("mint of tokens or NFTs", "mints of tokens or NFTs"),
    "TOKENBURN": ("burn of tokens", "burns of tokens"),
    "TOKENASSOCIATE": ("token association", "token associations"),
    "CRYPTOTRANSFER": ("transfer", "transfers"),
    "CRYPTOCREATEACCOUNT": ("account made", "accounts made"),
    "CRYPTOAPPROVEALLOWANCE": ("allowance given", "allowances given"),
    DEPLOYED: ("contract deployed", "contracts deployed"),
    CALLED: ("contract call", "contract calls"),
    "ETHEREUMTRANSACTION": ("EVM transaction", "EVM transactions"),
    "SCHEDULECREATE": ("schedule made", "schedules made"),
    "SCHEDULESIGN": ("schedule signed", "schedule signatures"),
    "SCHEDULED": ("scheduled transaction run", "scheduled transactions run"),
    "FILECREATE": ("file write", "file writes"),
    "FILEAPPEND": ("file write", "file writes"),
    "FILEUPDATE": ("file write", "file writes"),
}
OTHER = ("other transaction", "other transactions")
# A transaction of a history read before each one kept what it was (db/history.py, DEPTH 0).
UNREAD = ("transaction not read in detail yet", "transactions not read in detail yet")


@dataclass(frozen=True)
class Done:
    """One transaction of an own ID, with what it was."""

    stamp: str  # the moment of consensus, as the mirror node writes it
    at: datetime
    service: str
    entity_id: str
    kind: str  # the kind of the ID: account, topic, token, ...
    network: str
    act: Act


@dataclass(frozen=True)
class Day:
    """The transactions of one service on one day."""

    day: date
    count: int
    first: str  # the moment of the first one, for its link to HashScan
    network: str


@dataclass(frozen=True)
class Strip:
    """The days of the time of the table, as the card draws them (design 7.5)."""

    first: date
    last: date
    event_first: date
    event_last: date
    rows: tuple[tuple[str, tuple[Day, ...]], ...]  # each service with a transaction, its days
    most: int  # the most transactions of one service on one day

    @property
    def days(self) -> int:
        return (self.last - self.first).days + 1


@dataclass(frozen=True)
class Depth:
    """The depth of use of one project's own IDs (design 7.5)."""

    did: tuple[tuple[str, int], ...]  # the kinds in plain words with their numbers, most first
    more_kinds: int  # the kinds of transaction not named in `did`
    failed: int  # the transactions that failed
    others: int | None  # accounts other than the project's own IDs that took part; None: unknown
    held_by_others: int | None  # accounts other than its own that hold its tokens now
    days: int  # the days with a transaction in the time of the table
    days_during: int
    days_before: int
    days_after: int
    on_paper: tuple[str, ...]  # the signs that stay on paper, each a sentence of facts
    read: bool  # every own ID was read with what its transactions were
    strip: Strip | None  # None when the days of the event are not known
    total: int = 0  # the transactions in the time of the table, each moment once
    more_count: int = 0  # the transactions of the kinds not named in `did`
    setup: tuple[str, ...] = ()  # how the own IDs are set up, each a sentence (check/setup.py)
    setup_read_at: datetime | None = None  # the day of the check that it comes from


def merged(done: Sequence[Done]) -> list[Done]:
    """Each moment of consensus once, as the ledger story counts it: a moment that an account and
    a thing of the project both show belongs to the thing."""
    by_stamp: dict[str, Done] = {}
    for one in done:
        kept = by_stamp.get(one.stamp)
        if kept is None or (kept.kind == ACCOUNT and one.kind != ACCOUNT):
            by_stamp[one.stamp] = one
    return sorted(by_stamp.values(), key=lambda one: one.at)


def kinds_in_words(inside: Sequence[Done]) -> tuple[tuple[tuple[str, int], ...], int, int]:
    """What the transactions were, in plain words, the most first; the number of kinds left out;
    and how many failed."""
    failed = sum(one.act.ok is False for one in inside)
    counted: Counter[tuple[str, str]] = Counter(
        KIND_WORDS.get(one.act.name, OTHER) if one.act.name else UNREAD
        for one in inside
        if one.act.ok is not False
    )
    last = (OTHER, UNREAD)  # the kinds that are not named come after the named ones
    ordered = sorted(counted.items(), key=lambda item: (item[0] in last, -item[1], item[0][1]))
    did = tuple((words[0] if count == 1 else words[1], count)
                for words, count in ordered[:MOST_KINDS])  # fmt: skip
    return did, max(0, len(ordered) - MOST_KINDS), failed


def on_paper(
    own: Sequence[OwnId],
    moments: Sequence[Done],
    inside: Sequence[Done],
    holders: Mapping[tuple[str, str], tuple[str, ...] | None],
    named: set[str],
    *,
    in_code: frozenset[str] | None,
    set_up: frozenset[str],
    has_package: bool,
    shared_only: bool,
) -> tuple[str, ...]:
    """The signs that stay on paper, each a sentence of facts, in a fixed order."""
    found: list[str] = []
    by_id: dict[tuple[str, str], list[Done]] = {}
    for one in moments:
        by_id.setdefault((one.entity_id, one.network), []).append(one)
    for one in own:
        if one.asked_at is None:
            continue  # not read: nothing is known
        acts = [done.act.name for done in by_id.get((one.entity_id, one.network), [])]
        if one.kind == TOPIC and MESSAGE not in acts:
            found.append(f"Its topic {one.entity_id} has no message.")
        if one.kind == CONTRACT and acts and set(acts) == {DEPLOYED}:
            found.append(f"Its contract {one.entity_id} was never called after its deployment.")
        accounts = holders.get((one.entity_id, one.network))
        if one.kind == TOKEN and accounts is not None:
            if not accounts:
                found.append(f"No account holds its token {one.entity_id} now.")
            elif set(accounts) <= named:
                found.append(f"Its token {one.entity_id} is held only by accounts that the "
                             "project names.")  # fmt: skip
    if (
        own
        and all(one.kind == ACCOUNT for one in own)
        and inside
        and all(one.service == HBAR for one in inside)
    ):
        found.append("Its own accounts only moved HBAR in the time of the event, such as setting "
                     "themselves up.")  # fmt: skip
    if has_package and in_code is not None and not in_code and not set_up:
        found.append("Its code names a Hedera package, and calls no Hedera service.")
    if shared_only:
        found.append("Every Hedera ID that it names is named by other projects too: it has no ID "
                     "of its own.")  # fmt: skip
    return tuple(found)


def strip_of(
    moments: Sequence[Done], own: Sequence[OwnId], span: tuple[datetime, datetime],
    starts_at: datetime, ends_on: date,
) -> Strip:  # fmt: skip
    """The days of the time of the table, each service on a row of its own."""
    inside = [one for one in moments if span[0] <= one.at <= span[1]]
    rows: list[tuple[str, tuple[Day, ...]]] = []
    most = 0
    for service in SERVICES:
        by_day: dict[date, list[Done]] = {}
        for one in inside:
            if one.service == service:
                by_day.setdefault(one.at.date(), []).append(one)
        if by_day:
            days = tuple(Day(day, len(items), items[0].stamp, items[0].network)
                         for day, items in sorted(by_day.items()))  # fmt: skip
            most = max(most, *(one.count for one in days))
            rows.append((service, days))
    return Strip(span[0].date(), span[1].date(), starts_at.date(), ends_on, tuple(rows), most)


def depth_of(
    own: Sequence[OwnId],
    done: Sequence[Done],
    holders: Mapping[tuple[str, str], tuple[str, ...] | None],
    named: set[str],
    *,
    starts_at: datetime | None,
    ends_on: date | None,
    in_code: frozenset[str] | None,
    set_up: frozenset[str] = frozenset(),
    has_package: bool = False,
    shared_only: bool = False,
    read: bool = True,
    setups: Sequence[Setup] = (),
) -> Depth:
    """The depth of use of one project. `own` are its own IDs on their network (the story's),
    `done` the transactions of those that were read, with what each was, `holders` the accounts
    that hold each own token now, `named` every ID that the project names, `in_code` and
    `set_up` what its code calls and sets up for (check/story.py), `read` whether every own
    ID was read with what its transactions were, and `setups` what the check kept about how each
    own ID is set up."""
    span = time_of(starts_at, ends_on)
    moments = merged(done)
    inside = [one for one in moments if span is None or span[0] <= one.at <= span[1]]
    did, more_kinds, failed = kinds_in_words(inside)
    # the network's own accounts can pay too: the treasury makes the accounts of Hedera's portal
    left_out = named | NETWORK_ACCOUNTS
    others = {account for one in inside for account in (one.act.payer, *one.act.parties)
              if account and account not in left_out}  # fmt: skip
    known_acts = any(one.act.name for one in inside)
    held = [accounts for accounts in holders.values() if accounts is not None]
    days = {one.at.date() for one in inside}
    first = starts_at.date() if starts_at is not None else None
    return Depth(
        did, more_kinds, failed,
        len(others) if known_acts else None,
        len({account for accounts in held for account in accounts} - named) if held else None,
        len(days),
        sum(first is not None and ends_on is not None and first <= day <= ends_on for day in days),
        sum(first is not None and day < first for day in days),
        sum(ends_on is not None and day > ends_on for day in days),
        on_paper(own, moments, inside, holders, named, in_code=in_code, set_up=set_up,
                 has_package=has_package, shared_only=shared_only),
        read,
        strip_of(moments, own, span, starts_at, ends_on)
        if span is not None and starts_at is not None and ends_on is not None else None,
        len(inside),
        len(inside) - failed - sum(count for _, count in did),
        setup_words(setups),
        read_on(setups),
    )  # fmt: skip
