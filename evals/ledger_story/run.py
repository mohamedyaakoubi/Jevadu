"""The ledger story, first measure (guideline.md): how often the ledger shows what the card hides.

    python -m evals.ledger_story.run

It reads from the tool's tables: the projects with at least one own Hedera ID whose kind fits and
whose history was read (the step "history"), the events of those IDs, the days of each event, the
status of each ID, and the page's own words: its short line and the two texts that the parser
copied, not the card. It gives each project the five signals of the guideline, and writes
evals/results/<UTC time>-ledger-signal.json: numbers only, each share with its range by project,
and the projects by their number in the database, never by a text of their page.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import psycopg

from evals.test1.report import Counts, share
from hackathon_memory.check.history import CONSENSUS, CONTRACTS, FILES, SCHEDULED, TOKENS
from hackathon_memory.check.proof import ORDER, PROOF_FOUND
from hackathon_memory.db.history import KINDS_THAT_FIT
from hackathon_memory.parse.hedera_ids import ACCOUNT
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent.parent / "results"
WINDOW_BEFORE = timedelta(days=30)  # design 7.2: the window starts 30 days before the event
LIFE_LINE = timedelta(days=30)  # design 7.4: a sign of life is later than 30 days after the end
AT_LEAST = 3  # S4: the events of a service that make it "done"
SHARE_TO_BUILD = 0.20  # guideline.md: fixed before the reading
COUNTED = ("S1", "S3", "S4")  # the signals of the decision; S2 and S5 are reported
# The words that name a service (guideline.md, "What the page names"). HBAR is left out.
WORDS = {
    CONSENSUS: ("consensus service", "HCS", "Hedera topic", "HCS topic", "consensus topic",
                "topic ID"),
    TOKENS: ("token service", "HTS", "Hedera token"),
    CONTRACTS: ("smart contract", "Solidity"),
    SCHEDULED: ("scheduled transaction", "schedule service", "HSS"),
    FILES: ("file service", "HFS"),
}  # fmt: skip
# A check of the words, not the rule (the report): the same measure with looser words, to see
# whether the decision hangs on the strict ones.
LOOSE_WORDS = {
    CONSENSUS: (*WORDS[CONSENSUS], "topic"),
    TOKENS: (*WORDS[TOKENS], "token", "tokens", "NFT", "NFTs"),
    CONTRACTS: (*WORDS[CONTRACTS], "contract", "contracts", "EVM"),
    SCHEDULED: (*WORDS[SCHEDULED], "schedule", "scheduled"),
    FILES: (*WORDS[FILES], "file"),
}


def _patterns(words: dict[str, tuple[str, ...]]) -> dict[str, re.Pattern]:
    return {
        service: re.compile("|".join(rf"\b{re.escape(word)}\b" for word in found), re.IGNORECASE)
        for service, found in words.items()
    }


_NAMES = _patterns(WORDS)
_LOOSE_NAMES = _patterns(LOOSE_WORDS)


@dataclass(frozen=True)
class Event:
    at: datetime
    service: str
    of_an_account: bool  # seen only through an account, whose old history is not the project's


@dataclass(frozen=True)
class Project:
    project_id: int
    starts_at: datetime
    ends_on: date
    proof_found: bool  # one of its IDs has the status "proof found"
    words: str  # the page's own words
    events: tuple[Event, ...]


def named_services(words: str, names: dict[str, re.Pattern] = _NAMES) -> set[str]:
    """The services that the page's words name."""
    return {service for service, pattern in names.items() if pattern.search(words)}


def named_not_done(project: Project, names: dict[str, re.Pattern] = _NAMES) -> set[str]:
    """S3, by service: what the page names and none of its IDs shows, at any time."""
    done = {event.service for event in project.events}
    return {service for service in named_services(project.words, names) if service not in done}


def done_not_named(project: Project, names: dict[str, re.Pattern] = _NAMES) -> set[str]:
    """S4, by service: what its IDs show at least AT_LEAST times from the start of the window
    on, and the page does not name."""
    window_start = project.starts_at - WINDOW_BEFORE
    counts = Counter(event.service for event in project.events if event.at >= window_start)
    named = named_services(project.words, names)
    return {service for service in WORDS if counts[service] >= AT_LEAST and service not in named}


def signals(project: Project, names: dict[str, re.Pattern] = _NAMES) -> dict[str, bool]:
    """The five signals of the guideline for one project."""
    window_start = project.starts_at - WINDOW_BEFORE
    life_line = datetime.combine(project.ends_on, time.max, tzinfo=UTC) + LIFE_LINE
    own_things = [event for event in project.events if not event.of_an_account]
    before = [event for event in own_things if event.at < window_start]
    return {
        "S1": project.proof_found and bool(before),
        "S2": bool(own_things) and len(before) > len(own_things) / 2,
        "S3": bool(named_not_done(project, names)),
        "S4": bool(done_not_named(project, names)),
        "S5": any(event.at > life_line for event in own_things),
    }


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


