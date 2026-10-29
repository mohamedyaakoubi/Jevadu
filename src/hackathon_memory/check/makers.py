"""Who made a project's own things (design 7.5, 29 October 2026): the account that paid for the
transaction that created a contract, a topic, a token or a schedule, and when.

Found by the case of OmniShield (ETHOnline 2025): its README gave, among its contracts, the price
oracle of Pyth, made 20 months before its event by an account that made none of its other things.
The card drew Pyth's calls as OmniShield's. Now it says who made each own thing and whether the
project lists that account; a thing made long before the event by an account that made nothing
else of the project may belong to someone else. It judges nothing (design rule 1): it puts the
facts side by side.

The account comes from the history of the thing when it holds the creation (a contract's does), or
from one question to the mirror node: the transactions of the moment of creation.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from hackathon_memory.check.story import WINDOW_BEFORE, time_of
from hackathon_memory.hedera.mirror import MirrorNode
from hackathon_memory.parse.hedera_ids import CONTRACT, SCHEDULE, TOKEN, TOPIC

THINGS = (CONTRACT, TOPIC, TOKEN, SCHEDULE)  # the kinds that are made once, by one transaction
# A time in the database keeps microseconds and the node gives nanoseconds: the transaction of a
# creation is asked for in a few microseconds around it.
NEAR = timedelta(microseconds=2)
SAME_MOMENT = timedelta(milliseconds=1)  # an event of a history at the moment of a creation
_ACCOUNT = re.compile(r"^0\.0\.[0-9]+$")


@dataclass(frozen=True)
class Earlier:
    """An earlier entry of the same code at another event: its name and its days."""

    event: str
    starts_at: datetime
    ends_on: date


@dataclass(frozen=True)
class Made:
    """One own thing of a project: when it was made, and the account that paid for it."""

    entity_id: str  # as the project names it
    kind: str
    at: datetime
    by: str | None  # None when the mirror node gave no account


def payer_of(transaction_id: str) -> str | None:
    """The account that paid for a transaction: the first part of its ID,
    0.0.10941897-1792665693-564781427."""
    account, _, rest = transaction_id.partition("-")
    return account if rest and _ACCOUNT.match(account) else None


def maker_in(events: Iterable[tuple[datetime, str | None]], made_at: datetime) -> str | None:
    """The account that paid for a creation, when a history holds it: its event at that moment."""
    for at, payer in events:
        if payer and abs(at - made_at) <= SAME_MOMENT:
            return payer
    return None


def ask_maker(mirror: MirrorNode, ledger_id: str, made_at: datetime) -> str | None:
    """The account that paid for the transaction that made a thing: the transaction of that
    moment whose entity is the thing; None when the node gives none."""
    for one in mirror.transactions_at(made_at - NEAR, made_at + NEAR):
        if one.get("entity_id") == ledger_id:
            return payer_of(one.get("transaction_id") or "")
    return None


def made_lines(
    made: Sequence[Made],
    named: Collection[str],
    starts_at: datetime | None,
    earlier: Sequence[Earlier] = (),
) -> tuple[str, ...]:
    """Who made its own things, in plain words: for each account, what it made and when, and
    whether the project lists it; then each thing made long before the event by an account that
    made none of its other things and that it does not list. When an earlier entry of the same
    code was at an event in that time, the thing was made then, so the line says so: a team that
    came back made its token at its first event (seen on 29 October 2026)."""
    if not made:
        return ()
    groups: dict[str | None, list[Made]] = {}
    for one in sorted(made, key=lambda one: one.at):
        groups.setdefault(one.by, []).append(one)
    lines = []
    for by in sorted(groups, key=lambda by: (by is None, -len(groups[by]), groups[by][0].at)):
        things = groups[by]
        subject, when = _things(things), _when([one.at.date() for one in things])
        if by is None:
            lines.append(f"{subject}, {when}: who made {_them(things)} is not known.")
        else:
            listed = "lists" if by in named else "does not list"
            lines.append(f"{subject}, {when}: made by {by}, an account that the project {listed}.")
    if starts_at is not None:
        for one in made:
            alone = one.by is not None and len(groups[one.by]) == 1 and one.by not in named
            if alone and one.at < starts_at - WINDOW_BEFORE:
                maker = ("an account that made none of its other IDs" if len(made) > 1
                         else "an account that the project does not list")  # fmt: skip
                said = (f"Its {one.kind} {one.entity_id} was made "
                        f"{_how_long((starts_at - one.at).days)} before the event")  # fmt: skip
                then = [entry.event for entry in earlier if _during(one.at, entry)]
                if then:
                    lines.append(f"{said}, in the time of its earlier entry at {then[0]}, with the "
                                 "same code.")  # fmt: skip
                else:
                    lines.append(f"{said}, by {maker}: it may belong to someone else, such as a "
                                 "public service.")  # fmt: skip
    return tuple(lines)


def _during(at: datetime, entry: Earlier) -> bool:
    span = time_of(entry.starts_at, entry.ends_on)
    return span is not None and span[0] <= at <= span[1]


def _things(things: Sequence[Made]) -> str:
    if len(things) == 1:
        return f"Its {things[0].kind} {things[0].entity_id}"
    counts: dict[str, int] = {}
    for one in things:
        counts[one.kind] = counts.get(one.kind, 0) + 1
    parts = [f"{count} {kind}{'s' if count != 1 else ''}"
             for kind, count in sorted(counts.items(), key=lambda item: -item[1])]  # fmt: skip
    return "Its " + " and ".join(parts)


def _them(things: Sequence[Made]) -> str:
    return "it" if len(things) == 1 else "them"


def _when(days: Sequence[date]) -> str:
    first, last = days[0], days[-1]
    if first == last:
        return f"on {_day(first)}"
    if (first.year, first.month) == (last.year, last.month):
        return f"from {first.day} to {_day(last)}"
    if first.year == last.year:
        return f"from {first.day} {first:%B} to {_day(last)}"
    return f"from {_day(first)} to {_day(last)}"


def _day(day: date) -> str:
    return f"{day.day} {day:%B} {day.year}"


def _how_long(days: int) -> str:
    """A time in plain words: "45 days", "20 months", "2 years and 3 months"."""
    if days < 60:
        return f"{days} days"
    months = round(days / 30.44)
    if months < 24:
        return f"{months} months"
    years, months = divmod(months, 12)
    return f"{years} years" + (f" and {months} month{'s' if months != 1 else ''}" if months else "")
