"""The main network in a list of projects (design 7.6, screen S10; 1 November 2026).

How many projects of a list put an own ID on Hedera's main network, and what those IDs did there:
their transactions, the days they were used, the fees that the network charged, the HBAR that
changed hands, and the accounts that paid. Beside them, how many projects of the same list named
a Hedera ID, have a Hedera proof, and used an own ID on the test network. Every number comes from
the tables: the proof rule, the tag "Mainnet" (design 7.5), the histories of the own IDs
(db/history.py) and the details of their transactions (db/mainnet.py). A transaction counts once
for a project, and once in the totals, however many of the IDs took part in it.

Nothing here judges a project: the projects stand in the order of their events, and their numbers
side by side (design rule 1). evals/mainnet.py writes the same numbers into a dated file.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import psycopg

from hackathon_memory.check.mainnet import Rate
from hackathon_memory.check.proof import PROOF_FOUND
from hackathon_memory.db.history import OWN
from hackathon_memory.db.mainnet import mainnet_ids
from hackathon_memory.search.filters import Facts

# What each project's own IDs did on the test network: the projects and their transactions.
_TESTNET = """
SELECT count(DISTINCT h.project_id), count(DISTINCT e.stamp)
FROM hedera_ids h JOIN own USING (entity_id)
JOIN ledger_events e ON e.entity_id = h.entity_id AND e.network = 'testnet'
WHERE h.project_id = ANY(%s)
"""
# Each transaction of each project's own IDs on the main network, with its detail when it was read.
_EVENTS = """
SELECT t.project_id, e.stamp, e.at, e.service, coalesce(m.ok, e.ok), m.stamp IS NOT NULL, m.fee,
       m.moved, m.paid_by, m.cents, m.hbars
FROM unnest(%s::int[], %s::text[]) AS t(project_id, entity_id)
JOIN ledger_events e ON e.entity_id = t.entity_id AND e.network = 'mainnet'
LEFT JOIN mainnet_transactions m ON m.stamp = e.stamp
"""
_ABOUT = """
SELECT p.id, p.name, e.name, e.starts_at, e.ends_on, p.prize_state, p.site, p.site_key, e.site,
       e.slug
FROM projects p JOIN events e ON e.id = p.event_id WHERE p.id = ANY(%s)
"""


@dataclass(frozen=True)
class Transaction:
    """One transaction of a project's own IDs on the main network."""

    stamp: str
    at: datetime
    service: str
    ok: bool | None
    detailed: bool  # the mirror node gave what it cost and moved
    fee: int = 0  # tinybars
    moved: int = 0  # tinybars
    paid_by: tuple[str, ...] = ()
    rate: Rate | None = None


@dataclass(frozen=True)
class Used:
    """What a set of transactions counts to."""

    transactions: int
    failed: int
    first: datetime | None
    last: datetime | None
    days: int  # the days, in UTC, with at least one transaction
    detailed: int  # the transactions whose cost the mirror node gave
    fee: int  # tinybars
    fee_dollars: float  # at the network's rate of each hour
    moved: int  # tinybars
    moved_dollars: float
    without_rate: int  # detailed transactions with no rate of the network: not in the dollars
    payers: tuple[str, ...]  # the accounts that paid


@dataclass(frozen=True)
class OwnId:
    entity_id: str  # as the page, the README or the code names it
    kind: str | None
    ledger_id: str | None  # the ID that the ledger gives it, such as 0.0.123 for an EVM address


@dataclass(frozen=True)
class OnMainnet:
    """A project whose team put an own ID on the main network, and what its IDs did there."""

    project_id: int
    name: str
    event: str
    starts_at: datetime | None
    ends_on: date | None
    prize: str
    page: tuple[str, str]  # its site and its key there, to name it without a text of its page
    event_page: tuple[str, str]  # the site of its event and the event's short name in the address
    ids: tuple[OwnId, ...]
    services: tuple[str, ...]
    used: Used
    after: int | None  # its transactions after the last day of its event; None when not known


@dataclass(frozen=True)
class Summary:
    total: int  # the projects of the list
    named: int  # those that name a Hedera ID, on the page, in the README or in the code
    proven: int  # those with a Hedera proof (design 7.2)
    on_testnet: int  # those whose own IDs made a transaction on the test network
    testnet_transactions: int
    projects: tuple[OnMainnet, ...]  # those with the tag "Mainnet", the oldest event first
    used: Used  # their transactions on the main network, each once

    @property
    def used_after(self) -> int:
        """The projects whose own IDs on the main network were used after their event."""
        return sum(bool(one.after) for one in self.projects)


