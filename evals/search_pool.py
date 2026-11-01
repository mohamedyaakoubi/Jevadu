"""Where the known projects of Test 2 stand in the list by meaning (design 13.3, 1 November 2026):
within the first 10, within the first 30, the pool that Gemini puts in order (search/rerank.py,
POOL), and within the first 50. A better order of the pool can bring into the first 10 at most the
projects that the pool holds, so the share of the first 30 is how far a better order alone can
take the search, on the same counted cases as Test 2.

    python -m evals.search_pool

The ideas are embedded through the meter, in the budget of the tests (a fraction of a cent), and
kept for a day. It writes evals/results/<UTC time>-search-pool.json, in numbers only: no idea and
no page.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from evals.test2.run import IDEAS_FILE, PAIRS, cases_of, projects_of, read_ideas
from hackathon_memory.search.rerank import POOL
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
TOPS = (10, POOL, 50)


def within(ranks: Sequence[tuple[str, int | None]]) -> dict:
    """How many known projects stand within each of TOPS, from (kind, place) pairs; a place of
    None is past the list that was read."""
    known = len(ranks)
    found = {}
    for top in TOPS:
        inside = sum(1 for _, place in ranks if place is not None and place <= top)
        found[f"first_{top}"] = {"found": inside, "known": known,
                                 "share": round(inside / known, 4) if known else 0.0}  # fmt: skip
    outside = Counter(kind for kind, place in ranks if place is None or place > POOL)
    found["outside_the_pool_by_kind"] = dict(sorted(outside.items()))
    return found


def main(argv: Sequence[str] | None = None) -> int:
    from hackathon_memory.db.embeddings import EmbeddingStore
    from hackathon_memory.finops.meter import metered_client
    from hackathon_memory.search import engine

    del argv
    settings = Settings()
    conninfo = settings.database_conninfo()
    ideas = read_ideas(Path(settings.data_dir) / "evals" / "test2" / IDEAS_FILE)
    pages = {page for pair in PAIRS for page in (pair.first, pair.second)}
    pages |= {idea.page for idea in ideas}
    projects = projects_of(conninfo, sorted(pages))
    cases = [case for case in cases_of(projects, ideas) if case.counted]
    with psycopg.connect(conninfo) as conn:
        page_of = dict(conn.execute("SELECT id, page_url FROM projects").fetchall())
    client = metered_client(settings, "embed_query", run_id="search-pool")
    store = EmbeddingStore(conninfo)
    ranks: list[tuple[str, int | None]] = []
    for case in cases:
        own = projects[case.asked_by].id if case.asked_by else None
        hits = engine.by_meaning(store, client, case.idea, model=settings.gemini_embedding_model,
                                 limit=max(TOPS) + 1)  # fmt: skip
        shown = [page_of[pid] for pid in hits if pid != own]
        ranks += [(case.kind, shown.index(page) + 1 if page in shown else None)
                  for page in case.known]  # fmt: skip
    now = datetime.now(UTC)
    result = {"test": "search-pool", "made_on": now.date().isoformat(),
              "cases_of": "test2, the counted cases", "pool_ordered": POOL,
              "embedding_model": settings.gemini_embedding_model,
              "projects_searched": len(page_of), **within(ranks)}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-search-pool.json"
    path.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for top in TOPS:
        number = result[f"first_{top}"]
        found, known, part = number["found"], number["known"], number["share"]
        print(f"within the first {top}: {found} of {known} ({part:.1%})")
    print(f"Written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
