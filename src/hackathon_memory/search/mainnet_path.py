"""The path of one project on Hedera's main network (design 7.6, the window of screens S10 and S2):
what its own IDs did there, in order, in the words of the ledger and of its code; the other
networks that its messages name; and what the accounts that made its IDs also made there. Read
from the tables when the window opens, as the step `mainnet_what` left them; no request.

It holds only what no other place of the site says: the card counts the transactions of each
Hedera service around the event and who took part (design 7.5), and the view "Mainnet" counts the
fees and the HBAR of a list (S10). Nothing ranks or scores a project (design rule 1).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime

import psycopg

from hackathon_memory.check.mainnet_what import DEPLOYED
from hackathon_memory.check.story import WINDOW_BEFORE
from hackathon_memory.db.mainnet import mainnet_ids
from hackathon_memory.parse.hedera_ids import (
    ACCOUNT,
    CONTRACT,
    SCHEDULE,
    TOKEN,
    TOPIC,
    TRANSACTION,
)

FIRST = {SCHEDULE: 0, CONTRACT: 1, TOPIC: 2, TOKEN: 3, ACCOUNT: 4}  # who holds a shared moment
# The transactions that made an own ID: its line of the path says so once, with the ID's facts.
MADE_BY_KIND = {"CRYPTOCREATEACCOUNT", "CONSENSUSCREATETOPIC", "TOKENCREATION", "SCHEDULECREATE",
                "CONTRACTCREATEINSTANCE"}  # fmt: skip
MAX_LISTED = 8  # the things of one account that are named; the others are counted


@dataclass(frozen=True)
class Own:
    """An own ID of the project on the main network."""

    named: str  # as the project names it
    ledger_id: str  # as the ledger names it
    kind: str
    made_at: datetime | None
    made_by: str | None
    name: str | None  # a token's name, or a memo
    fields: tuple[str, ...]  # a topic: the keys of its JSON messages
    names_from: str | None  # a contract: where the names of its functions come from
    scheduled: str | None  # a schedule: what it holds
    executed_at: datetime | None  # a schedule: when it ran


@dataclass(frozen=True)
class Step:
    """The transactions of one own ID that did one thing, from the first to the last."""

    ledger_id: str
    kind: str  # the kind of the own ID
    what: str | None  # in the ledger's or the code's words; None when the name says it
    name: str | None  # the kind of transaction, as the mirror node names it
    first: datetime
    last: datetime
    count: int
    failed: int
    by_maker: bool  # every one was sent by the account that made the ID


@dataclass(frozen=True)
class Line:
    """One line of the path: an own ID made, or what its transactions did."""

    first: datetime
    last: datetime
    own: Own
    step: Step | None  # None for an ID whose making is not among its transactions
    made: bool  # the line of the making of the ID


@dataclass(frozen=True)
class Made:
    """What one account that made an own ID also made on the main network, in the time."""

    account: str
    of: tuple[tuple[str, str], ...]  # the own IDs that it made: (kind, ledger ID)
    followed: str | None  # "read", "service", or None when not read yet
    things: tuple[tuple[str, str, datetime | None, str | None, int | None, int | None,
                        str | None], ...]  # fmt: skip
    # (ledger ID, kind, made at, name, held by others, messages, scheduled), at most MAX_LISTED
    counts: tuple[tuple[str, int], ...]  # each kind with how many it made
    first: datetime | None
    last: datetime | None
    more: int = 0  # the things not named
    more_kind: str | None = None  # their kind, when they are all of one kind


@dataclass(frozen=True)
class Path:
    project_id: int
    name: str
    event: str
    starts_at: datetime | None
    ends_on: date | None
    own: tuple[Own, ...]
    steps: tuple[Step, ...]
    networks: tuple[tuple[str, int], ...]  # a network that its messages name, in how many
    messages: int  # its messages, among its transactions
    made: tuple[Made, ...]
    last: datetime | None  # its last transaction
    read_on: datetime | None  # when its transactions were last explained

    def when(self, moment: datetime) -> str:
        """A moment against the event: "before" its first day, "during" it, "after" its last
        day (by the day in UTC, as the view counts, search/mainnet.py), or "unknown"."""
        if self.ends_on is not None and moment.astimezone(UTC).date() > self.ends_on:
            return "after"
        if self.starts_at is not None and moment < self.starts_at:
            return "before"
        return "unknown" if self.starts_at is None or self.ends_on is None else "during"

    def lines(self) -> list[Line]:
        """The path in order: each own ID's making once, with its facts, then the steps."""
        own = {one.ledger_id: one for one in self.own}
        found, made = [], set()
        for step in self.steps:
            one = own[step.ledger_id]
            # an ID that is a transaction is made by itself: its one line is its making
            making = step.what == DEPLOYED or step.name in MADE_BY_KIND or one.kind == TRANSACTION
            if making and step.ledger_id not in made and step.count == 1:
                made.add(step.ledger_id)
            else:
                making = False
            found.append(Line(step.first, step.last, one, step, making))
        for one in self.own:
            if one.ledger_id not in made and one.made_at is not None:
                found.append(Line(one.made_at, one.made_at, one, None, True))
        return sorted(found, key=lambda line: (line.first, not line.made, line.last))

    def days_after(self, moment: datetime) -> int | None:
        """How many days after the last day of the event a moment is."""
        if self.ends_on is None or self.when(moment) != "after":
            return None
        return (moment.astimezone(UTC).date() - self.ends_on).days


