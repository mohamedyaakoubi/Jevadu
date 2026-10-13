"""A summary of the cards of a set, in numbers only (design 13.1).

    python -m evals.cards_report evals/sets/tuning.json
    python -m evals.cards_report evals/sets/tuning.json --version card-form-0

It writes evals/results/<UTC time>-cards-<set>-<version>.json: how many cards were made, the
quotes given and found, the fields kept, not found and dropped, the labels of each field, the
middle and the longest length in words of each text field, the number of steps, the categories
and the cost. No text of a page and no text of a card: the cards stay in the local database.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.read.sets import pages_of
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"


def summary(rows: list[tuple], pages: int) -> dict:
    """The numbers of the cards of a set. `rows` are (fields, quotes given, quotes found,
    fields dropped, cost) for each card."""
    labels: dict[str, Counter[str]] = defaultdict(Counter)
    states: Counter[str] = Counter()
    words: dict[str, list[int]] = defaultdict(list)
    steps: Counter[int] = Counter()
    categories: Counter[str] = Counter()
    for fields, *_ in rows:
        for name, field in fields.items():
            labels[name][field["label"]] += 1
            states[field["state"]] += 1
            value = field["value"]
            if name == "category":
                categories[value or "(dropped)"] += 1
            elif name == "how_it_works":
                steps[len(value)] += 1
            elif value:
                words[name].append(len(value.split()))
    cost = sum(float(row[4] or 0) for row in rows)
    return {
        "pages_of_the_set": pages,
        "cards": len(rows),
        "quotes_given": sum(row[1] for row in rows),
        "quotes_found": sum(row[2] for row in rows),
        "fields": dict(states),
        "labels": {name: dict(counts) for name, counts in sorted(labels.items())},
        "words": {
            name: {"middle": statistics.median(lengths), "longest": max(lengths)}
            for name, lengths in sorted(words.items())
        },
        "steps": {str(n): count for n, count in sorted(steps.items())},
        "categories": dict(categories.most_common()),
        "cost_usd": round(cost, 4),
        "cost_usd_a_card": round(cost / len(rows), 4) if rows else None,
    }


def rows_of(conninfo: str, pages: list[str], model: str, version: str) -> list[tuple]:
    with psycopg.connect(conninfo) as conn:
        return conn.execute(
            "SELECT c.fields, c.quotes_given, c.quotes_found, c.fields_dropped, c.cost_usd "
            "FROM cards c JOIN projects p ON p.id = c.project_id "
            "WHERE p.page_url = ANY(%s) AND c.model = %s AND c.instructions_version = %s "
            "ORDER BY p.id",
            (pages, model, version),
        ).fetchall()


def write(result: dict, set_name: str, version: str, folder: Path = RESULTS) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"{stamp}-cards-{set_name}-{version}.json"
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 3) or (len(argv) == 3 and argv[1] != "--version"):
        print("usage: python -m evals.cards_report <set file> [--version <instructions version>]")
        return 2
    version = argv[2] if len(argv) == 3 else INSTRUCTIONS_VERSION
    settings = Settings()
    set_file = Path(argv[0])
    pages = pages_of(set_file)
    model = settings.gemini_rewrite_model
    result = {
        "set": set_file.stem,
        "model": model,
        "thinking_level": settings.gemini_rewrite_thinking_level,
        "instructions_version": version,
        "made_on": datetime.now(UTC).strftime("%Y-%m-%d"),
        "counts_of": "a run of the cards, for writing the instructions; not a test result",
        **summary(rows_of(settings.database_conninfo(), pages, model, version), len(pages)),
    }
    path = write(result, set_file.stem, version)
    print(f"{result['cards']} cards; quotes {result['quotes_found']} of {result['quotes_given']} "
          f"found; ${result['cost_usd']}. Written: {path.as_posix()}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
