"""Gate B: the thinnest full path, on real projects (design 14.3).

    python -m proofs.gate_b             about 20 minutes: it asks the mirror node and Google
    python -m proofs.gate_b --keep      the same, and the new database is kept to look at

From an empty database, one command (python -m hackathon_memory.pipeline all) takes every saved
project through parse, readmes, check and embed. The pages and the READMEs were saved before,
and none is asked for again. Then each written question of data/by-hand/gate-b-questions.txt is
searched. The proof checks that the known projects of each question are in the first 10
results, and that each result shows what the mirror node said about its ids, or says that it
gives none.

The questions and their known projects are written by a person, in a file that stays out of
git. The result file holds places and numbers only: no question, no name and no address of a
project.
"""

from __future__ import annotations

import secrets
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr

from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.runs import last_runs
from hackathon_memory.finops.meter import metered_client
from hackathon_memory.pipeline.__main__ import ALL_STEPS
from hackathon_memory.pipeline.__main__ import main as pipeline_main
from hackathon_memory.search import engine, listing
from hackathon_memory.settings import Settings
from proofs.result import ProofResult

QUESTIONS = "gate-b-questions.txt"  # in data/by-hand, out of git
FIRST = 10
MINIMUM_PROJECTS = 50
MINIMUM_QUESTIONS = 3

DOES_NOT_PROVE = [
    "That the search is good. Three questions show that the path works from end to end. How "
    "well the search finds similar projects is measured by the test of the search (design "
    "13.3), on many more cases.",
    "That the questions are blind. A person wrote each one after seeing the page of its known "
    "project.",
    "That an id belongs to the team that names it, or that a project is still alive.",
    "That the projects of an event with no typed end can be judged: their ids are asked, and "
    'the rule waits for the end of the event ("window_not_known").',
]


class QuestionsError(ValueError):
    """The file of questions cannot be read. The message names the line, never its text."""


@dataclass(frozen=True)
class Question:
    idea: str
    finds: tuple[str, ...]  # the addresses of the pages of its known projects


def read_questions(path: Path) -> list[Question]:
    """Blocks of one line "idea: ..." and one or more lines "finds: <the address of a page>".

    Empty lines and lines that start with "#" are skipped.
    """
    questions: list[Question] = []
    idea: str | None = None
    finds: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "idea" and value:
            if idea is not None:
                if not finds:
                    raise QuestionsError(f"line {number}: the idea before it finds no project")
                questions.append(Question(idea, tuple(finds)))
            idea, finds = value, []
        elif key == "finds" and value.startswith("https://") and idea is not None:
            finds.append(value.rstrip("/"))
        else:
            raise QuestionsError(
                f'line {number}: expected "idea: <words>" or "finds: <https address>"'
            )
    if idea is not None:
        if not finds:
            raise QuestionsError("the last idea finds no project")
        questions.append(Question(idea, tuple(finds)))
    return questions


