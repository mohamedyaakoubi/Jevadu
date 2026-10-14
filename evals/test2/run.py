"""Test 2, the search (design 13.3): is a known similar project in the first 10 results?

    python -m evals.test2.run

The cases, fixed before the run (guideline.md):

* each pair of the same idea (cases.py), both ways: the short line of one project, with its own
  name taken out, is the idea, and the other project must be in the first 10 results;
* each idea of the maintainer (data/evals/test2/ideas.txt): its project, and the projects of the
  same idea as that project, must be in the first 10 results. An idea that repeats four words in
  a row from its project is counted apart;
* each pair that only looks alike, both ways, for information.

The search is the one of the product (search/engine.py): by meaning and by words, merged. The
project that gives the idea is left out of its own results, so 11 are asked and 10 stay.

It writes evals/results/<UTC time>-test2.json: for each case the addresses, the place of each
known project or none, and a fingerprint of the idea, with no text of a page or of an idea. The
number is the share of known projects found in the first 10, with its range by case: a pair, both
ways, is one case. It is compared with the pass mark of design 13.6.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from evals.test2.cases import LOOK_ALIKE, PAIRS, SAME_IDEA
from evals.test2.ideas import FILE as IDEAS_FILE
from evals.test2.ideas import read as read_ideas
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent.parent / "results"
FIRST = 10
DRAWS = 10_000
SEED = 20261015
LEAST_FOUND = 0.80  # design 13.6, fixed on 9 October 2026
MIN_WORDS = 3
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_LEADING_SIGNS = re.compile(r"^[\s:;,.|\-–—]+")


class RunError(ValueError):
    """The cases cannot be run."""


@dataclass(frozen=True)
class Project:
    id: int
    page: str
    name: str
    short_line: str
    first_text: str


@dataclass(frozen=True)
class Case:
    kind: str  # same idea, look alike, or idea
    source: str
    asked_by: str  # the page whose idea is searched, or "" for an idea of the maintainer
    known: tuple[str, ...]  # the pages that must be in the first 10
    idea: str  # never written to the result file
    counted: bool = True  # False for a look-alike pair, or an idea that copies its project
    group: str = ""  # the cases of one group are drawn together for the range


def first_sentence(text: str) -> str:
    return next((part.strip() for part in _SENTENCE_END.split(text) if part.strip()), "")


def idea_of(project: Project) -> str:
    """The idea that a project gives: its short line, or else the first sentence of its text,
    with its own name taken out, so that the name cannot find it."""

    def without_name(text: str) -> str:
        text = re.sub(re.escape(project.name), " ", text, flags=re.IGNORECASE)
        return " ".join(_LEADING_SIGNS.sub("", " ".join(text.split())).split())

    idea = without_name(project.short_line)
    if len(idea.split()) < MIN_WORDS:
        idea = without_name(first_sentence(project.first_text))
    return idea


def projects_of(conninfo: str, pages: Sequence[str]) -> dict[str, Project]:
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT p.id, p.page_url, p.name, coalesce(p.short_line, ''), "
            "coalesce((SELECT s.body FROM sections s WHERE s.project_id = p.id "
            "ORDER BY s.position LIMIT 1), '') "
            "FROM projects p WHERE p.page_url = ANY(%s)",
            (list(pages),),
        ).fetchall()
    found = {row[1]: Project(*row) for row in rows}
    missing = sorted(set(pages) - set(found))
    if missing:
        raise RunError(f"{len(missing)} page(s) of the cases are not in the database")
    return found


def cases_of(projects: dict[str, Project], ideas: Sequence) -> list[Case]:
    cases: list[Case] = []
    for number, pair in enumerate(PAIRS, start=1):
        for asking, other in ((pair.first, pair.second), (pair.second, pair.first)):
            cases.append(Case(pair.kind, pair.source, asking, (other,),
                              idea_of(projects[asking]), pair.kind == SAME_IDEA,
                              f"pair {number}"))  # fmt: skip
    partners: dict[str, set[str]] = {}
    for pair in PAIRS:
        if pair.kind == SAME_IDEA:
            partners.setdefault(pair.first, set()).add(pair.second)
            partners.setdefault(pair.second, set()).add(pair.first)
    for idea in ideas:
        known = (idea.page, *sorted(partners.get(idea.page, ())))
        cases.append(Case("idea", "the maintainer's words", "", known, idea.words,
                          not idea.copied, f"idea {idea.number}"))  # fmt: skip
    return cases


def places(
    case: Case,
    search: Callable[[str, int], list[int]],
    projects: dict[str, Project],
    page_of: dict[int, str],
) -> list[int | None]:
    """The place of each known project in the first 10 results, or None."""
    own = projects[case.asked_by].id if case.asked_by else None
    shown = [page_of[pid] for pid in search(case.idea, FIRST + 1) if pid != own][:FIRST]
    return [shown.index(page) + 1 if page in shown else None for page in case.known]


def share(groups: dict[str, tuple[int, int]], draws: int = DRAWS, seed: int = SEED) -> dict:
    """The share of known projects found, and its range when whole groups are drawn again."""
    found = sum(f for f, _ in groups.values())
    known = sum(k for _, k in groups.values())
    if not known:
        return {"share": None, "range": None, "found": 0, "known": 0}
    values = list(groups.values())
    chance = random.Random(seed)  # noqa: S311 - a draw that must be repeatable, not a secret
    results = []
    for _ in range(draws):
        picked = [values[chance.randrange(len(values))] for _ in values]
        total = sum(k for _, k in picked)
        if total:
            results.append(sum(f for f, _ in picked) / total)
    results.sort()
    low = results[math.floor(0.025 * len(results))]
    high = results[math.ceil(0.975 * len(results)) - 1]
    return {"share": round(found / known, 4), "range": [round(low, 4), round(high, 4)],
            "found": found, "known": known}  # fmt: skip


def run(
    cases: list[Case],
    search: Callable[[str, int], list[int]],
    projects: dict[str, Project],
    page_of: dict[int, str],
    draws: int = DRAWS,
) -> dict:
    rows = []
    groups: dict[str, dict[str, tuple[int, int]]] = {"all": {}, "pairs": {}, "ideas": {}}
    for case in cases:
        where = places(case, search, projects, page_of)
        found = sum(place is not None for place in where)
        rows.append({
            "kind": case.kind, "source": case.source, "group": case.group,
            "asked_by": case.asked_by or None, "known": list(case.known), "places": where,
            "counted": case.counted,
            "idea_sha256": hashlib.sha256(case.idea.encode("utf-8")).hexdigest(),
        })  # fmt: skip
        if not case.counted:
            continue
        part = "ideas" if case.kind == "idea" else "pairs"
        for name in ("all", part):
            before = groups[name].get(case.group, (0, 0))
            groups[name][case.group] = (before[0] + found, before[1] + len(case.known))
    numbers = {name: share(group, draws) for name, group in groups.items()}
    alike = [row for row in rows if row["kind"] == LOOK_ALIKE]
    apart = [row for row in rows if row["kind"] == "idea" and not row["counted"]]
    return {
        "numbers": numbers,
        "pass_mark": f"at least {LEAST_FOUND:.0%} of the known projects in the first {FIRST}",
        "passes": numbers["all"]["share"] is not None and numbers["all"]["share"] >= LEAST_FOUND,
        "look_alike_shown": {
            "shown": sum(row["places"][0] is not None for row in alike),
            "of": len(alike),
        },
        "ideas_counted_apart": {
            "found": sum(p is not None for row in apart for p in row["places"]),
            "known": sum(len(row["known"]) for row in apart),
        },
        "cases": rows,
    }


def write(result: dict, folder: Path | None = None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = folder or RESULTS
    path = folder / f"{stamp}-test2.json"
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return path


def main(argv: Sequence[str]) -> int:
    from hackathon_memory.finops.meter import metered_client
    from hackathon_memory.search import engine
    from hackathon_memory.search.engine import RRF_K

    if argv:
        print("usage: python -m evals.test2.run")
        return 2
    settings = Settings()
    conninfo = settings.database_conninfo()
    model = settings.gemini_embedding_model
    try:
        ideas = read_ideas(Path(settings.data_dir) / "evals" / "test2" / IDEAS_FILE)
        pages = {page for pair in PAIRS for page in (pair.first, pair.second)}
        pages |= {idea.page for idea in ideas}
        projects = projects_of(conninfo, sorted(pages))
        cases = cases_of(projects, ideas)
    except (RunError, ValueError) as error:
        print(f"Stopped: {error}")
        return 1
    with psycopg.connect(conninfo) as conn:
        page_of = dict(conn.execute("SELECT id, page_url FROM projects").fetchall())
    client = metered_client(settings, "embed_query", run_id="test2")

    def search(idea: str, limit: int) -> list[int]:
        hits = engine.search(conninfo, client, idea, model=model, limit=limit)
        return [hit.project_id for hit in hits]

    result = {
        "test": "test2",
        "made_on": datetime.now(UTC).strftime("%Y-%m-%d"),
        "search": {"embedding_model": model, "merge_constant": RRF_K,
                   "asked": FIRST + 1, "kept": FIRST, "the_asking_project": "left out"},
        "projects_searched": len(page_of),
        **run(cases, search, projects, page_of),
    }  # fmt: skip
    path = write(result)
    for name, number in result["numbers"].items():
        print(f"{name}: {number['found']} of {number['known']} = {number['share']} "
              f"{number['range']}")  # fmt: skip
    print(f"look-alike shown: {result['look_alike_shown']}; passes: {result['passes']}")
    print(f"Written: {path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
