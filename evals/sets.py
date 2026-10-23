"""The sets of pages of the tests (design 13.1, 13.2): drawn once, then frozen.

    python -m evals.sets draw    draws the 15 tuning pages and the 60 pages of Test 1, once
    python -m evals.sets draw-test3    draws the 50 pages of Test 3, once

Design 13.2: the instructions of the LLM are written and improved on 15 pages, never on the 60
pages of Test 1, and the 60 are drawn at random from groups that are fixed before the draw. The
groups were measured on DoraHacks pages; the pages of ETHGlobal's showcase have one fixed shape,
so their groups come from what really differs there:

* the length of the text that the model reads: short, medium or long, cut at the thirds of all
  the full cards;
* whether the project gives a Hedera id, on its page or in the README of its code.

That makes six groups. The tuning set takes 15 pages, as evenly as the groups allow; Test 1 takes
10 pages of each group from the others. The seed of the draw is written in each file, so the draw
can be made again and checked.

Test 3 (design 13.4) checks the Hedera IDs of a page and of its README. Its groups are fixed
before its draw, from where the tool found an ID: on the page itself, in the README only, or
nowhere, the last group for the IDs that the tool missed. It takes 15, 20 and 15 pages, with a
seed of its own.

A set file holds, for each page, its address, its group, when it was read and the fingerprint of
the saved page, and no text of the page (design 13.1). A set file is never written over.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hackathon_memory.read.sets import SetError, pages_of

SETS = Path(__file__).parent / "sets"
TUNING = SETS / "tuning.json"
TEST1 = SETS / "test1.json"
SEED = 20261013
TUNING_SIZE = 15
TEST1_PER_GROUP = 10
TEST3 = SETS / "test3.json"
TEST3_SEED = 20261018
TEST3_GROUPS = {"an id on the page": 15, "an id in the README only": 20, "no id found": 15}
TEST3_WHY = ("where the tool found a Hedera id: on the page (15 pages), in the README only (20), "
             "or nowhere (15), fixed before the draw (design 13.4)")  # fmt: skip
__all__ = ["SetError", "pages_of", "draw", "write_set"]


@dataclass(frozen=True)
class Candidate:
    page: str
    length: int  # the number of letters that the model reads
    id_given: bool
    read_at: str
    sha256: str


@dataclass(frozen=True)
class Found:
    """A full card for Test 3: where the tool found a Hedera id, and its saved page."""

    page: str
    on_page: bool
    in_readme: bool
    read_at: str
    sha256: str


def group3(found: Found) -> str:
    if found.on_page:
        return "an id on the page"
    return "an id in the README only" if found.in_readme else "no id found"


def draw_test3(pages: list[Found], seed: int = TEST3_SEED) -> list[dict]:
    """The 50 pages of Test 3: from each group, its share, at random."""
    groups: dict[str, list[Found]] = {}
    for one in sorted(pages, key=lambda f: f.page):
        groups.setdefault(group3(one), []).append(one)
    chance = random.Random(seed)  # noqa: S311 - a draw that must be repeatable, not a secret
    cases = []
    for name, share in TEST3_GROUPS.items():
        pool = groups.get(name, [])[:]
        chance.shuffle(pool)
        if len(pool) < share:
            raise SetError(f"the group {name!r} has {len(pool)} pages, fewer than the draw needs")
        cases += [{"page": f.page, "group": name, "read_at": f.read_at, "sha256": f.sha256}
                  for f in pool[:share]]  # fmt: skip
    return cases


def thirds(lengths: list[int]) -> tuple[int, int]:
    """The two lengths that cut the sorted lengths into three parts of the same size."""
    ordered = sorted(lengths)
    return ordered[len(ordered) // 3], ordered[2 * len(ordered) // 3]


def group_of(candidate: Candidate, cuts: tuple[int, int]) -> str:
    size = (
        "short"
        if candidate.length < cuts[0]
        else ("medium" if candidate.length < cuts[1] else "long")
    )
    return f"{size}, {'an id given' if candidate.id_given else 'no id given'}"


def draw(
    candidates: list[Candidate], seed: int = SEED
) -> tuple[list[dict], list[dict], tuple[int, int]]:
    """The tuning set and the set of Test 1, and the cuts of the lengths."""
    cuts = thirds([c.length for c in candidates])
    groups: dict[str, list[Candidate]] = {}
    for candidate in sorted(candidates, key=lambda c: c.page):
        groups.setdefault(group_of(candidate, cuts), []).append(candidate)
    chance = random.Random(seed)  # noqa: S311 - a draw that must be repeatable, not a secret
    names = sorted(groups)
    shares = [TUNING_SIZE // len(names) + (i < TUNING_SIZE % len(names)) for i in range(len(names))]
    tuning: list[dict] = []
    test1: list[dict] = []
    for name, share in zip(names, shares, strict=True):
        pool = groups[name][:]
        chance.shuffle(pool)
        if len(pool) < share + TEST1_PER_GROUP:
            raise SetError(f"the group {name!r} has {len(pool)} pages, fewer than the draw needs")
        tuning += [_case(c, name) for c in pool[:share]]
        test1 += [_case(c, name) for c in pool[share : share + TEST1_PER_GROUP]]
    return tuning, test1, cuts


def _case(candidate: Candidate, group: str) -> dict:
    return {
        "page": candidate.page,
        "group": group,
        "read_at": candidate.read_at,
        "sha256": candidate.sha256,
    }


def write_set(
    path: Path,
    name: str,
    cases: list[dict],
    cuts: tuple[int, int] | None = None,
    *,
    groups: str | None = None,
    seed: int = SEED,
) -> None:
    """Write a set once. The groups are those of Test 1, by the cuts, unless `groups` says them."""
    if path.exists():
        raise SetError(f"{path.name} exists already, and a set is never drawn again")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "set": name,
        "drawn_on": datetime.now(UTC).strftime("%Y-%m-%d"),
        "seed": seed,
        "groups": groups
        or "the length of the text the model reads (short, medium, long; cut at "
        f"{cuts[0]} and {cuts[1]} letters) and whether a Hedera id is given (design 13.2)",
        "cases": cases,
    }
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")


def candidates_from_the_data() -> list[Candidate]:
    """Every full card of the local database, with what its group needs."""
    import psycopg

    from hackathon_memory.collect.ethglobal import data_paths
    from hackathon_memory.collect.rawstore import RawStore
    from hackathon_memory.db.cards import CardStore
    from hackathon_memory.settings import Settings

    settings = Settings()
    conninfo = settings.database_conninfo()
    raw = RawStore(data_paths(settings).raw_dir)
    with psycopg.connect(conninfo) as conn:
        with_ids = {row[0] for row in conn.execute("SELECT DISTINCT project_id FROM hedera_ids")}
    found = []
    for card in CardStore(conninfo).inputs():
        saved = raw.load(card.page)
        if saved is None:
            continue
        meta = saved.meta
        found.append(Candidate(card.page, len(card.text), card.project_id in with_ids,
                               meta["fetched_at"], meta["sha256"]))  # fmt: skip
    return found


def found_from_the_data() -> list[Found]:
    """Every full card of the local database, with where the tool found a Hedera id."""
    import psycopg

    from hackathon_memory.collect.ethglobal import data_paths
    from hackathon_memory.collect.rawstore import RawStore
    from hackathon_memory.db.cards import CardStore
    from hackathon_memory.settings import Settings

    settings = Settings()
    conninfo = settings.database_conninfo()
    raw = RawStore(data_paths(settings).raw_dir)
    with psycopg.connect(conninfo) as conn:
        where = {pid: (on_page, in_readme) for pid, on_page, in_readme in conn.execute(
            "SELECT project_id, bool_or(found_in = 'page'), bool_or(found_in = 'readme') "
            "FROM hedera_ids GROUP BY project_id")}  # fmt: skip
    found = []
    for card in CardStore(conninfo).inputs():
        saved = raw.load(card.page)
        if saved is None:
            continue
        on_page, in_readme = where.get(card.project_id, (False, False))
        found.append(Found(card.page, on_page, in_readme, saved.meta["fetched_at"],
                           saved.meta["sha256"]))  # fmt: skip
    return found


def main(argv: list[str]) -> int:
    if argv == ["draw-test3"]:
        cases = draw_test3(found_from_the_data())
        write_set(TEST3, "test3", cases, groups=TEST3_WHY, seed=TEST3_SEED)
        print(f"Drawn: {len(cases)} pages of Test 3.")
        return 0
    if argv != ["draw"]:
        print("usage: python -m evals.sets draw | draw-test3")
        return 2
    tuning, test1, cuts = draw(candidates_from_the_data())
    write_set(TUNING, "tuning", tuning, cuts)
    write_set(TEST1, "test1", test1, cuts)
    print(f"Drawn: {len(tuning)} tuning pages, {len(test1)} pages of Test 1, cuts at {cuts}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
