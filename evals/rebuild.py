"""A database built again from the saved pages, counted against the one in use.

    POSTGRES_DB=<new database> python -m hackathon_memory.db migrate
    POSTGRES_DB=<new database> python -m hackathon_memory.pipeline parse
    POSTGRES_DB=<new database> python -m hackathon_memory.pipeline readmes --no-requests
    POSTGRES_DB=<new database> python -m hackathon_memory.pipeline code --no-requests
    POSTGRES_DB=<new database> python -m hackathon_memory.pipeline hedera_code --no-requests
    POSTGRES_DB=<new database> python -m hackathon_memory.pipeline check
    POSTGRES_DB=<new database> python -m hackathon_memory.pipeline embed
    POSTGRES_DB=<new database> python -m hackathon_memory.pipeline cards --restore <file of cards>
    python -m evals.rebuild <database in use> <new database>

The pages, the READMEs, the facts of the code and what the code says about Hedera come from the
saved files, with no request; the mirror node of Hedera is asked again, since its answers are the
ledger of today; the embeddings are made again by the model; and the cards come back from the
file that `cards --export` wrote, with their quotes checked again, since the model would not
write the same cards twice.

It writes evals/results/<UTC time>-rebuild.json, in numbers only: for each count, the value in
the database in use, in the new one, and whether they are the same.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo

from hackathon_memory.search import seen
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"

# Each count: a name, and a query that gives rows of (part, number).
COUNTS = {
    "events": "SELECT 'all', count(*) FROM events",
    "events_with_both_days": "SELECT 'all', count(*) FROM events "
    "WHERE starts_at IS NOT NULL AND ends_on IS NOT NULL",
    "projects": "SELECT entry_kind, count(*) FROM projects GROUP BY 1",
    "sections": "SELECT 'all', count(*) FROM sections",
    "links": "SELECT 'all', count(*) FROM links",
    "prizes": "SELECT 'all', count(*) FROM prizes",
    "hedera_ids": "SELECT found_in, count(*) FROM hedera_ids GROUP BY 1",
    "repositories": "SELECT 'all', count(*) FROM repositories",
    "archives": "SELECT archive_status, count(*) FROM repositories "
    "WHERE archive_status IS NOT NULL GROUP BY 1",
    "hedera_in_code": "SELECT kind, count(*) FROM hedera_in_code GROUP BY 1",
    "id_checks": "SELECT status, count(*) FROM id_checks GROUP BY 1",
    "ledger_facts": "SELECT kind, count(*) FROM ledger_facts GROUP BY 1",
    "cards": "SELECT instructions_version, count(*) FROM cards GROUP BY 1",
    "card_quotes_given": "SELECT instructions_version, sum(quotes_given) FROM cards GROUP BY 1",
    "card_quotes_found": "SELECT instructions_version, sum(quotes_found) FROM cards GROUP BY 1",
    "card_fields_dropped": "SELECT instructions_version, sum(fields_dropped) FROM cards GROUP BY 1",
    "embeddings": "SELECT model, count(*) FROM project_embeddings GROUP BY 1",
}


def counts(conninfo: str) -> dict[str, dict[str, int]]:
    """Every count of COUNTS in one database, and the projects linked across events."""
    found: dict[str, dict[str, int]] = {}
    with psycopg.connect(conninfo) as conn:
        for name, query in COUNTS.items():
            found[name] = {str(part): int(number or 0) for part, number in conn.execute(query)}
    found["linked_across_events"] = seen.counted(seen.came_back(conninfo))
    return found


def compare(in_use: dict, rebuilt: dict) -> dict:
    """For each count and part: the two values and whether they are the same."""
    table: dict[str, dict] = {}
    for name in in_use.keys() | rebuilt.keys():
        parts = in_use.get(name, {}).keys() | rebuilt.get(name, {}).keys()
        table[name] = {part: {"in_use": in_use.get(name, {}).get(part, 0),
                              "rebuilt": rebuilt.get(name, {}).get(part, 0)}
                       for part in sorted(parts)}  # fmt: skip
        for values in table[name].values():
            values["same"] = values["in_use"] == values["rebuilt"]
    return dict(sorted(table.items()))


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m evals.rebuild <database in use> <new database>")
        return 2
    base = Settings().database_conninfo()
    in_use, rebuilt = (counts(make_conninfo(base, dbname=name)) for name in argv)
    table = compare(in_use, rebuilt)
    differing = [f"{name}/{part}" for name, parts in table.items()
                 for part, values in parts.items() if not values["same"]]  # fmt: skip
    now = datetime.now(UTC)
    result = {"test": "rebuild", "made_on": now.date().isoformat(),
              "made_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "counts": table,
              "differing": differing}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-rebuild.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(
        f"Counts compared: {sum(len(parts) for parts in table.values())}; differing: "
        f"{len(differing)}{': ' + ', '.join(differing) if differing else ''}. Written: {path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
