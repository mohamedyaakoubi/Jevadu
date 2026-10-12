"""Gate B: the thinnest full path, on real projects (design 14.3).

    python -m proofs.gate_b             about 20 minutes: the whole path, then the ideas
    python -m proofs.gate_b --keep      the same, and the new database is kept to look at
    python -m proofs.gate_b --marks     reads the marks that a person gave the results

It runs in two parts.

1. The path. From an empty database, one command (python -m hackathon_memory.pipeline all)
   takes every saved project through all the steps. The pages and the READMEs were saved
   before, and none is asked for again. Then each idea of data/by-hand/gate-b-questions.txt is
   searched. Each result must show what the mirror node said about its ids, or say that it gives
   none. An idea may name its known projects ("finds:"), and then they must be in the first 10
   results. The results of every idea are written into data/by-hand/gate-b-results.txt.
2. The marks. A person marks each result "yes" (the project is close to the idea, or shares a
   big part of it) or "no". With --marks the proof reads the marks: each idea needs at least
   one "yes" among its first 10 results.

The maintainer decided on 12 October 2026 to write the ideas without reading any project page
first, so that the words of a page cannot lean on them. An idea with no known project is judged
by the marks. Gate B passes when both result files pass.

The ideas, the results and the marks stay in data/by-hand, out of git. The result files hold
places and numbers only: no idea, no name and no address of a project.
"""

from __future__ import annotations

import re
import secrets
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
RESULTS = "gate-b-results.txt"  # in data/by-hand, out of git: the results to mark
FIRST = 10
MINIMUM_PROJECTS = 50
MINIMUM_QUESTIONS = 3
MARKS = ("yes", "no")

DOES_NOT_PROVE = [
    "That the search is good. Three ideas show that the path works from end to end. How well "
    "the search finds similar projects is measured by the test of the search (design 13.3), "
    "on many more cases.",
    "That another person would mark the results in the same way. A mark is the judgment of the "
    "person who wrote the idea.",
    "That an id belongs to the team that names it, or that a project is still alive.",
]


class QuestionsError(ValueError):
    """The file of ideas cannot be read. The message names the line, never its text."""


class MarksError(ValueError):
    """The file of results cannot be read. The message names the line, never its text."""


@dataclass(frozen=True)
class Question:
    idea: str
    finds: tuple[str, ...]  # the addresses of the pages of its known projects; may be empty


