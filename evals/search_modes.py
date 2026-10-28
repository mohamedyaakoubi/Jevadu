"""The modes of the search, on the cases of Test 2: how many known projects each finds, how fast,
and at what cost.

    python -m evals.search_modes
    python -m evals.search_modes --typos     the same cases, with two typing errors in each idea

Each mode gives the 10 projects it finds first for an idea; the project that gives the idea is
left out, as in Test 2. The modes:

* words: BM25 over the name, the short line and the texts of each page (search/engine.py).
* meaning: the embedding of the idea against the embedding of each page.
* both: the two lists merged by their ranks, as the search of the website does.
* meaning, then AI: the 30 closest by meaning; the search model reads them and orders the 10
  that are closest to the idea.
* both, then AI: the 30 first of the merged lists, ordered by the search model.
* AI over every project: the search model reads the name and the short line of every project and
  picks the 10 closest to the idea. No embedding and no BM25.

The model only says which projects are closest to the idea, closest first. It never scores a
project or judges its quality (design rule 1). The cases, the known projects and the count are
those of Test 2 (evals/test2/run.py and guideline.md); only the counted cases are used.

It writes evals/results/<UTC time>-search-modes[-typos].json, in numbers only: for each mode the
known projects found in the first 10 with a range by case, the time of a search (middle and 95 of
100), and the cost of a search from the ledger of the costs. No idea and no text of a page is
written. The embedding of each idea is made before the clock starts, and kept for a day.
"""

from __future__ import annotations

import json
import random
import re
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from pydantic import ValidationError

from evals.test2.cases import PAIRS
from evals.test2.ideas import FILE as IDEAS_FILE
from evals.test2.ideas import read as read_ideas
from evals.test2.run import FIRST, Case, cases_of, projects_of, share
from hackathon_memory.db.embeddings import EmbeddingStore
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.finops.calls import PostgresStore
from hackathon_memory.finops.meter import metered_client
from hackathon_memory.pipeline.embed import FAILED_CALLS
from hackathon_memory.search import engine
from hackathon_memory.search.rerank import by_ai, texts_of
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
POOL = 30  # the candidates that an AI mode orders
TEXT_LETTERS = 300  # of the first text of a page, for a candidate that the AI orders
CATALOG_LETTERS = 120  # of the short line, or of the first text, for "AI over every project"
TYPO_SEED = 20261016
TYPOS = 2  # typing errors in each idea, with --typos
MODES = ("words", "meaning", "both", "meaning, then AI", "both, then AI", "AI over every project")


def with_typos(idea: str, seed: int, count: int = TYPOS) -> str:
    """The idea with `count` typing errors, each in a word of five letters or more: two letters
    swapped, or one letter left out. The same seed gives the same errors."""
    rng = random.Random(seed)  # noqa: S311  (typing errors to test with, not a secret)
    words = re.split(r"(\s+)", idea)
    places = [i for i, word in enumerate(words) if word.isalpha() and len(word) >= 5]
    for i in rng.sample(places, min(count, len(places))):
        word = words[i]
        at = rng.randrange(1, len(word) - 2)
        swapped = word[:at] + word[at + 1] + word[at] + word[at + 2 :]
        # Two equal letters swapped change nothing: then one letter is left out instead.
        words[i] = swapped if rng.random() < 0.5 and swapped != word else word[:at] + word[at + 1 :]
    return "".join(words)


def measure(settings: Settings, cases: Sequence[Case], projects: dict, page_of: dict[int, str],
            *, typos: bool, run_id: str) -> list[dict]:  # fmt: skip
    """One row for each counted case and mode: the known projects found in the first 10, the
    seconds, and whether an AI call failed (then the mode keeps the order it had before)."""
    conninfo = settings.database_conninfo()
    embedding_model = settings.gemini_embedding_model
    model, level = settings.gemini_search_model, settings.gemini_search_thinking_level
    client = metered_client(settings, "search_modes", run_id=run_id)
    store = EmbeddingStore(conninfo)
    texts = texts_of(conninfo)
    rows = []
    counted = [case for case in cases if case.counted]
    for number, case in enumerate(counted, start=1):
        idea = with_typos(case.idea, TYPO_SEED + number) if typos else case.idea
        own = projects[case.asked_by].id if case.asked_by else None
        engine.by_meaning(store, client.tagged(purpose="embed_query"), idea,
                          model=embedding_model, limit=1)  # fmt: skip

        def meaning(limit: int, _idea: str = idea) -> list[int]:
            return engine.by_meaning(store, client, _idea, model=embedding_model, limit=limit)

        def words(limit: int, _idea: str = idea) -> list[int]:
            return engine.by_words(conninfo, _idea, limit=limit)

        def both(window: int) -> list[int]:
            return [hit.project_id for hit in engine.merge(meaning(window), words(window))]

        def reordered(
            pool: list[int], mode: str, _idea: str = idea, _n: int = number, _own: Any = own
        ) -> list[int]:
            pool = [pid for pid in pool if pid != _own][:POOL]
            ordered = by_ai(client.tagged(item_ref=f"{_n}:{mode}"), model, level, _idea, pool,
                            texts, letters=TEXT_LETTERS, with_text=True)  # fmt: skip
            return ordered + [pid for pid in pool if pid not in ordered]

        def catalog(_idea: str = idea, _n: int = number, _own: Any = own) -> list[int]:
            pool = [pid for pid in texts if pid != _own]
            mode = "AI over every project"
            return by_ai(client.tagged(item_ref=f"{_n}:{mode}"), model, level, _idea, pool,
                         texts, letters=CATALOG_LETTERS, with_text=False)  # fmt: skip

        plans: dict[str, Callable[[], list[int]]] = {
            "words": lambda: words(FIRST + 1),
            "meaning": lambda: meaning(FIRST + 1),
            "both": lambda: both(FIRST + 1),
            "meaning, then AI": lambda: reordered(meaning(POOL + 1), "meaning, then AI"),
            "both, then AI": lambda: reordered(both(POOL + 1), "both, then AI"),
            "AI over every project": catalog,
        }
        for mode, plan in plans.items():
            begin = time.perf_counter()
            failed = False
            try:
                ranked = plan()
            except (*FAILED_CALLS, BudgetExceeded, ValidationError):
                failed = True
                ranked = {"meaning, then AI": lambda: meaning(POOL + 1),
                          "both, then AI": lambda: both(POOL + 1)}.get(mode, list)()  # fmt: skip
            seconds = time.perf_counter() - begin
            shown = [page_of[pid] for pid in ranked if pid != own][:FIRST]
            rows.append({
                "case": number, "group": case.group, "mode": mode,
                "found": sum(page in shown for page in case.known), "known": len(case.known),
                "seconds": round(seconds, 2), "failed": failed,
            })  # fmt: skip
        print(f"case {number} of {len(counted)}: " + ", ".join(
            f"{r['mode']} {r['found']}/{r['known']} {r['seconds']}s"
            for r in rows if r["case"] == number))  # fmt: skip
    return rows


