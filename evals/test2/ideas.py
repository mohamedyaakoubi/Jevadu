"""Test 2, the ideas of the maintainer, written in their own words (design 13.3).

    python -m evals.test2.ideas draw     writes data/evals/test2/ideas.txt, once: 30 projects
    python -m evals.test2.ideas check    checks the written ideas and counts them

The file lists 30 projects drawn at random, with a fixed seed, from the full cards that are not
in the tuning set or in Test 1, so that each test stands alone. For each project it gives a
number, the name and the short line. The maintainer picks 15 and writes, on the line "idea:" of
each, the idea as a builder would type it into the search: in their own words, without opening
the page. That project is then the known answer of the idea, and Test 2 counts how often the
search shows it in the first 10 results.

The file stays in data/evals/test2, out of git: it holds names and short lines of the pages, and
the maintainer's words. `check` prints numbers only. It flags an idea that repeats four words in
a row from the name or the short line, because a copied idea measures the copy, not the search.
"""

from __future__ import annotations

import random
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hackathon_memory.read.sets import pages_of

SEED = 20261014
DRAWN = 30
WANTED = 15
COPIED_WORDS = 4
FILE = "ideas.txt"
SETS = Path(__file__).parent.parent / "sets"
HEADER = """\
# Test 2: ideas in your own words (design 13.3)
#
# Below are {count} projects, drawn at random. Pick {wanted} of them. For each one you pick:
#   1. Read only its name and its short line. Do not open its page.
#   2. After "idea:", write the idea as a builder would type it into the search box,
#      in your own words, in one line.
#   3. Do not copy words from the short line. Say the idea the way you would say it.
# Leave the other projects with an empty "idea:". Save the file in the same place.
#
# Example (invented):
#   name: CoffeeTrail
#   short line: Track every coffee sack from farm to cup on Hedera.
#   idea: an app that shows a buyer where their coffee came from
#
# Then the search must find that project in its first 10 results for your idea.
"""


class IdeasError(ValueError):
    """The file of ideas cannot be written or read."""


@dataclass(frozen=True)
class Project:
    page: str
    name: str
    short_line: str


@dataclass(frozen=True)
class Idea:
    number: int
    page: str
    words: str
    copied: bool  # four words in a row from the name or the short line


def drawn(projects: Sequence[Project], left_out: set[str], seed: int = SEED) -> list[Project]:
    """`DRAWN` projects, at random with a fixed seed, from those not left out."""
    pool = sorted((p for p in projects if p.page not in left_out), key=lambda p: p.page)
    if len(pool) < DRAWN:
        raise IdeasError(f"only {len(pool)} projects to draw from, {DRAWN} needed")
    chance = random.Random(seed)  # noqa: S311 - a draw that must be repeatable, not a secret
    return chance.sample(pool, DRAWN)


def write(folder: Path, projects: Sequence[Project]) -> Path:
    path = folder / FILE
    if path.exists():
        raise IdeasError(f"{path.as_posix()} exists already: the projects are drawn once")
    lines = [HEADER.format(count=len(projects), wanted=WANTED)]
    for number, project in enumerate(projects, start=1):
        lines += [
            f"== {number}",
            f"page: {project.page}",
            f"name: {project.name}",
            f"short line: {project.short_line}",
            "idea:",
            "",
        ]
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def copies(idea: str, source: str, run: int = COPIED_WORDS) -> bool:
    """True when the idea repeats `run` words in a row from the source."""
    words = _words(source)
    runs = {tuple(words[i : i + run]) for i in range(len(words) - run + 1)}
    mine = _words(idea)
    return any(tuple(mine[i : i + run]) in runs for i in range(len(mine) - run + 1))


def read(path: Path) -> list[Idea]:
    """The ideas written in the file, with a flag on each that copies its project."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise IdeasError(f"{path.name} cannot be read") from error
    ideas = []
    for block in re.split(r"^== ", text, flags=re.MULTILINE)[1:]:
        lines = block.splitlines()
        number = int(lines[0].strip())
        fields = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
        words = fields.get("idea", "").strip()
        if not words:
            continue
        source = f"{fields.get('name', '')} {fields.get('short line', '')}"
        ideas.append(Idea(number, fields["page"].strip(), words, copies(words, source)))
    return ideas


def projects_from_the_data() -> list[Project]:
    """Every full card of the local database: its address, name and short line."""
    import psycopg

    from hackathon_memory.parse.project import FULL_CARD
    from hackathon_memory.settings import Settings

    with psycopg.connect(Settings().database_conninfo()) as conn:
        rows = conn.execute(
            "SELECT page_url, name, coalesce(short_line, '') FROM projects WHERE entry_kind = %s",
            (FULL_CARD,),
        ).fetchall()
    return [Project(page, name, short_line) for page, name, short_line in rows]


def main(argv: Sequence[str]) -> int:
    from hackathon_memory.settings import Settings

    if list(argv) not in (["draw"], ["check"]):
        print("usage: python -m evals.test2.ideas draw | check")
        return 2
    folder = Path(Settings().data_dir) / "evals" / "test2"
    try:
        if argv[0] == "draw":
            left_out = set(pages_of(SETS / "tuning.json")) | set(pages_of(SETS / "test1.json"))
            path = write(folder, drawn(projects_from_the_data(), left_out))
            print(f"Written: {path.as_posix()} ({DRAWN} projects; seed {SEED}).")
            return 0
        ideas = read(folder / FILE)
    except IdeasError as error:
        print(f"Stopped: {error}")
        return 1
    copied = [idea.number for idea in ideas if idea.copied]
    print(f"{len(ideas)} idea(s) written, {WANTED} wanted.")
    if copied:
        print(f"These repeat {COPIED_WORDS} words in a row from their project: "
              + ", ".join(str(n) for n in copied))  # fmt: skip
    return 0 if len(ideas) >= WANTED and not copied else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
