"""The filters of the search (design 8.2): organiser, event, year, category, Hedera proof, main
network, life and prize.

Each project gets its eight facts from the tables: the organiser of its event, its event, the
year of that event, the category of its card when the model wrote one, the result of the proof
rule, whether its team put an own ID on the main network (the tag "Mainnet" of design 7.5, by the
rule of search/listing.py; 31 October 2026), its life by the rule of design 7.4, and its prize.
The organiser of an event of ETHGlobal's showcase is ETHGlobal; of any other event, the organiser
that its list of winners names, which the parser keeps as the sponsor of each entry's prize (30
October 2026). A filter keeps the projects
whose fact matches it, and the search then ranks only those (search/engine.py). With no filter set,
every project is searched.
The prize is the one fact with two values at once: a project known only from a winners' list
also won a Hedera prize, so each of the choices keeps the projects that have it. A prize of
another sponsor and no Hedera prize is a choice of its own (28 October 2026).

The choices that the page offers are the values that the projects really have, each with its
number of projects. A value that a request names but no project has is left out, and the page
says so.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime

import psycopg

from hackathon_memory.check.life import ACTIVE, QUIET, STOPPED, TOO_EARLY, UNKNOWN, life_of
from hackathon_memory.read.quotes import KEPT
from hackathon_memory.search import listing, seen

NOT_CHECKED = "not_checked"  # a project that the proof rule has not seen yet
# The site of ETHGlobal's showcase, and the organiser of every event read there.
ETHGLOBAL_SITE, ETHGLOBAL = "ethglobal.com", "ETHGlobal"
# The kinds of Hedera ID that the charts count.
KINDS = ("account", "topic", "token", "contract", "schedule")
LIFE_ORDER = (ACTIVE, QUIET, STOPPED, TOO_EARLY, UNKNOWN)
# The choices of the prize filter, and their words, which the tags of a card use too.
HEDERA_PRIZE, OTHER_PRIZE, WINNERS_LIST = "hedera_prize", "other_prize", "winners_list"
WINNER_WORDS = {HEDERA_PRIZE: "Won a Hedera prize", OTHER_PRIZE: "Won another sponsor's prize",
                WINNERS_LIST: "Winners' list only"}  # fmt: skip
# The choices of the main network filter: a project with the tag "Mainnet", or one without it.
YES, NO = "yes", "no"
MAINNET_WORDS = {YES: "Yes", NO: "No"}
PROOF_ORDER = (*[status for status in listing.STATUS_WORDS if status], NOT_CHECKED)
PROOF_WORDS = {**{k: v for k, v in listing.STATUS_WORDS.items() if k},
               NOT_CHECKED: listing.STATUS_WORDS[None]}  # fmt: skip


@dataclass(frozen=True)
class Filters:
    """The values chosen on the page; an empty text is "all"."""

    event: str = ""  # the number of an event
    year: str = ""
    category: str = ""
    proof: str = ""
    life: str = ""
    winner: str = ""
    organiser: str = ""
    mainnet: str = ""

    def chosen(self) -> dict[str, str]:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name)}


@dataclass(frozen=True)
class Facts:
    """The facts of one project that the filters look at, and more that the charts count:
    its prize, its kind of entry, the kinds of its Hedera IDs that the ledger confirms, and what
    the reading of its code found (design 7.3): the Hedera services it calls and the Hedera
    packages it names."""

    project_id: int
    event: str
    event_name: str
    year: str
    category: str
    proof: str
    life: str
    prize: str = "no_prize"
    entry_kind: str = "full_card"
    kinds: tuple[str, ...] = ()
    code_read: bool = False  # the code of its repository was read, whole or in part
    code_services: tuple[str, ...] = ()
    code_packages: tuple[str, ...] = ()
    organiser: str = ""  # who ran its event: ETHGlobal, or the organiser of its winners' list
    mainnet: str = NO  # YES when its team put an own ID on the main network (design 7.5)

    @property
    def winner(self) -> tuple[str, ...]:
        """The choices of the prize filter that keep the project."""
        won = (self.prize,) if self.prize in (HEDERA_PRIZE, OTHER_PRIZE) else ()
        return won + ((WINNERS_LIST,) if self.entry_kind == "winner_entry" else ())


@dataclass(frozen=True)
class Choice:
    value: str
    words: str
    count: int


@dataclass(frozen=True)
class Choices:
    """What each filter offers, and how many projects have a category at all."""

    event: list[Choice]
    year: list[Choice]
    category: list[Choice]
    proof: list[Choice]
    life: list[Choice]
    winner: list[Choice]
    projects: int
    with_category: int
    organiser: list[Choice] = field(default_factory=list)
    mainnet: list[Choice] = field(default_factory=list)

    def knows(self, name: str, value: str) -> bool:
        return any(choice.value == value for choice in getattr(self, name))


def facts(conninfo: str, *, model: str, version: str, now: datetime | None = None) -> list[Facts]:
    """The facts of every project. The category is the one kept on the project's card of
    this model and these instructions; a project without such a card has none. The kinds are
    those of its IDs that the ledger found as the kind the project gave (search/seen.py). The
    services and the packages are those that the reading of its code found."""
    now = now or datetime.now(UTC)
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT p.id, e.id, e.name, "
            "coalesce(extract(year FROM e.ends_on), extract(year FROM e.starts_at), e.year)::int, "
            "p.proof_status, c.fields -> 'category', p.prize_state, p.entry_kind, "
            "(SELECT coalesce(array_agg(DISTINCT f.kind ORDER BY f.kind), '{}') "
            " FROM hedera_ids h JOIN id_checks ic ON ic.hedera_id = h.id AND ic.status = ANY(%s) "
            " JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = ic.network "
            " WHERE h.project_id = p.id AND f.kind = ANY(%s)), "
            "coalesce(r.archive_status IN ('read', 'partial'), false), "
            "(SELECT coalesce(array_agg(hc.name ORDER BY hc.name), '{}') FROM hedera_in_code hc "
            " WHERE hc.repository_id = r.id AND hc.kind = 'feature'), "
            "(SELECT coalesce(array_agg(hc.name ORDER BY hc.name), '{}') FROM hedera_in_code hc "
            " WHERE hc.repository_id = r.id AND hc.kind = 'package') "
            "FROM projects p JOIN events e ON e.id = p.event_id "
            "LEFT JOIN repositories r ON r.id = p.repository_id "
            "LEFT JOIN cards c ON c.project_id = p.id AND c.model = %s "
            "AND c.instructions_version = %s ORDER BY p.id",
            (list(seen.CONFIRMED), list(KINDS), model, version),
        ).fetchall()
        signs = listing.signs_of_life(conn, [row[0] for row in rows])
        organisers = dict(conn.execute(
            "SELECT e.id, CASE WHEN e.site = %s THEN %s ELSE ("
            " SELECT pr.sponsor FROM projects p JOIN prizes pr ON pr.project_id = p.id"
            " WHERE p.event_id = e.id AND p.entry_kind = 'winner_entry'"
            " ORDER BY p.id, pr.position LIMIT 1) END FROM events e",
            (ETHGLOBAL_SITE, ETHGLOBAL),
        ).fetchall())  # fmt: skip
        on_main = listing.on_mainnet(conn, [row[0] for row in rows])
    found = []
    for (project_id, event_id, event_name, year, proof, category, prize, entry, kinds, code_read,
         services, packages) in rows:  # fmt: skip
        end, _, _, last_push, last_activity, *_ = signs[project_id]
        life = life_of(event_end=end, last_push=last_push, last_ledger_activity=last_activity,
                       now=now)  # fmt: skip
        kept = category and category.get("state") == KEPT and category.get("value")
        found.append(Facts(project_id, str(event_id), event_name, str(year) if year else "",
                           kept or "", proof or NOT_CHECKED, life.status, prize, entry,
                           tuple(kinds), code_read, tuple(services), tuple(packages),
                           organisers.get(event_id) or "",
                           YES if project_id in on_main else NO))  # fmt: skip
    return found


def allowed(rows: Sequence[Facts], chosen: Filters) -> list[int] | None:
    """The projects that match every chosen filter, or None when no filter is chosen."""
    wanted = chosen.chosen()
    if not wanted:
        return None
    return [row.project_id for row in rows
            if all(_has(getattr(row, k), v) for k, v in wanted.items())]  # fmt: skip


def _has(fact: str | tuple[str, ...], value: str) -> bool:
    return value in fact if isinstance(fact, tuple) else fact == value


def _counted(values: Iterable[str], order: Sequence[str] | None = None) -> list[tuple[str, int]]:
    counts = Counter(value for value in values if value)
    if order is None:
        return sorted(counts.items())
    return [(value, counts[value]) for value in order if counts[value]]


def keep_chosen(offer: Choices, every: Choices, chosen: Filters) -> Choices:
    """`offer`, with each chosen value that it lacks added with no project, so that a filter of
    a search keeps its value on the page even when none of the closest projects has it."""
    lists = {}
    for name, value in chosen.chosen().items():
        options = list(getattr(offer, name))
        if not any(choice.value == value for choice in options):
            known = next((c for c in getattr(every, name) if c.value == value), None)
            if known is not None:
                options.append(Choice(known.value, known.words, 0))
        lists[name] = options
    return replace(offer, **lists)


def choices(rows: Sequence[Facts]) -> Choices:
    """The values of each filter that the projects really have, with their numbers."""
    events: dict[str, tuple[str, str]] = {}
    for row in rows:
        events.setdefault(row.event, (row.event_name, row.year))
    by_event = Counter(row.event for row in rows)
    # The newest events first; the events with no known date after them, by name.
    order = sorted(events, key=lambda e: (-(int(events[e][1]) if events[e][1] else 0),
                                          events[e][0]))  # fmt: skip
    return Choices(
        event=[Choice(e, events[e][0], by_event[e]) for e in order],
        year=[Choice(v, v, n) for v, n in reversed(_counted(row.year for row in rows))],
        category=[Choice(v, v, n) for v, n in _counted(row.category for row in rows)],
        proof=[
            Choice(v, PROOF_WORDS[v], n) for v, n in _counted((r.proof for r in rows), PROOF_ORDER)
        ],
        life=[Choice(v, v, n) for v, n in _counted((row.life for row in rows), LIFE_ORDER)],
        winner=[
            Choice(v, WINNER_WORDS[v], n)
            for v, n in _counted(
                (tag for row in rows for tag in row.winner),
                (HEDERA_PRIZE, OTHER_PRIZE, WINNERS_LIST),
            )
        ],  # fmt: skip
        projects=len(rows),
        with_category=sum(bool(row.category) for row in rows),
        organiser=[Choice(v, v, n) for v, n in _counted(row.organiser for row in rows)],
        mainnet=[
            Choice(v, MAINNET_WORDS[v], n)
            for v, n in _counted((row.mainnet for row in rows), (YES, NO))
        ],
    )
