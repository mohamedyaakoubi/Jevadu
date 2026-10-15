"""A plain listing of the results of a search (design 14.3: "only a plain debug listing").

For each project it shows the facts that the tool holds, read from the tables: the event, the
prize, the result of the proof rule, the life of the project and the dates of its code, the
links, and for each Hedera id what the mirror node answered and on which day it was asked
(design 7). Nothing here is written by a model
(design rule 2), and nothing gives a score of quality (design rule 1): the place in the list
says only how close a project is to the idea.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg

from hackathon_memory.check.life import Life, life_of
from hackathon_memory.parse.project import FULL_CARD, WINNER_ENTRY
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
    "no_id_given": "no Hedera ID given",
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
    code_status: str | None = None  # found, gone or blocked; None when not asked yet
    made_at: datetime | None = None
    last_push_at: datetime | None = None
    life: Life | None = None
    entry_kind: str = FULL_CARD


# The signs of life of each project (design 7.4): the end of its event, the facts of its code,
# and the last activity of its own ids. An id counts on a network where the proof rule found
# it, and only when no project with other code names it too: a shared service is not a sign.
_SIGNS = """
SELECT p.id, e.ends_on, r.code_status, r.made_at, r.last_push_at,
       (SELECT max(f.last_activity_at)
        FROM hedera_ids h
        JOIN id_checks c ON c.hedera_id = h.id AND c.status IN (
            'proof_found', 'window_not_known', 'dates_do_not_fit', 'found_but_empty')
        JOIN ledger_facts f ON f.entity_id = h.entity_id AND f.network = c.network
        WHERE h.project_id = p.id
          AND NOT EXISTS (
              SELECT 1 FROM hedera_ids o JOIN projects op ON op.id = o.project_id
              WHERE o.entity_id = h.entity_id
                AND coalesce(op.repository_id, -op.id) <> coalesce(p.repository_id, -p.id)))
FROM projects p JOIN events e ON e.id = p.event_id
LEFT JOIN repositories r ON r.id = p.repository_id
WHERE p.id = ANY(%s)
"""


def signs_of_life(conn: psycopg.Connection, ids: Sequence[int]) -> dict[int, tuple]:
    """For each project: the end of its event, the status, start and last push of its code, and
    the last activity of its own ids (design 7.4)."""
    return {row[0]: row[1:] for row in conn.execute(_SIGNS, (list(ids),)).fetchall()}


def cards(conninfo: str, hits: Sequence[Hit], *, now: datetime | None = None) -> list[ResultCard]:
    """The facts of each project that was found, in the order of the hits."""
    now = now or datetime.now(UTC)
    ids = [hit.project_id for hit in hits]
    with psycopg.connect(conninfo) as conn:
        projects = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT p.id, p.name, e.name, p.prize_state, p.proof_status, p.page_url, r.url, "
                "p.entry_kind "
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
        signs = signs_of_life(conn, ids)
    found: list[ResultCard] = []
    for rank, hit in enumerate(hits, start=1):
        if hit.project_id not in projects:
            continue
        end, code_status, made_at, last_push, last_activity = signs[hit.project_id]
        *facts, entry_kind = projects[hit.project_id]
        life = life_of(
            event_end=end, last_push=last_push, last_ledger_activity=last_activity, now=now
        )
        found.append(
            ResultCard(
                rank,
                hit,
                *facts,
                tuple(ledger.get(hit.project_id, [])),
                code_status=code_status,
                made_at=made_at,
                last_push_at=last_push,
                life=life,
                entry_kind=entry_kind,
            )
        )
    return found


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
        if card.entry_kind == WINNER_ENTRY:
            out.append(
                "   a winner entry: only the winners of this event are public, from the "
                "organiser's list"
            )
        if card.life is not None:
            out.append(f"   {_life_words(card, card.life)}")
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


CODE_WORDS = {
    "gone": "the repository is gone or private",
    "blocked": "GitHub blocked the repository",
}


def _life_words(card: ResultCard, life: Life) -> str:
    """The life of a project and the dates of its code, in one line."""
    words = f"life: {life.status} ({life.why}"
    words += f", last sign {life.last_sign:%Y-%m-%d})" if life.last_sign else ")"
    if card.code_status == "found" and card.made_at:
        words += f". Code: made {card.made_at:%Y-%m-%d}"
        if card.last_push_at:
            words += f", last push {card.last_push_at:%Y-%m-%d}"
    elif card.code_status in CODE_WORDS:
        words += f". Code: {CODE_WORDS[card.code_status]}"
    return words + "."
