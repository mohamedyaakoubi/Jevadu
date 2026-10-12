"""Gate B: the thinnest full path, on real projects (design 14.3).

    python -m proofs.gate_b                   the whole path, then the ideas of gate-b-questions.txt
    python -m proofs.gate_b --keep            the same, and the new database is kept to look at
    python -m proofs.gate_b --questions Q --results R
                                              the same, for the ideas of another file
    python -m proofs.gate_b --marks [R ...]   reads the marks given to one or more results files

The files are named without a folder: they are in data/by-hand. The proof runs in two parts.

1. The path. From an empty database, one command (python -m hackathon_memory.pipeline all)
   takes every saved project through all the steps. The pages and the READMEs were saved
   before, and none is asked for again. Then each idea of the file of ideas is searched. Each
   result must show what the mirror node said about its ids, or say that it gives none. An idea
   may name its known projects ("finds:"), and then they must be in the first 10 results. The
   results of every idea are written into the results file, for a person to mark.
2. The marks. Each result gets one of three marks:

       yes   the project is close to the idea, or shares a big part of it
       n/a   it is about something else, but has some small use for the idea
       no    it is unrelated, and of no use for the idea

   An idea that expects close projects needs at least one "yes" among its first 10 results. An
   idea written on purpose about something that the data may not hold says "expect: none": it
   shows what the search does when nothing is close, and it needs only its marks. Gate B needs
   at least three ideas that expect close projects, and every result marked.

The ideas are written without reading any project page first, so that the words of a page cannot
lean on them, and the scale of three marks is the maintainer's (12 October 2026). Gate B passes
when the result files of both parts pass.

The ideas, the results and the marks stay in data/by-hand, out of git. The result files hold
file names, places and numbers only: no idea, no name and no address of a project.
"""

from __future__ import annotations

import argparse
import re
import secrets
import shutil
import sys
from collections.abc import Mapping, Sequence
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
MARKS = ("yes", "n/a", "no")
CLOSE, NONE = "close", "none"  # what an idea expects to find in the data