def run(
    settings: Settings | None = None,
    *,
    keep: bool = False,
    mirrors: Mapping | None = None,
    google: object = None,
    minimum_projects: int = MINIMUM_PROJECTS,
) -> int:
    settings = settings or Settings()
    result = ProofResult(proof="gate_b", gate="B")
    result.does_not_prove.extend(DOES_NOT_PROVE)
    result.hide(settings.postgres_password.get_secret_value())

    path = Path(settings.data_dir) / "by-hand" / QUESTIONS
    try:
        questions = read_questions(path)
    except FileNotFoundError:
        result.check("the written questions can be read", False, f"no file {QUESTIONS}")
        return result.finish()
    except QuestionsError as wrong:
        result.check("the written questions can be read", False, str(wrong))
        return result.finish()
    if not result.check(
        f"at least {MINIMUM_QUESTIONS} written questions, each with its known project",
        len(questions) >= MINIMUM_QUESTIONS,
        f"{len(questions)} question(s), {sum(len(q.finds) for q in questions)} known project(s)",
    ):
        return result.finish()

    server = settings.database_conninfo()
    name = "gate_b_" + secrets.token_hex(4)
    with psycopg.connect(server, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        conninfo = make_conninfo(server, dbname=name)
        migrate(conninfo)
        with psycopg.connect(conninfo) as conn:
            before = conn.execute("SELECT count(*) FROM projects").fetchone()[0]
        result.check("the database starts empty", before == 0, f"a new database, {before} projects")
        fresh = settings.model_copy(update={"database_url": SecretStr(conninfo)})

        print("--- one command: python -m hackathon_memory.pipeline all --no-requests")
        code = pipeline_main(["all", "--no-requests"], fresh, mirrors, google)
        runs = list(reversed(last_runs(conninfo, limit=len(ALL_STEPS))))
        steps = [row["step"] for row in runs]
        with psycopg.connect(conninfo) as conn:
            projects = conn.execute("SELECT count(*) FROM projects").fetchone()[0]
            embedded = conn.execute("SELECT count(*) FROM project_embeddings").fetchone()[0]
            with_ids = conn.execute("SELECT count(DISTINCT project_id) FROM hedera_ids").fetchone()[
                0
            ]
            answers = conn.execute("SELECT count(*) FROM ledger_facts").fetchone()[0]
        result.check(
            "one command took the projects through parse, readmes, check and embed",
            code == 0 and steps == list(ALL_STEPS) and all(row["ok"] for row in runs),
            f"steps {steps}, exit code {code}",
        )
        result.check(
            f"at least {minimum_projects} real projects went the whole way",
            projects >= minimum_projects and embedded == projects,
            f"{projects} projects, {embedded} embeddings",
        )

        client = google or metered_client(fresh, "gate_b", run_id=name)
        model = settings.gemini_embedding_model
        with psycopg.connect(conninfo) as conn:
            page_ids = dict(conn.execute("SELECT page_url, id FROM projects").fetchall())
        places: list[list[int | None]] = []
        shown = {"results": 0, "with_ledger_facts": 0, "saying_no_id": 0}
        for number, question in enumerate(questions, start=1):
            hits = engine.search(conninfo, client, question.idea, model=model, limit=FIRST)
            found = listing.cards(conninfo, hits)
            rank_of = {card.hit.project_id: card.rank for card in found}
            here = [rank_of.get(page_ids.get(page, -1)) for page in question.finds]
            places.append(here)
            result.check(
                f"question {number}: its known project(s) in the first {FIRST} results",
                all(place is not None for place in here),
                "place(s): " + ", ".join(str(place) if place else "not there" for place in here),
            )
            facts_ok = True
            for card in found:
                shown["results"] += 1
                asked = [line for line in card.ledger if line.network]
                if asked:
                    shown["with_ledger_facts"] += 1
                    facts_ok &= all(line.asked_at is not None for line in asked)
                else:
                    shown["saying_no_id"] += card.proof_status == "no_id_given"
                    facts_ok &= card.proof_status in ("no_id_given", None) and not card.ledger
            result.check(
                f"question {number}: each result shows what the mirror node said, or that it "
                "gives no id",
                facts_ok and len(found) == min(FIRST, projects),
                f"{len(found)} result(s)",
            )
        result.measurements.update(
            {
                "database": "a new one, deleted after the proof" if not keep else "kept",
                "projects": projects,
                "embeddings": embedded,
                "projects_with_an_id": with_ids,
                "answers_of_the_mirror_node": answers,
                "questions": len(questions),
                "places_of_the_known_projects": places,
                "results_shown": shown,
                "embedding_model": model,
            }
        )
    finally:
        if not keep:
            with psycopg.connect(server, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
                )
        else:
            print(f"The database {name} is kept.")
    return result.finish()


if __name__ == "__main__":
    sys.exit(run(keep="--keep" in sys.argv[1:]))
