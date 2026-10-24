"""The stand-in for the search model, measured against it on the cases of Test 2: Gemini 3.8 Flash
(the search model, at its level of thinking) and DeepSeek V4.1 Flash on Vertex AI, without
thinking and thinking at the effort "high", each putting the same 30 closest projects by meaning
in order.

    python -m evals.search_fallback

The maintainer asked on 24 October 2026 for DeepSeek V4.1 Flash on high thinking as the stand-in
when Gemini keeps failing, after a quick benchmark against Gemini 3.8 Flash. A first trial call on
high thinking was far too slow for a page, so the version without thinking is measured too.

For each counted case of Test 2, the 30 projects closest to the idea by meaning (the project that
gives the idea left out) go to each model with the same instructions and lines (search/rerank.py),
and the known projects in each model's first 10 are counted, as in evals/search_modes.py. A call
that fails or is late keeps the order of meaning for that case and is counted as failed. The order
of meaning itself, with no model, is counted too (MEANING), so that a stand-in is used only when it
finds more than no model at all. WORKERS cases run at the same time, so that the slow version ends
within the hour; the times are those of each call.

It writes evals/results/<UTC time>-search-fallback.json, in numbers only: for each model the
known projects found in the first 10 with a range by group of cases, the seconds of a call (middle
and 95 of 100), the failed calls, and the cost of a call from the ledger. No idea and no text of a
page.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from evals.search_modes import POOL, TEXT_LETTERS, summary
from evals.test2.cases import PAIRS
from evals.test2.ideas import FILE as IDEAS_FILE
from evals.test2.ideas import read as read_ideas
from evals.test2.run import FIRST, cases_of, projects_of
from hackathon_memory.db.embeddings import EmbeddingStore
from hackathon_memory.finops.calls import PostgresStore
from hackathon_memory.finops.meter import metered_client
from hackathon_memory.llm.open_models import DEEPSEEK_FLASH, open_models
from hackathon_memory.search import engine
from hackathon_memory.search.rerank import NOT_ORDERED, OPEN_EFFORT, OPEN_OFF, by_ai, texts_of
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
PURPOSE = "search_fallback"
MEANING = "meaning, no model"
WORKERS = 6
# One try of each call, long enough to measure a slow answer, not to cut it: thinking on "high"
# can take minutes.
SECONDS = {"quick": 120.0, "thinking": 420.0}


def main(argv: Sequence[str]) -> int:
    if argv:
        print("usage: python -m evals.search_fallback")
        return 2
    settings = Settings()
    conninfo = settings.database_conninfo()
    ideas = read_ideas(Path(settings.data_dir) / "evals" / "test2" / IDEAS_FILE)
    pages = {page for pair in PAIRS for page in (pair.first, pair.second)}
    pages |= {idea.page for idea in ideas}
    projects = projects_of(conninfo, sorted(pages))
    cases = [case for case in cases_of(projects, ideas) if case.counted]
    with psycopg.connect(conninfo) as conn:
        page_of = dict(conn.execute("SELECT id, page_url FROM projects").fetchall())
    run_id = f"search-fallback-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    started = datetime.now(UTC)
    gemini = metered_client(settings, PURPOSE, run_id=run_id)
    deepseek = open_models(settings, PURPOSE, run_id=run_id)
    search_level = settings.gemini_search_thinking_level
    models: dict[str, tuple[Any, str, str, float]] = {
        f"{settings.gemini_search_model} {search_level}":
            (gemini, settings.gemini_search_model, search_level, SECONDS["quick"]),
        f"{DEEPSEEK_FLASH} {OPEN_OFF}": (deepseek, DEEPSEEK_FLASH, OPEN_OFF, SECONDS["quick"]),
        f"{DEEPSEEK_FLASH} {OPEN_EFFORT}":
            (deepseek, DEEPSEEK_FLASH, OPEN_EFFORT, SECONDS["thinking"]),
    }  # fmt: skip
    store = EmbeddingStore(conninfo)
    texts = texts_of(conninfo)

    def one_case(number: int, case: Any) -> list[dict]:
        own = projects[case.asked_by].id if case.asked_by else None
        meaning = engine.by_meaning(store, gemini.tagged(purpose="embed_query"), case.idea,
                                    model=settings.gemini_embedding_model,
                                    limit=POOL + 1)  # fmt: skip
        pool = [pid for pid in meaning if pid != own][:POOL]
        shown = [page_of[pid] for pid in pool][:FIRST]
        rows = [{"case": number, "group": case.group, "mode": MEANING,
                 "found": sum(page in shown for page in case.known), "known": len(case.known),
                 "seconds": 0.0, "failed": False}]  # fmt: skip
        for name, (client, model, level, seconds) in models.items():
            begin = time.perf_counter()
            failed = False
            try:
                ordered = by_ai(client.tagged(item_ref=f"{number}:{name}"), model, level, case.idea,
                                pool, texts, letters=TEXT_LETTERS, with_text=True,
                                timeout_seconds=seconds)  # fmt: skip
            except NOT_ORDERED:
                failed, ordered = True, []
            took = time.perf_counter() - begin
            ranked = ordered + [pid for pid in pool if pid not in ordered]
            shown = [page_of[pid] for pid in ranked][:FIRST]
            rows.append({"case": number, "group": case.group, "mode": name,
                         "found": sum(page in shown for page in case.known),
                         "known": len(case.known), "seconds": round(took, 2),
                         "failed": failed})  # fmt: skip
        return rows

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as workers:
        running = [workers.submit(one_case, number, case)
                   for number, case in enumerate(cases, start=1)]  # fmt: skip
        for count, future in enumerate(as_completed(running), start=1):
            try:
                done = future.result()
            except Exception as error:  # noqa: BLE001 - one broken case must not stop the others
                print(f"{count} of {len(cases)} cases: one failed with {type(error).__name__}",
                      flush=True)  # fmt: skip
                continue
            rows.extend(done)
            print(f"{count} of {len(cases)} cases (case {done[0]['case']}): " + ", ".join(
                f"{r['mode']} {r['found']}/{r['known']} {r['seconds']} s"
                + (" failed" * r["failed"]) for r in done), flush=True)  # fmt: skip
    modes = [MEANING, *models]
    rows.sort(key=lambda row: (row["case"], modes.index(row["mode"])))
    ledger = [call for call in PostgresStore(conninfo).calls(since=started)
              if call.run_id == run_id and call.purpose == PURPOSE]  # fmt: skip
    costs: dict[str, list[float]] = {}
    for call in ledger:
        costs.setdefault((call.item_ref or "").partition(":")[2], []).append(call.cost_usd or 0.0)
    now = datetime.now(UTC)
    result = {
        "test": "search-fallback",
        "made_on": now.strftime("%Y-%m-%d"),
        "made_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cases_of": "test2, the counted cases",
        "pool_ordered": POOL,
        "cases_at_once": WORKERS,
        "seconds_limit": {name: spec[3] for name, spec in models.items()},
        "models": summary(rows, costs, modes=modes),
        "rows": rows,
    }  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-search-fallback.json"
    path.write_bytes((json.dumps(result, indent=1) + "\n").encode("utf-8"))
    for name, numbers in result["models"].items():
        print(f"{name}: {numbers['found']} of {numbers['known']} = {numbers['share']} "
              f"{numbers['range']}, {numbers['seconds_middle']} s, "
              f"{numbers['cost_usd_per_search']} dollars, "
              f"{numbers['failed_ai_calls']} failed")  # fmt: skip
    print(f"Written: {path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
