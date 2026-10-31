"""What the comparison of design 8.3 should read: the card of each project, or its full text.

    python -m evals.compare_inputs data/evals/test2/ideas.txt

For each of the maintainer's ideas of Test 2, the search finds the first 10 projects by meaning,
as the quick results do, and the comparison is asked twice: once with the cards (what the website
does since 15 October 2026), once with the full text of each page: its name, its short line and
every section as the team wrote it. The order of the two turns from one idea to the next, so that
a slow minute of the service does not fall on one of them only.

It writes evals/results/<UTC time>-compare-inputs.json, in numbers only: for each call the
seconds, the tokens, the cost and how many projects got a comparison. The sentences are written
side by side into data/evals/compare-inputs/<UTC time>.html, a local file outside git, for the
maintainer to read and choose which input gives the more right comparison. The program does not
judge the sentences: a person does (design rule 6).
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from evals.compare_levels import middle
from evals.test2.ideas import IdeasError, read
from hackathon_memory.db.embeddings import EmbeddingStore
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.finops.calls import PostgresStore
from hackathon_memory.finops.meter import metered_client
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.pipeline.embed import FAILED_CALLS
from hackathon_memory.search import compare as comparing
from hackathon_memory.search import engine
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
FIRST = 10  # the first results that the website compares
INPUTS = ("cards", "full_text")
LEVEL = "LOW"  # the level of the search model on the website since 16 October 2026


def full_items(conninfo: str, project_ids: Sequence[int]) -> list[comparing.Item]:
    """Each project as its own page says it: the name, the short line, and every section in
    the order of the page."""
    with psycopg.connect(conninfo) as conn:
        rows = {pid: (name, short) for pid, name, short in conn.execute(
            "SELECT id, name, coalesce(short_line, '') FROM projects WHERE id = ANY(%s)",
            (list(project_ids),)).fetchall()}  # fmt: skip
        sections: dict[int, list[str]] = {}
        for pid, body in conn.execute(
            "SELECT project_id, body FROM sections WHERE project_id = ANY(%s) "
            "ORDER BY project_id, position", (list(project_ids),)).fetchall():  # fmt: skip
            sections.setdefault(pid, []).append(body.strip())
    items = []
    for number, pid in enumerate(project_ids, start=1):
        if pid not in rows:
            continue
        name, short = rows[pid]
        texts = {"name": name}
        if short.strip():
            texts["short_line"] = short.strip()
        if sections.get(pid):
            texts["page_text"] = "\n\n".join(sections[pid])
        items.append(comparing.Item(number, pid, texts))
    return items


def measure(settings: Settings, ideas: Sequence[Any]) -> tuple[list[dict], list[dict]]:
    """Ask the comparison of each idea with each input; one row of numbers for each call, and
    the sentences of each idea for the page to read."""
    conninfo = settings.database_conninfo()
    run = f"compare-inputs-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    client = metered_client(settings, "compare_inputs", run_id=run)
    started = datetime.now(UTC)
    rows, pages = [], []
    for turn, idea in enumerate(ideas):
        ids = engine.by_meaning(
            EmbeddingStore(conninfo), client.tagged(purpose="embed_query"), idea.words,
            model=settings.gemini_embedding_model, limit=FIRST,
        )  # fmt: skip
        given = {
            "cards": comparing.items_for(conninfo, ids, models=settings.card_models(),
                                         version=INSTRUCTIONS_VERSION),
            "full_text": full_items(conninfo, ids),
        }  # fmt: skip
        answers: dict[str, dict] = {}
        order = list(INPUTS) if turn % 2 == 0 else list(reversed(INPUTS))
        for name in order:
            ref = f"{idea.number}:{name}"
            begin = time.perf_counter()
            try:
                found = comparing.compare(client.tagged(item_ref=ref), idea.words, given[name],
                                          model=settings.gemini_search_model,
                                          thinking_level=LEVEL)  # fmt: skip
                failed = False
            except (comparing.CompareError, BudgetExceeded, *FAILED_CALLS):
                found, failed = {}, True
            seconds = round(time.perf_counter() - begin, 1)
            answers[name] = found
            rows.append({"idea": idea.number, "input": name, "seconds": seconds,
                         "failed": failed, "projects": len(given[name]),
                         "answered": len(found)})  # fmt: skip
            print(f"idea {idea.number}, {name}: {seconds} s, {len(found)} of {len(given[name])}")
        pages.append({"idea": idea, "ids": ids, "names": {i.project_id: i.texts["name"]
                      for i in given["full_text"]}, "answers": answers})  # fmt: skip
    ledger = [call for call in PostgresStore(conninfo).calls(since=started) if call.run_id == run]
    for row in rows:
        mine = [c for c in ledger if c.item_ref == f"{row['idea']}:{row['input']}"]
        row |= {"attempts": len(mine), "input_tokens": sum(c.input_tokens for c in mine),
                "output_tokens": sum(c.output_tokens for c in mine),
                "cost_usd": round(sum(c.cost_usd or 0.0 for c in mine), 6)}  # fmt: skip
    return rows, pages


def summary(rows: Sequence[dict]) -> dict:
    found = {}
    for name in INPUTS:
        mine = [row for row in rows if row["input"] == name]
        done = [row for row in mine if not row["failed"]]
        found[name] = {
            "calls": len(mine), "failed": len(mine) - len(done),
            "seconds_middle": round(middle([row["seconds"] for row in done]), 1) if done else None,
            "input_tokens_middle": middle([row["input_tokens"] for row in done]),
            "cost_usd": round(sum(row["cost_usd"] for row in mine), 6),
            "projects_answered": sum(row["answered"] for row in done),
            "projects_asked": sum(row["projects"] for row in done),
        }  # fmt: skip
    return found


def side_by_side(pages: Sequence[dict], made: str) -> str:
    """One local page: for each idea and each project, the two comparisons next to each other."""
    parts = [f"<!doctype html><meta charset='utf-8'><title>Card or full text, {made}</title>",
             "<style>body{font-family:system-ui,sans-serif;max-width:70rem;margin:2rem auto;"
             "padding:0 1rem;line-height:1.45}td,th{vertical-align:top;padding:.4rem .6rem;"
             "border-top:1px solid #ccc;text-align:left}table{border-collapse:collapse;"
             "width:100%}h2{margin-top:2.5rem}</style>",
             f"<h1>What should the comparison read? ({made})</h1>",
             "<p>For each of your ideas, the same 10 closest projects. On the left Gemini "
             "read each project's card, on the right its full text. Read both and choose the "
             "column whose sentences are more right. Nothing here judges a project.</p>",
             ]  # fmt: skip
    for page in pages:
        parts.append(f"<h2>Idea {page['idea'].number}</h2><p><b>{html.escape(page['idea'].words)}"
                     "</b></p><table><tr><th>Project</th><th>From the card</th>"
                     "<th>From the full text</th></tr>")  # fmt: skip
        for pid in page["ids"]:
            cells = []
            for name in INPUTS:
                one = page["answers"].get(name, {}).get(pid)
                cells.append("<td>no answer</td>" if one is None else
                             f"<td><b>Same</b> {html.escape(one.same)}<br><b>Differs</b> "
                             f"{html.escape(one.differs)}</td>")  # fmt: skip
            parts.append(f"<tr><td>{html.escape(page['names'].get(pid, str(pid)))}</td>"
                         + "".join(cells) + "</tr>")  # fmt: skip
        parts.append("</table>")
    return "\n".join(parts) + "\n"


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.compare_inputs",
                                     description=__doc__.splitlines()[0])  # fmt: skip
    parser.add_argument("ideas", type=Path, help="the file of ideas of Test 2")
    arguments = parser.parse_args(argv)
    settings = Settings()
    try:
        ideas = [idea for idea in read(arguments.ideas) if idea.words]
    except IdeasError as error:
        print(f"Stopped: {error}")
        return 1
    rows, pages = measure(settings, ideas)
    made = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    result = {
        "test": "compare-inputs",
        "made_on": datetime.now(UTC).strftime("%Y-%m-%d"),
        "model": settings.gemini_search_model,
        "thinking_level": LEVEL,
        "instructions_version": comparing.INSTRUCTIONS_VERSION,
        "cards_of": INSTRUCTIONS_VERSION,
        "ideas": len(ideas),
        "first_results": FIRST,
        "inputs": summary(rows),
        "calls": rows,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{made}-compare-inputs.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    local = Path(settings.data_dir) / "evals" / "compare-inputs" / f"{made}.html"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(side_by_side(pages, result["made_on"]), encoding="utf-8")
    for name, numbers in result["inputs"].items():
        answered = f"{numbers['projects_answered']} of {numbers['projects_asked']} answered"
        print(f"{name}: middle {numbers['seconds_middle']} s, {numbers['cost_usd']} dollars, "
              f"{answered}")  # fmt: skip
    print(f"Written: {path.as_posix()} (numbers) and {local.as_posix()} (to read, not in git)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
