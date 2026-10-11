"""Command line for the steps of the path.

    python -m hackathon_memory.pipeline parse              read every saved page that is new
    python -m hackathon_memory.pipeline parse --limit 50   read at most 50, the first ones saved

A step sends no request to a site: it works on the pages that are saved. It prints numbers, and
for a page that it could not read the address and the rule that failed. It never prints text of
a page, and never the connection text of the database.
"""

from __future__ import annotations

import argparse
import sys

import psycopg

from hackathon_memory.collect.ethglobal import data_paths
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.projects import CHANGED, NEW, SAME, ProjectStore
from hackathon_memory.db.runs import Run, recorded_run
from hackathon_memory.pipeline.parse_pages import STEP, parse_saved_pages
from hackathon_memory.settings import Settings, SettingsError

USAGE = "usage: python -m hackathon_memory.pipeline parse [--limit N]"


class _Quiet(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse would exit; the caller prints the usage
        raise ValueError(message)


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = _Quiet(prog="python -m hackathon_memory.pipeline", add_help=False)
    parser.add_argument("step", choices=[STEP])
    parser.add_argument("--limit", type=int)
    arguments = parser.parse_args(argv)
    if arguments.limit is not None and arguments.limit < 1:
        raise ValueError("--limit must be 1 or more")
    return arguments


def parse_lines(run: Run) -> list[str]:
    """What a run of the parse step did, in plain words."""
    counts = run.counts
    lines = [
        f"Saved pages: {counts['pages']}. New: {counts[NEW]}. Read again because the page or "
        f"the parser changed: {counts[CHANGED]}. The same as before: {counts[SAME]}. "
        f"Not read: {counts['not_read']}."
    ]
    if counts["left_for_later"]:
        lines.append(f"Left for a later run, because of the limit: {counts['left_for_later']}.")
    if run.problems:
        lines.append("Not read, with the rule that failed:")
        lines.extend(f"  {problem['what']}: {problem['rule']}" for problem in run.problems)
        if run.problems_left_out:
            lines.append(f"  ... and {run.problems_left_out} more")
    lines.append(f"This is run {run.id} in the table of runs.")
    return lines


def main(argv: list[str], settings: Settings | None = None) -> int:
    try:
        arguments = _arguments(argv)
    except ValueError as problem:
        print(f"{problem}\n{USAGE}")
        return 2
    settings = settings or Settings()
    try:
        conninfo = settings.database_conninfo()
        raw = RawStore(data_paths(settings).raw_dir)
        with recorded_run(conninfo, STEP) as run:
            parse_saved_pages(raw, ProjectStore(conninfo), run, limit=arguments.limit)
    except SettingsError as problem:
        print(f"Stopped: {problem}")
        return 1
    except psycopg.errors.UndefinedTable:
        print("Stopped: the tables do not exist yet. Run: python -m hackathon_memory.db migrate")
        return 1
    except psycopg.OperationalError:
        # The message of this error can hold the connection text, so it is not shown.
        print("Stopped: cannot reach the database. Is it running? (docker compose up -d db)")
        return 1
    print("\n".join(parse_lines(run)))
    return 1 if run.counts["not_read"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