def read_questions(path: Path) -> list[Question]:
    """Lines "idea: ...", each followed by zero or more lines "finds: <the address of a page>".

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
                questions.append(Question(idea, tuple(finds)))
            idea, finds = value, []
        elif key == "finds" and value.startswith("https://") and idea is not None:
            finds.append(value.rstrip("/"))
        else:
            raise QuestionsError(
                f'line {number}: expected "idea: <words>" or "finds: <https address>"'
            )
    if idea is not None:
        questions.append(Question(idea, tuple(finds)))
    return questions


# --------------------------------------------------------------------- the results to mark


def results_text(ideas: list[tuple[Question, list[listing.ResultCard], dict[int, str]]]) -> str:
    """The results of every idea, for a person to mark. Each result ends with "mark:"."""
    lines = [
        f"# Gate B: the first {FIRST} results of each idea, made on {datetime.now(UTC):%Y-%m-%d} "
        "from a new, empty database.",
        '# Mark each result: write "yes" or "no" after "mark:".',
        "#   yes = the project is close to the idea, or shares a big part of it",
        "#   no  = it does not",
        '# Gate B passes when each idea has at least one "yes". Then run:',
        "#   python -m proofs.gate_b --marks",
        "# This file stays out of git.",
        "",
    ]
    for number, (question, cards, short_lines) in enumerate(ideas, start=1):
        lines += [f"== idea {number}", f"idea: {question.idea}", ""]
        for card in cards:
            shown = listing.lines([card])
            short = short_lines.get(card.hit.project_id, "")
            lines.append(shown[0])
            if short:
                lines.append(f"   {short}")
            lines += shown[1:]
            lines += ["   mark:", ""]
    return "\n".join(lines) + "\n"


@dataclass
class IdeaMarks:
    results: int = 0
    marks: list[tuple[int, str]] = field(default_factory=list)  # (place, "yes" or "no")

    @property
    def first_yes(self) -> int | None:
        return min((place for place, mark in self.marks if mark == "yes"), default=None)


_IDEA = re.compile(r"^== idea (\d+)$")
_PLACE = re.compile(r"^(\d+)\. ")
_MARK = re.compile(r"^\s*mark:\s*(.*)$", re.IGNORECASE)


def read_marks(path: Path) -> list[IdeaMarks]:
    """The marks of each idea, in the order of the ideas."""
    ideas: list[IdeaMarks] = []
    place: int | None = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if _IDEA.match(line.strip()):
            ideas.append(IdeaMarks())
            place = None
            continue
        found = _PLACE.match(line)
        if found and ideas:
            place = int(found.group(1))
            ideas[-1].results += 1
            continue
        mark = _MARK.match(line)
        if mark and ideas and place is not None:
            value = mark.group(1).strip().lower()
            if value in MARKS:
                ideas[-1].marks.append((place, value))
            elif value:
                raise MarksError(f'line {number}: a mark is "yes", "no" or nothing')
    return ideas


def _keep_marked(path: Path) -> Path | None:
    """Move a results file that holds marks aside, so that a new run never loses them."""
    if not path.exists():
        return None
    try:
        marked = any(idea.marks for idea in read_marks(path))
    except MarksError:
        marked = True  # a file that cannot be read is kept too
    if not marked:
        return None
    aside = path.with_name(f"gate-b-results-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.txt")
    shutil.move(path, aside)
    return aside


# --------------------------------------------------------------------- part 1: the path


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

    folder = Path(settings.data_dir) / "by-hand"
    try:
        questions = read_questions(folder / QUESTIONS)
    except FileNotFoundError:
        result.check("the written ideas can be read", False, f"no file {QUESTIONS}")
        return result.finish()
    except QuestionsError as wrong:
        result.check("the written ideas can be read", False, str(wrong))
        return result.finish()
    known = sum(len(q.finds) for q in questions)
    if not result.check(
        f"at least {MINIMUM_QUESTIONS} written ideas",
        len(questions) >= MINIMUM_QUESTIONS,
        f"{len(questions)} idea(s), {known} of them with known projects",
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
            "one command took the projects through every step of the path",
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
            short_lines = dict(conn.execute("SELECT id, short_line FROM projects").fetchall())
        places: list[list[int | None]] = []
        shown = {"results": 0, "with_ledger_facts": 0, "saying_no_id": 0}
        to_mark: list[tuple[Question, list[listing.ResultCard], dict[int, str]]] = []
        for number, question in enumerate(questions, start=1):
            hits = engine.search(conninfo, client, question.idea, model=model, limit=FIRST)
            found = listing.cards(conninfo, hits)
            to_mark.append((question, found, short_lines))
            if question.finds:
                rank_of = {card.hit.project_id: card.rank for card in found}
                here = [rank_of.get(page_ids.get(page, -1)) for page in question.finds]
                places.append(here)
                result.check(
                    f"idea {number}: its known project(s) in the first {FIRST} results",
                    all(place is not None for place in here),
                    "place(s): "
                    + ", ".join(str(place) if place else "not there" for place in here),
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
                f"idea {number}: each result shows what the mirror node said, or that it gives "
                "no id",
                facts_ok and len(found) == min(FIRST, projects),
                f"{len(found)} result(s)",
            )

        results_path = folder / RESULTS
        aside = _keep_marked(results_path)
        results_path.write_text(results_text(to_mark), encoding="utf-8", newline="\n")
        written = read_marks(results_path)
        result.check(
            "the results of every idea are written for a person to mark",
            [idea.results for idea in written] == [len(cards) for _, cards, _ in to_mark],
            f"{len(written)} idea(s) in {RESULTS}"
            + (", and an earlier file with marks was kept" if aside else ""),
        )
        result.measurements.update(
            {
                "database": "a new one, deleted after the proof" if not keep else "kept",
                "projects": projects,
                "embeddings": embedded,
                "projects_with_an_id": with_ids,
                "answers_of_the_mirror_node": answers,
                "ideas": len(questions),
                "ideas_with_known_projects": sum(1 for q in questions if q.finds),
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


# --------------------------------------------------------------------- part 2: the marks


def judge(settings: Settings | None = None) -> int:
    """Read the marks of the results file: each idea needs at least one "yes"."""
    settings = settings or Settings()
    result = ProofResult(proof="gate_b_marks", gate="B")
    result.does_not_prove.extend(DOES_NOT_PROVE)
    path = Path(settings.data_dir) / "by-hand" / RESULTS
    try:
        ideas = read_marks(path)
    except FileNotFoundError:
        result.check("the results can be read", False, f"no file {RESULTS}: run the path first")
        return result.finish()
    except MarksError as wrong:
        result.check("the results can be read", False, str(wrong))
        return result.finish()
    result.check(f"at least {MINIMUM_QUESTIONS} ideas", len(ideas) >= MINIMUM_QUESTIONS,
                 f"{len(ideas)} idea(s)")  # fmt: skip
    for number, idea in enumerate(ideas, start=1):
        yes = sum(1 for _, mark in idea.marks if mark == "yes")
        result.check(
            f'idea {number}: at least one result marked "yes" in the first {FIRST}',
            idea.first_yes is not None and idea.first_yes <= FIRST,
            f"{yes} yes, {len(idea.marks) - yes} no, {idea.results - len(idea.marks)} not marked"
            + (f"; the first yes at place {idea.first_yes}" if idea.first_yes else ""),
        )
    result.measurements["ideas"] = [
        {
            "results": idea.results,
            "yes": sum(1 for _, mark in idea.marks if mark == "yes"),
            "no": sum(1 for _, mark in idea.marks if mark == "no"),
            "not_marked": idea.results - len(idea.marks),
            "first_yes_at": idea.first_yes,
        }
        for idea in ideas
    ]
    return result.finish()


if __name__ == "__main__":
    arguments = sys.argv[1:]
    sys.exit(judge() if "--marks" in arguments else run(keep="--keep" in arguments))