_ABOUT = """SELECT p.name, e.name, e.starts_at, e.ends_on FROM projects p
JOIN events e ON e.id = p.event_id WHERE p.id = %s"""
_OWN = """SELECT f.entity_id, coalesce(f.ledger_id, f.entity_id), f.kind, f.created_at,
coalesce(t.made_by, f.made_by), t.name, coalesce(t.fields, '{}'), t.names_from, t.scheduled,
t.executed_at
FROM ledger_facts f LEFT JOIN mainnet_things t ON t.entity_id = coalesce(f.ledger_id, f.entity_id)
WHERE f.network = 'mainnet' AND f.found AND f.entity_id = ANY(%s)"""
_MOMENTS = """SELECT v.entity_id, m.stamp, m.at, m.what, m.name, m.ok, v.payer, m.networks,
m.explained_at FROM ledger_events v JOIN mainnet_transactions m ON m.stamp = v.stamp
WHERE v.network = 'mainnet' AND v.entity_id = ANY(%s) ORDER BY m.at, m.stamp"""
_MADE = """SELECT entity_id, kind, made_at, made_by, name, held_by_others, messages, scheduled
FROM mainnet_things WHERE made_by = ANY(%s) AND NOT entity_id = ANY(%s)
AND kind <> 'account' AND (%s::timestamptz IS NULL OR made_at >= %s::timestamptz)
ORDER BY made_at, entity_id"""


def path_of(conninfo: str, project_id: int) -> Path | None:
    """The path of a project on the main network; None when it has no own ID there."""
    with psycopg.connect(conninfo) as conn:
        about = conn.execute(_ABOUT, (project_id,)).fetchone()
        named = sorted(mainnet_ids(conn, [project_id]).get(project_id, ()))
        if about is None or not named:
            return None
        rows = conn.execute(_OWN, (named,)).fetchall()
        own = tuple(Own(*row[:6], tuple(row[6]), *row[7:]) for row in rows)
        moments = conn.execute(_MOMENTS, (named,)).fetchall()
        makers = sorted({one.made_by for one in own if one.made_by})
        since = about[2] - WINDOW_BEFORE if about[2] else None
        made_rows = conn.execute(_MADE, (makers, [one.ledger_id for one in own], since,
                                         since)).fetchall()  # fmt: skip
        followed = dict(conn.execute(
            "SELECT entity_id, followed FROM mainnet_things WHERE entity_id = ANY(%s)", (makers,)
        ).fetchall())  # fmt: skip
    by_named = {one.named: one for one in own}
    steps, networks, messages, last, read_on = _steps(moments, by_named)
    made = tuple(_made(account, own, followed.get(account),
                       [row for row in made_rows if row[3] == account])
                 for account in makers)  # fmt: skip
    return Path(project_id, about[0], about[1], about[2], about[3],
                tuple(sorted(own, key=lambda one: (one.made_at is None, one.made_at or 0))),
                steps, networks, messages, made, last, read_on)  # fmt: skip


def _steps(moments: list[tuple], own: dict[str, Own]) -> tuple:
    """The steps of the own IDs' transactions: each moment once, given to one own ID (a schedule
    first, then a contract, a topic, a token, an account), then grouped by what it did."""
    holder: dict[str, tuple] = {}
    for row in moments:
        one = own.get(row[0])
        if one is None:
            continue
        kept = holder.get(row[1])
        if kept is None or FIRST.get(one.kind, 9) < FIRST.get(own[kept[0]].kind, 9):
            holder[row[1]] = row
    groups: dict[tuple[str, str | None, str | None], list[tuple]] = {}
    networks: Counter[str] = Counter()
    messages = 0
    for row in sorted(holder.values(), key=lambda row: (row[2], row[1])):
        groups.setdefault((row[0], row[3], None if row[3] else row[4]), []).append(row)
        networks.update(row[7] or ())
        messages += row[4] == "CONSENSUSSUBMITMESSAGE"
    steps = []
    for (named, what, name), rows in groups.items():
        one = own[named]
        by_maker = bool(one.made_by) and all(row[6] == one.made_by for row in rows)
        steps.append(Step(one.ledger_id, one.kind, what, name or rows[0][4], rows[0][2],
                          rows[-1][2], len(rows), sum(row[5] is False for row in rows),
                          by_maker))  # fmt: skip
    steps.sort(key=lambda step: (step.first, step.last))
    moments_at = [row[2] for row in holder.values()]
    explained = [row[8] for row in holder.values() if row[8] is not None]
    return (
        tuple(steps),
        tuple(networks.most_common()),
        messages,
        max(moments_at) if moments_at else None,
        max(explained) if explained else None,
    )


def _made(account: str, own: tuple[Own, ...], followed: str | None, rows: list[tuple]) -> Made:
    """What one account made: its things named, at most MAX_LISTED, and the others counted;
    contracts are only counted when there are more than MAX_LISTED, as a factory makes them."""
    counts = Counter(row[1] for row in rows)
    listed = [row for row in rows if not (row[1] == CONTRACT and counts[CONTRACT] > MAX_LISTED)]
    things = tuple((row[0], row[1], row[2], row[4], row[5], row[6], row[7])
                   for row in listed[:MAX_LISTED])  # fmt: skip
    rest = Counter(row[1] for row in rows) - Counter(one[1] for one in things)
    dates = [row[2] for row in rows if row[2]]
    return Made(account, tuple((one.kind, one.ledger_id) for one in own if one.made_by == account),
                followed, things, tuple(sorted(counts.items())), min(dates) if dates else None,
                max(dates) if dates else None, rest.total(),
                next(iter(rest)) if len(rest) == 1 else None)  # fmt: skip
