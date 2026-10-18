"""The sheet of Test 3 (design 13.4): the texts of each page of the set, for the check by hand.

    python -m evals.test3.sheet          writes the sheet into data/evals/test3, once

The sheet shows the text that the tool read: the page (its name, its short line, its texts and
its links) and the README of its code, both with the words about people taken out. Under each
text it lists every string with the shape of a Hedera ID, caught by a net wider than the parser's:
any three numbers joined by dots, with what follows a transaction, any address of the EVM kind,
and any link to HashScan. The net helps the eye; it decides nothing.

The person reads each page and its README, and writes the IDs of the project into answers.json,
as guideline.md says. The folder holds the texts of the pages, so it stays out of git (design
13.1). A sheet is never written over: to start again, delete the folder.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg

from evals.sets import TEST3, pages_of
from hackathon_memory.collect import github
from hackathon_memory.collect.github_readmes import FOUND, saved_readme
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.settings import Settings

# The wide net: three numbers with dots (and what follows a transaction), an EVM address, a link
# to HashScan.
NET = re.compile(
    r"(?<![\w.])\d+\.\d+\.\d+(?:@\d+\.\d+|-\d+-\d+)?(?![\w.]*\d)"
    r"|0x[0-9a-fA-F]{40}"
    r"|https?://(?:www\.)?hashscan\.io/[^\s)\]\"'<>]+"
)
AROUND = 90  # letters shown on each side of a string


def caught(text: str) -> list[dict]:
    """Each string of the net, with the words around it on one line."""
    found = []
    for match in NET.finditer(text):
        start, end = max(0, match.start() - AROUND), min(len(text), match.end() + AROUND)
        found.append({"string": match.group(0), "around": " ".join(text[start:end].split())})
    return found


def page_texts(conninfo: str, page: str) -> tuple[int, str, str | None] | None:
    """The project of a page: its number, the text that the tool read, and its repository."""
    with psycopg.connect(conninfo) as conn:
        row = conn.execute(
            "SELECT p.id, p.name, coalesce(p.short_line, ''), r.url FROM projects p "
            "LEFT JOIN repositories r ON r.id = p.repository_id WHERE p.page_url = %s", (page,)
        ).fetchone()  # fmt: skip
        if row is None:
            return None
        pid, name, short, repository = row
        sections = conn.execute(
            "SELECT title, body FROM sections WHERE project_id = %s ORDER BY position", (pid,)
        ).fetchall()
        links = conn.execute(
            "SELECT label, url FROM links WHERE project_id = %s ORDER BY position", (pid,)
        ).fetchall()
    parts = [name, short] + [f"{title}\n{body}" for title, body in sections]
    parts.append("Links:\n" + "\n".join(f"{label}: {url}" for label, url in links))
    return pid, "\n\n".join(part for part in parts if part.strip()), repository


def make(settings: Settings, folder: Path) -> int:
    """Write sheet.md and answers.json for the pages of Test 3. Returns how many pages."""
    if folder.exists():
        raise SystemExit(f"{folder} exists already: a sheet is never written over")
    conninfo = settings.database_conninfo()
    readmes = RawStore(github.raw_dir(settings))
    lines, answers = ["# Test 3: the pages to check by hand", ""], []
    for number, page in enumerate(pages_of(TEST3), start=1):
        found = page_texts(conninfo, page)
        if found is None:
            raise SystemExit(f"no project for {page}: the database is not the one of the draw")
        pid, text, repository = found
        readme = saved_readme(readmes, repository) if repository else None
        readme_text = readme.text if readme is not None and readme.status == FOUND else ""
        lines += [f"## {number}. {page}", f"Project {pid}. Repository: {repository or 'none'}", ""]
        for where, body in (("page", text), ("readme", readme_text)):
            lines += [f"### The {where}", "", "```text", body or "(nothing)", "```", ""]
            lines += [f"Caught by the net in the {where}:"] + [
                f"- [net] `{one['string']}`: {one['around']}" for one in caught(body)
            ] + [""]  # fmt: skip
        answers.append({"page": page, "project": pid, "ids": [], "checked": False})
    folder.mkdir(parents=True)
    (folder / "sheet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "answers.json").write_text(json.dumps(answers, indent=1) + "\n", encoding="utf-8")
    return len(answers)


def main(argv: Sequence[str]) -> int:
    del argv
    settings = Settings()
    folder = Path(settings.data_dir) / "evals" / "test3"
    count = make(settings, folder)
    print(f"Written: {folder.as_posix()}/sheet.md and answers.json, for {count} pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
