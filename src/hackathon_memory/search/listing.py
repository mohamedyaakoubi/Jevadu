"""A plain listing of the results of a search (design 14.3: "only a plain debug listing").

For each project it shows the facts that the tool holds, read from the tables: the event, the
prize, the result of the proof rule, the links, and for each Hedera id what the mirror node
answered and on which day it was asked (design 7). Nothing here is written by a model
(design rule 2), and nothing gives a score of quality (design rule 1): the place in the list
says only how close a project is to the idea.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import psycopg

from hackathon_memory.search.engine import Hit

PRIZE_WORDS = {
    "hedera_prize": "a Hedera prize",
    "other_prize": "a prize of another sponsor",
    "no_prize": "no prize",
}
STATUS_WORDS = {
    "proof_found": "proof found",
    "window_not_known": "found, the end of the event is not typed in yet",
    "dates_do_not_fit": "found, but the dates do not fit",
    "found_but_empty": "found, but empty",
    "another_kind": "found, but as another kind of thing",
    "cannot_be_checked": "cannot be checked",
    "not_found": "not found",
    "no_id_given": "no Hedera id given on the page or in the README",
    None: "not checked yet",
}


@dataclass(frozen=True)
class LedgerLine:
    """What the mirror node said about one id of the project, on one network."""

    entity_id: str
    found_in: str  # page or readme
    network: str | None  # the network that was asked, or None when it was not asked yet
    status: str | None  # the result of the proof rule there
    kind: str | None
    created_at: datetime | None
    last_activity_at: datetime | None
    asked_at: datetime | None


@dataclass(frozen=True)
class ResultCard:
    rank: int
    hit: Hit
    name: str
    event: str
    prize_state: str
    proof_status: str | None
    page_url: str
    repository: str | None
    ledger: tuple[LedgerLine, ...]


def cards(conninfo: str, hits: Sequence[Hit]) -> list[ResultCard]:
    """The facts of each project that was found, in the order of the hits."""
    ids = [hit.project_id for hit in hits]
    with psycopg.connect(conninfo) as conn:
        projects = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT p.id, p.name, e.name, p.prize_state, p.proof_status, p.page_url, r.url "
                "FROM projects p JOIN events e ON e.id = p.event_id "
                "LEFT JOIN repositories r ON r.id = p.repository_id WHERE p.id = ANY(%s)",
                (ids,),
            ).fetchall()
        }
        ledger: dict[int, list[LedgerLine]] = {}
        for row in conn.execute(
            "SELECT h.project_id, h.entity_id, h.found_in, c.network, c.status, f.kind, "
            "f.created_at, f.last_activity_at, f.asked_at "
            "FROM hedera_ids h LEFT JOIN id_checks c ON c.hedera_id = h.id "
            "LEFT JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network "
            "WHERE h.project_id = ANY(%s) ORDER BY h.project_id, h.id, c.network",
            (ids,),
        ).fetchall():
            ledger.setdefault(row[0], []).append(LedgerLine(*row[1:]))
    return [
        ResultCard(rank, hit, *projects[hit.project_id], tuple(ledger.get(hit.project_id, [])))
        for rank, hit in enumerate(hits, start=1)
        if hit.project_id in projects
    ]


def lines(found: Sequence[ResultCard], *, names: bool = True) -> list[str]:
    """The listing in plain words. With `names` False, no name, link or id of a project is
    shown: only places, states and numbers."""
    out: list[str] = []
    for card in found:
        title = f"{card.name}  ({card.event})" if names else f"project {card.hit.project_id}"
        out.append(f"{card.rank}. {title}")
        out.append(
            f"   prize: {PRIZE_WORDS.get(card.prize_state, card.prize_state)}. "
            f"Hedera proof: {STATUS_WORDS.get(card.proof_status, card.proof_status)}."
        )
        if names:
            out.append(f"   page: {card.page_url}")
            if card.repository:
                out.append(f"   code: {card.repository}")
        checked = [line for line in card.ledger if line.network]
        if names:
            out.extend(f"   {_ledger_words(line)}" for line in checked)
        elif checked:
            out.append(
                f"   ids asked of the mirror node: {len(checked)}, with "
                f"{sum(1 for line in checked if line.asked_at)} answer(s) kept"
            )
        hit = card.hit
        places = [f"meaning #{hit.meaning_rank}" if hit.meaning_rank else "",
                  f"words #{hit.words_rank}" if hit.words_rank else ""]  # fmt: skip
        out.append(f"   found by: {', '.join(place for place in places if place)}")
    return out


def _ledger_words(line: LedgerLine) -> str:
    where = "from the README" if line.found_in == "readme" else "from the page"
    facts = [line.kind or "nothing"]
    if line.created_at:
        facts.append(f"created {line.created_at:%Y-%m-%d}")
    if line.last_activity_at:
        facts.append(f"last activity {line.last_activity_at:%Y-%m-%d}")
    asked = f" (asked {line.asked_at:%Y-%m-%d})" if line.asked_at else ""
    return (
        f"{line.entity_id} on {line.network}, {where}: {', '.join(facts)}. "
        f"{STATUS_WORDS.get(line.status, line.status)}{asked}"
    )