def used_of(transactions: Sequence[Transaction]) -> Used:
    """What `transactions` count to, each moment once."""
    once = list({one.stamp: one for one in transactions}.values())
    detailed = [one for one in once if one.detailed]
    priced = [one for one in detailed if one.rate is not None]
    return Used(
        transactions=len(once),
        failed=sum(one.ok is False for one in once),
        first=min((one.at for one in once), default=None),
        last=max((one.at for one in once), default=None),
        days=len({one.at.date() for one in once}),
        detailed=len(detailed),
        fee=sum(one.fee for one in detailed),
        fee_dollars=sum(one.rate.dollars(one.fee) for one in priced if one.rate),
        moved=sum(one.moved for one in detailed),
        moved_dollars=sum(one.rate.dollars(one.moved) for one in priced if one.rate),
        without_rate=len(detailed) - len(priced),
        payers=tuple(sorted({account for one in detailed for account in one.paid_by})),
    )


def summary(conninfo: str, rows: Sequence[Facts]) -> Summary:
    """The main network in the list of projects `rows` (search/filters.py)."""
    ids = [row.project_id for row in rows]
    with psycopg.connect(conninfo) as conn:
        owned = mainnet_ids(conn, ids)
        (named,) = conn.execute(
            "SELECT count(DISTINCT project_id) FROM hedera_ids WHERE project_id = ANY(%s)", (ids,)
        ).fetchone()
        on_testnet, testnet_transactions = conn.execute(OWN + _TESTNET, (ids,)).fetchone()  # noqa: S608
        pairs = sorted((project_id, one) for project_id, found in owned.items() for one in found)
        events = conn.execute(_EVENTS, ([p for p, _ in pairs], [e for _, e in pairs])).fetchall()
        about = {row[0]: row[1:] for row in conn.execute(_ABOUT, (sorted(owned),)).fetchall()}
        facts = {row[0]: OwnId(*row) for row in conn.execute(
            "SELECT entity_id, kind, ledger_id FROM ledger_facts WHERE network = 'mainnet' "
            "AND entity_id = ANY(%s)", ([e for _, e in pairs],)).fetchall()}  # fmt: skip
    by_project: dict[int, list[Transaction]] = {project_id: [] for project_id in owned}
    for project_id, stamp, at, service, ok, detailed, fee, moved, paid_by, cents, hbars in events:
        rate = Rate(cents, hbars) if cents and hbars else None
        one = Transaction(stamp, at, service, ok, detailed, fee or 0, moved or 0,
                          tuple(paid_by or ()), rate)  # fmt: skip
        by_project[project_id].append(one)
    projects = []
    for project_id, found in owned.items():
        name, event, starts, ends, prize, site, key, event_site, slug = about[project_id]
        mine = by_project[project_id]
        after = None if ends is None else sum(one.at.date() > ends for one in {
            one.stamp: one for one in mine}.values())  # fmt: skip
        projects.append(OnMainnet(
            project_id, name, event, starts, ends, prize, (site, key), (event_site, slug),
            tuple(facts.get(one, OwnId(one, None, None)) for one in sorted(found)),
            tuple(sorted({one.service for one in mine})), used_of(mine), after,
        ))  # fmt: skip
    projects.sort(key=lambda one: (one.starts_at is None, one.starts_at, one.project_id))
    return Summary(
        total=len(rows),
        named=named,
        proven=sum(row.proof == PROOF_FOUND for row in rows),
        on_testnet=on_testnet,
        testnet_transactions=testnet_transactions,
        projects=tuple(projects),
        used=used_of([one for mine in by_project.values() for one in mine]),
    )


def days_between(first: datetime, last: datetime) -> str:
    """The days from `first` to `last` in few words: "6 July 2025", "19 to 21 February 2026",
    "4 September to 5 October 2026", "26 February 2025 to 23 September 2026"."""
    one, two = first.date(), last.date()
    if one == two:
        return f"{one.day} {one:%B %Y}"
    if (one.year, one.month) == (two.year, two.month):
        return f"{one.day} to {two.day} {two:%B %Y}"
    if one.year == two.year:
        return f"{one.day} {one:%B} to {two.day} {two:%B %Y}"
    return f"{one.day} {one:%B %Y} to {two.day} {two:%B %Y}"


def hbar_words(tinybars: int) -> str:
    """An amount of HBAR for a person: two decimals, or "less than 0.01"."""
    if tinybars == 0:
        return "0"
    value = tinybars / 100_000_000
    return f"{value:,.2f}" if value >= 0.01 else "less than 0.01"


def dollar_words(dollars: float) -> str:
    """An amount of US dollars for a person: two decimals, or "less than $0.01"."""
    if dollars == 0:
        return "$0"
    return f"${dollars:,.2f}" if dollars >= 0.01 else "less than $0.01"
