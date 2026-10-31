"""How long the comparison of design 8.3 takes at each thinking level, and what it costs.

    python -m evals.compare_levels data/evals/test2/ideas.txt
    python -m evals.compare_levels data/evals/test2/ideas.txt --levels LOW HIGH --show

The ideas are the maintainer's ideas of Test 2 (a local file, not in git). For each idea the
search finds the first 10 projects, as the website does, and the comparison is asked once at
each level. The order of the levels turns from one idea to the next, so that a slow minute of
the service does not fall on one level only.

It writes evals/results/<UTC time>-compare-levels.json, in numbers only: for each call the
seconds, the tokens and the cost from the ledger of the costs, how many projects got a
comparison, and the middle length of its sentences in words. With --show the sentences are
printed on the screen for a person to read; they are never written to the file.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.test2.ideas import IdeasError, read
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.finops.calls import PostgresStore
from hackathon_memory.finops.meter import metered_client
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.pipeline.embed import FAILED_CALLS
from hackathon_memory.search import compare as comparing
from hackathon_memory.search import engine, listing
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
FIRST = 10  # the first results that the website compares
LEVELS = ("LOW", "MEDIUM", "HIGH")
NOTHING_CLEAR = "Nothing clear."  # the sentence of the instructions when nothing is shared


def middle(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def summary(calls: Sequence[dict]) -> dict:
    """The numbers of each level, from the rows of its calls."""
    levels: dict[str, dict] = {}
    for level in dict.fromkeys(call["level"] for call in calls):
        rows = [call for call in calls if call["level"] == level]
        done = [row for row in rows if not row["failed"]]
        levels[level] = {
            "calls": len(rows),
            "failed": len(rows) - len(done),
            "seconds_middle": middle([row["seconds"] for row in done]),
            "seconds_longest": max((row["seconds"] for row in done), default=None),
            "thinking_tokens_middle": middle([row["thinking_tokens"] for row in done]),
            "output_tokens_middle": middle([row["output_tokens"] for row in done]),
            "cost_usd": round(sum(row["cost_usd"] for row in rows), 6),
            "projects_answered": sum(row["answered"] for row in done),
            "projects_asked": sum(row["projects"] for row in done),
            "nothing_clear": sum(row["nothing_clear"] for row in done),
        }
    return levels


def _words(texts: Sequence[str]) -> float | None:
    return middle([len(text.split()) for text in texts])


def measure(settings: Settings, ideas: Sequence[Any], levels: Sequence[str], *,
            show: bool = False) -> list[dict]:  # fmt: skip
    """Ask the comparison of each idea once at each level; one row for each call."""
    conninfo = settings.database_conninfo()
    run = f"compare-levels-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    client = metered_client(settings, "compare_levels", run_id=run)
    started = datetime.now(UTC)
    rows = []
    for turn, idea in enumerate(ideas):
        hits = engine.search(conninfo, client.tagged(purpose="embed_query"), idea.words,
                             model=settings.gemini_embedding_model, limit=FIRST)  # fmt: skip
        ids = [card.hit.project_id for card in listing.cards(conninfo, hits)]
        items = comparing.items_for(conninfo, ids, models=settings.card_models(),
                                    version=INSTRUCTIONS_VERSION)  # fmt: skip
        order = list(levels[turn % len(levels) :]) + list(levels[: turn % len(levels)])
        for level in order:
            ref = f"{idea.number}:{level}"
            begin = time.perf_counter()
            try:
                found = comparing.compare(client.tagged(item_ref=ref), idea.words, items,
                                          model=settings.gemini_search_model,
                                          thinking_level=level)  # fmt: skip
                failed = False
            except (comparing.CompareError, BudgetExceeded, *FAILED_CALLS):
                found, failed = {}, True
            seconds = round(time.perf_counter() - begin, 1)
            answers = list(found.values())
            rows.append({
                "idea": idea.number, "level": level, "seconds": seconds, "failed": failed,
                "projects": len(items), "answered": len(answers),
                "same_words_middle": _words([a.same for a in answers]),
                "differs_words_middle": _words([a.differs for a in answers]),
                "texts_named": sum(len(a.fields_used) for a in answers),
                "nothing_clear": sum(a.same.strip() == NOTHING_CLEAR for a in answers),
            })  # fmt: skip
            print(f"idea {idea.number}, {level}: {seconds} s, {len(answers)} of {len(items)}")
            if show:
                for answer in answers:
                    print(f"   same: {answer.same}\n   differs: {answer.differs}")
    ledger = [call for call in PostgresStore(conninfo).calls(since=started) if call.run_id == run]
    for row in rows:
        mine = [c for c in ledger if c.item_ref == f"{row['idea']}:{row['level']}"]
        row |= {
            "attempts": len(mine),
            "input_tokens": sum(c.input_tokens for c in mine),
            "output_tokens": sum(c.output_tokens for c in mine),
            "thinking_tokens": sum(c.thinking_tokens for c in mine),
            "cost_usd": round(sum(c.cost_usd or 0.0 for c in mine), 6),
        }
    return rows


def write(result: dict, folder: Path | None = None) -> Path:
    folder = folder or RESULTS
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-compare-levels.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return path


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.compare_levels",
                                     description=__doc__.splitlines()[0])  # fmt: skip
    parser.add_argument("ideas", type=Path, help="the file of ideas of Test 2")
    parser.add_argument("--levels", nargs="+", choices=LEVELS, default=list(LEVELS))
    parser.add_argument("--show", action="store_true", help="print the sentences, not saved")
    arguments = parser.parse_args(argv)
    settings = Settings()
    try:
        ideas = read(arguments.ideas)
    except IdeasError as error:
        print(f"Stopped: {error}")
        return 1
    calls = measure(settings, ideas, arguments.levels, show=arguments.show)
    result = {
        "test": "compare-levels",
        "made_on": datetime.now(UTC).strftime("%Y-%m-%d"),
        "model": settings.gemini_search_model,
        "instructions_version": comparing.INSTRUCTIONS_VERSION,
        "cards_of": INSTRUCTIONS_VERSION,
        "ideas": len(ideas),
        "first_results": FIRST,
        "levels": summary(calls),
        "calls": calls,
    }
    path = write(result)
    for level, n in result["levels"].items():
        answered = f"{n['projects_answered']} of {n['projects_asked']} answered"
        print(f"{level}: middle {n['seconds_middle']} s, longest {n['seconds_longest']} s, "
              f"{n['cost_usd']} dollars, {answered}")  # fmt: skip
    print(f"Written: {path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