def summary(rows: Sequence[dict], costs: dict[str, list[float]],
            modes: Sequence[str] = MODES) -> dict:  # fmt: skip
    """The numbers of each mode of `modes`: the share found with its range by group of cases, the
    time of a search, and its cost."""
    numbers = {}
    for mode in modes:
        mine = [row for row in rows if row["mode"] == mode]
        if not mine:
            continue
        groups: dict[str, tuple[int, int]] = {}
        for row in mine:
            found, known = groups.get(row["group"], (0, 0))
            groups[row["group"]] = (found + row["found"], known + row["known"])
        seconds = sorted(row["seconds"] for row in mine)
        spent = costs.get(mode, [])
        numbers[mode] = {
            **share(groups),
            "searches": len(mine),
            "failed_ai_calls": sum(row["failed"] for row in mine),
            "seconds_middle": round(statistics.median(seconds), 2),
            "seconds_95_of_100": seconds[min(len(seconds) - 1, int(len(seconds) * 0.95))],
            "cost_usd_per_search": round(sum(spent) / len(mine), 6) if spent else 0.0,
        }
    return numbers


def write(result: dict, typos: bool, folder: Path | None = None) -> Path:
    folder = folder or RESULTS
    folder.mkdir(parents=True, exist_ok=True)
    name = "search-modes-typos" if typos else "search-modes"
    path = folder / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{name}.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return path


def main(argv: Sequence[str]) -> int:
    typos = argv == ["--typos"]
    if argv and not typos:
        print("usage: python -m evals.search_modes [--typos]")
        return 2
    settings = Settings()
    conninfo = settings.database_conninfo()
    ideas = read_ideas(Path(settings.data_dir) / "evals" / "test2" / IDEAS_FILE)
    pages = {page for pair in PAIRS for page in (pair.first, pair.second)}
    pages |= {idea.page for idea in ideas}
    projects = projects_of(conninfo, sorted(pages))
    cases = cases_of(projects, ideas)
    with psycopg.connect(conninfo) as conn:
        page_of = dict(conn.execute("SELECT id, page_url FROM projects").fetchall())
    run_id = f"search-modes-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    started = datetime.now(UTC)
    rows = measure(settings, cases, projects, page_of, typos=typos, run_id=run_id)
    ledger = [c for c in PostgresStore(conninfo).calls(since=started)
              if c.run_id == run_id and c.purpose == "search_modes"]  # fmt: skip
    costs: dict[str, list[float]] = {}
    for call in ledger:  # each AI call is tagged "<case>:<mode>"; a retry adds to its own mode
        mode = (call.item_ref or "").partition(":")[2]
        costs.setdefault(mode, []).append(call.cost_usd or 0.0)
    result = {
        "test": "search-modes-typos" if typos else "search-modes",
        "made_on": datetime.now(UTC).strftime("%Y-%m-%d"),
        "cases_of": "test2, the counted cases",
        "embedding_model": settings.gemini_embedding_model,
        "search_model": settings.gemini_search_model,
        "thinking_level": settings.gemini_search_thinking_level,
        "pool_ordered_by_ai": POOL,
        "typing_errors_in_each_idea": TYPOS if typos else 0,
        "typo_seed": TYPO_SEED if typos else None,
        "projects_searched": len(page_of),
        "modes": summary(rows, costs),
        "rows": rows,
    }
    path = write(result, typos)
    for mode, number in result["modes"].items():
        print(f"{mode}: {number['found']} of {number['known']} = {number['share']} "
              f"{number['range']}, {number['seconds_middle']} s, "
              f"{number['cost_usd_per_search']} dollars")  # fmt: skip
    print(f"Written: {path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