DOES_NOT_PROVE = [
    "That the search is good. A few ideas show that the path works from end to end. How well "
    "the search finds similar projects is measured by the test of the search (design 13.3), "
    "on many more cases.",
    "That another reader would mark the results in the same way. A mark is the judgment of "
    "the one who wrote the idea.",
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
    expect: str = CLOSE  # NONE: written on purpose about something the data may not hold


def in_by_hand(folder: Path, name: str) -> Path:
    """A file of data/by-hand, given by its name alone."""
    if not name or Path(name).name != name or name in (".", ".."):
        raise ValueError(f"a file is named without a folder: {name!r}")
    return folder / name


def read_questions(path: Path) -> list[Question]:
    """Lines "idea: ...", each followed by zero or more lines "finds: <the address of a page>"
    and at most one line "expect: none" (or "expect: close", which is what an idea expects
    when it says nothing).

    Empty lines and lines that start with "#" are skipped.
    """
    questions: list[Question] = []
    idea: str | None = None
    finds: list[str] = []
    expect = CLOSE
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "idea" and value:
            if idea is not None:
                questions.append(Question(idea, tuple(finds), expect))
            idea, finds, expect = value, [], CLOSE
        elif key == "finds" and value.startswith("https://") and idea is not None:
            finds.append(value.rstrip("/"))
        elif key == "expect" and value.lower() in (CLOSE, NONE) and idea is not None:
            expect = value.lower()
        else:
            raise QuestionsError(
                f'line {number}: expected "idea: <words>", "finds: <https address>" or '
                '"expect: none"'
            )
    if idea is not None:
        questions.append(Question(idea, tuple(finds), expect))
    return questions


# --------------------------------------------------------------------- the results to mark


def results_text(
    ideas: list[tuple[Question, list[listing.ResultCard], dict[int, str]]], name: str = RESULTS
) -> str:
    """The results of every idea, for a person to mark. Each result ends with "mark:"."""
    lines = [
        f"# Gate B: the first {FIRST} results of each idea, made on {datetime.now(UTC):%Y-%m-%d} "
        "from a new, empty database.",
        '# Mark each result: write "yes", "n/a" or "no" after "mark:".',
        "#   yes = the project is close to the idea, or shares a big part of it",
        "#   n/a = it is about something else, but has some small use for the idea",
        "#   no  = it is unrelated, and of no use for the idea",
        '# An idea needs at least one "yes", unless it says "expect: none": then it needs only',
        "# its marks. When every result is marked, run:",
        f"#   python -m proofs.gate_b --marks {name}",
        "# This file stays out of git.",
        "",
    ]
    for number, (question, cards, short_lines) in enumerate(ideas, start=1):
        lines += [f"== idea {number}", f"idea: {question.idea}"]
        if question.expect == NONE:
            lines.append(f"expect: {NONE}")
        lines.append("")
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
    expect: str = CLOSE
    marks: list[tuple[int, str]] = field(default_factory=list)  # (place, one of MARKS)

    @property
    def first_yes(self) -> int | None:
        return min(self.places("yes"), default=None)

    @property
    def not_marked(self) -> int:
        return self.results - len(self.marks)

    def places(self, mark: str) -> list[int]:
        return [place for place, given in self.marks if given == mark]


_IDEA = re.compile(r"^== idea (\d+)$")
_EXPECT = re.compile(r"^expect:\s*(.*)$", re.IGNORECASE)
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
        expect = _EXPECT.match(line)
        if expect and ideas and place is None:
            value = expect.group(1).strip().lower()
            if value not in (CLOSE, NONE):
                raise MarksError(f'line {number}: an idea expects "close" or "none"')
            ideas[-1].expect = value
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
                raise MarksError(f'line {number}: a mark is "yes", "n/a", "no" or nothing')
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
    aside = path.with_name(f"{path.stem}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}{path.suffix}")
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
    questions: str = QUESTIONS,
    results: str = RESULTS,
) -> int:
    settings = settings or Settings()
    result = ProofResult(proof="gate_b", gate="B")
    result.does_not_prove.extend(DOES_NOT_PROVE)
    result.hide(settings.postgres_password.get_secret_value())

    folder = Path(settings.data_dir) / "by-hand"
    try:
        asked = read_questions(in_by_hand(folder, questions))
        results_path = in_by_hand(folder, results)
    except FileNotFoundError:
        result.check("the written ideas can be read", False, f"no file {questions}")
        return result.finish()
    except ValueError as wrong:  # a QuestionsError, or a file named with a folder
        result.check("the written ideas can be read", False, str(wrong))
        return result.finish()
    known = sum(len(q.finds) for q in asked)
    if not result.check(
        f"at least {MINIMUM_QUESTIONS} written ideas",
        len(asked) >= MINIMUM_QUESTIONS,
        f"{len(asked)} idea(s), {known} of them with known projects",
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
        for number, question in enumerate(asked, start=1):
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
                ledger = [line for line in card.ledger if line.network]
                if ledger:
                    shown["with_ledger_facts"] += 1
                    facts_ok &= all(line.asked_at is not None for line in ledger)
                else:
                    shown["saying_no_id"] += card.proof_status == "no_id_given"
                    facts_ok &= card.proof_status in ("no_id_given", None) and not card.ledger
            result.check(
                f"idea {number}: each result shows what the mirror node said, or that it gives "
                "no id",
                facts_ok and len(found) == min(FIRST, projects),
                f"{len(found)} result(s)",
            )

        aside = _keep_marked(results_path)
        results_path.write_text(results_text(to_mark, results), encoding="utf-8", newline="\n")
        written = read_marks(results_path)
        result.check(
            "the results of every idea are written for a person to mark",
            [idea.results for idea in written] == [len(cards) for _, cards, _ in to_mark],
            f"{len(written)} idea(s) in {results}"
            + (", and an earlier file with marks was kept" if aside else ""),
        )
        result.measurements.update(
            {
                "database": "a new one, deleted after the proof" if not keep else "kept",
                "projects": projects,
                "embeddings": embedded,
                "projects_with_an_id": with_ids,
                "answers_of_the_mirror_node": answers,
                "file_of_ideas": questions,
                "ideas": len(asked),
                "ideas_with_known_projects": sum(1 for q in asked if q.finds),
                "ideas_that_expect_nothing_close": sum(1 for q in asked if q.expect == NONE),
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


def judge(settings: Settings | None = None, files: Sequence[str] = (RESULTS,)) -> int:
    """Read the marks of one or more results files, by the rule of the module's docstring."""
    settings = settings or Settings()
    result = ProofResult(proof="gate_b_marks", gate="B")
    result.does_not_prove.extend(DOES_NOT_PROVE)
    folder = Path(settings.data_dir) / "by-hand"
    ideas: list[tuple[str, int, IdeaMarks]] = []
    for name in files:
        try:
            marked = read_marks(in_by_hand(folder, name))
        except FileNotFoundError:
            result.check(f"{name} can be read", False, "no such file: run the path first")
            return result.finish()
        except ValueError as wrong:  # a MarksError, or a file named with a folder
            result.check(f"{name} can be read", False, str(wrong))
            return result.finish()
        ideas += [(name, number, idea) for number, idea in enumerate(marked, start=1)]

    close = sum(1 for _, _, idea in ideas if idea.expect == CLOSE)
    result.check(
        f"at least {MINIMUM_QUESTIONS} ideas that expect close projects",
        close >= MINIMUM_QUESTIONS,
        f"{close} of {len(ideas)} idea(s)",
    )
    for name, number, idea in ideas:
        counts = ", ".join(f"{len(idea.places(mark))} {mark}" for mark in MARKS)
        detail = f"{counts}, {idea.not_marked} not marked"
        if idea.expect == CLOSE:
            result.check(
                f'{name}, idea {number}: at least one "yes" in the first {FIRST}, and every '
                "result marked",
                idea.first_yes is not None and idea.first_yes <= FIRST and idea.not_marked == 0,
                detail + (f"; the first yes at place {idea.first_yes}" if idea.first_yes else ""),
            )
        else:
            result.check(
                f"{name}, idea {number}: expects nothing close, and every result is marked",
                idea.not_marked == 0,
                detail,
            )
    result.measurements["ideas"] = [
        {
            "file": name,
            "idea": number,
            "expect": idea.expect,
            "results": idea.results,
            **{mark: len(idea.places(mark)) for mark in MARKS},
            "not_marked": idea.not_marked,
            "first_yes_at": idea.first_yes,
            "places": {mark: idea.places(mark) for mark in MARKS},
        }
        for name, number, idea in ideas
    ]
    return result.finish()


def main(arguments: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m proofs.gate_b",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--keep", action="store_true", help="keep the new database to look at")
    parser.add_argument("--questions", default=QUESTIONS, help="the file of ideas")
    parser.add_argument("--results", default=RESULTS, help="the results file to write")
    parser.add_argument(
        "--marks", nargs="*", metavar="RESULTS", help="read the marks of these results files"
    )
    given = parser.parse_args(list(arguments))
    if given.marks is not None:
        return judge(files=given.marks or [RESULTS])
    return run(keep=given.keep, questions=given.questions, results=given.results)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