def projects(conninfo: str) -> tuple[list[Project], dict[str, int]]:
    """The projects of the measure, and what was read for them."""
    with psycopg.connect(conninfo) as conn:
        ids = conn.execute(
            "WITH own AS (SELECT entity_id FROM hedera_ids GROUP BY entity_id "
            "             HAVING count(DISTINCT project_id) = 1) "
            "SELECT DISTINCT h.project_id, h.entity_id, c.network, c.status, r.kind, r.cut "
            "FROM hedera_ids h JOIN own USING (entity_id) "
            "JOIN id_checks c ON c.hedera_id = h.id "
            "JOIN ledger_histories r ON r.entity_id = h.entity_id AND r.network = c.network "
            "WHERE c.status = ANY(%s)",
            (list(KINDS_THAT_FIT),),
        ).fetchall()
        events: dict[tuple[str, str], list[tuple[str, datetime, str]]] = {}
        for entity, network, stamp, at, service in conn.execute(
            "SELECT entity_id, network, stamp, at, service FROM ledger_events"
        ):
            events.setdefault((entity, network), []).append((stamp, at, service))
        days = {
            pid: (starts, ends)
            for pid, starts, ends in conn.execute(
                "SELECT p.id, e.starts_at, e.ends_on FROM projects p "
                "JOIN events e ON e.id = p.event_id "
                "WHERE e.starts_at IS NOT NULL AND e.ends_on IS NOT NULL"
            )
        }
        words: dict[int, list[str]] = {}
        for pid, text in conn.execute(
            "SELECT id, short_line FROM projects UNION ALL SELECT project_id, body FROM sections"
        ):
            words.setdefault(pid, []).append(text or "")
    by_project: dict[int, list[tuple]] = {}
    for row in on_its_network(ids):
        by_project.setdefault(row[0], []).append(row)
    found: list[Project] = []
    read = Counter()
    for pid, rows in sorted(by_project.items()):
        if pid not in days:
            read["left_out_no_days"] += 1
            continue
        seen: list[tuple[str, datetime, str, bool]] = []
        for entity, network, kind, cut in {(r[1], r[2], r[4], r[5]) for r in rows}:
            read["ids"] += 1
            read["ids_cut"] += int(cut)
            for stamp, at, service in events.get((entity, network), []):
                seen.append((stamp, at, service, kind == ACCOUNT))
        starts, ends = days[pid]
        found.append(Project(pid, starts, ends, any(r[3] == PROOF_FOUND for r in rows),
                             "\n".join(words.get(pid, [])), merged(seen)))  # fmt: skip
        read["events"] += len(found[-1].events)
    return found, dict(read)


def measure(found: Sequence[Project]) -> dict:
    """Each signal's share, with its range by project, and the decision of the guideline."""
    rows = [signals(project) for project in found]
    numbers = {}
    for name in ("S1", "S2", "S3", "S4", "S5"):
        numbers[name] = share(Counts(tuple(int(row[name]) for row in rows), tuple(1 for _ in rows)))
    any_counted = share(Counts(tuple(int(any(row[n] for n in COUNTED)) for row in rows),
                               tuple(1 for _ in rows)))  # fmt: skip
    loose = [signals(project, _LOOSE_NAMES) for project in found]
    loose_any = share(
        Counts(tuple(int(any(row[n] for n in COUNTED)) for row in loose), tuple(1 for _ in loose))
    )
    named = Counter(s for project in found for s in named_services(project.words))
    done = Counter(s for project in found for s in {event.service for event in project.events})
    return {
        "signals": numbers,
        "any_of_S1_S3_S4": any_counted,
        "share_to_build": SHARE_TO_BUILD,
        "worth_building": any_counted["share"] is not None
        and any_counted["share"] >= SHARE_TO_BUILD,
        "check_loose_words": {
            "any_of_S1_S3_S4": loose_any,
            "S3": sum(row["S3"] for row in loose),
            "S4": sum(row["S4"] for row in loose),
        },
        "projects_naming_each_service": dict(named),
        "projects_with_events_of_each_service": dict(done),
        "S3_by_service": dict(Counter(s for p in found for s in named_not_done(p))),
        "S4_by_service": dict(Counter(s for p in found for s in done_not_named(p))),
        "per_project": [
            {
                "project": project.project_id,
                **row,
                "named": sorted(named_services(project.words)),
                "events": dict(Counter(event.service for event in project.events)),
            }
            for project, row in zip(found, rows, strict=True)
        ],
    }


def main(argv: Sequence[str]) -> int:
    del argv
    found, read = projects(Settings().database_conninfo())
    now = datetime.now(UTC)
    result = {"test": "ledger-signal", "made_on": now.date().isoformat(), "projects": len(found),
              "read": read, **measure(found)}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-ledger-signal.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    shown = "; ".join(f"{name}: {value['count']} of {value['of']} ({value['share']})"
                      for name, value in result["signals"].items())  # fmt: skip
    counted = result["any_of_S1_S3_S4"]
    print(f"Projects: {len(found)}. {shown}. At least one of S1, S3, S4: {counted['count']} of "
          f"{counted['of']} ({counted['share']}, range {counted['range']}). Worth building: "
          f"{result['worth_building']}. Written: {path}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
