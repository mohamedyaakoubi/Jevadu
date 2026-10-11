"""Command line for the steps of the path.

    python -m hackathon_memory.pipeline parse              read every saved page that is new
    python -m hackathon_memory.pipeline parse --limit 50   read at most 50, the first ones saved
    python -m hackathon_memory.pipeline check              check the Hedera ids on the ledger
    python -m hackathon_memory.pipeline check --max-age-days 0   ask the ledger about every id again

"parse" sends no request: it works on the pages that are saved. It also writes the last day of
each event that a person typed into data/by-hand/ethglobal.com/event-ends.txt, because the proof
rule needs it and no page gives it (design 7.2). "check" asks the Hedera mirror node, a public API
made for programs, and no site (design rule 17).

A step prints numbers. For a page or an id that it could not handle it prints the address or
the id and the rule that failed. It never prints text of a page, and never the connection text
of the database.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from datetime import timedelta

import psycopg

from hackathon_memory.check import proof
from hackathon_memory.collect.ethglobal import data_paths
from hackathon_memory.collect.ethglobal_site import SITE
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.projects import CHANGED, NEW, SAME, ProjectStore
from hackathon_memory.db.runs import Run, recorded_run
from hackathon_memory.hedera.mirror import MIRROR_URLS, MirrorNode
from hackathon_memory.parse import event_ends
from hackathon_memory.pipeline import check_ids, parse_pages
from hackathon_memory.settings import Settings, SettingsError

USAGE = (
    "usage: python -m hackathon_memory.pipeline parse [--limit N]\n"
    "       python -m hackathon_memory.pipeline check [--max-age-days N]"
)
# What each status of the proof rule means, in plain words (design 7.2).
STATUS_WORDS = {
    proof.PROOF_FOUND: "proof found",
    proof.WINDOW_NOT_KNOWN: "found, and the end of the event is not typed in yet",
    proof.DATES_DO_NOT_FIT: "found, but the dates do not fit",
    proof.FOUND_BUT_EMPTY: "found, but empty",
    proof.ANOTHER_KIND: "found, but as another kind of thing than the page says",
    proof.CANNOT_BE_CHECKED: "cannot be checked",
    proof.NOT_FOUND: "not found",
    proof.NO_ID_GIVEN: "no id given",
}


class _Quiet(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse would exit; the caller prints the usage
        raise ValueError(message)


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = _Quiet(prog="python -m hackathon_memory.pipeline", add_help=False)
    parser.add_argument("step", choices=[parse_pages.STEP, check_ids.STEP])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-age-days", type=float)
    arguments = parser.parse_args(argv)
    is_parse = arguments.step == parse_pages.STEP
    if arguments.limit is not None and (not is_parse or arguments.limit < 1):
        raise ValueError("--limit goes with parse, and must be 1 or more")
    if arguments.max_age_days is not None and (is_parse or arguments.max_age_days < 0):
        raise ValueError("--max-age-days goes with check, and must be 0 or more")
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
    if counts["words_about_people_hidden"]:
        lines.append(
            "Handles, addresses and profile links that were hidden in the texts and the links: "
            f"{counts['words_about_people_hidden']}."
        )
    if counts["event_ends_written"] or counts["event_ends_same"] or counts["events_without_an_end"]:
        lines.append(
            f"Ends of events typed by hand: {counts['event_ends_written']} written, "
            f"{counts['event_ends_same']} the same as before. "
            f"Events with no end yet: {counts['events_without_an_end']}."
        )
    return lines + _problem_lines(run, "Not used, and why:")


def check_lines(run: Run) -> list[str]:
    """What a run of the check step did, in plain words."""
    counts = run.counts
    lines = [
        f"Answers of the mirror node: {counts['answers_from_the_node']} new, "
        f"{counts['answers_from_the_table']} from the table. Requests: {counts['requests']}. "
        f"Looks inside a window: {counts['looks_inside_a_window']}."
    ]
    for title, prefix in (("Ids, on each network that was asked", "id_"), ("Projects", "project_")):
        lines.append(f"{title}:")
        lines.extend(
            f"  {counts[prefix + status]:5}  {words}"
            for status, words in STATUS_WORDS.items()
            if counts[prefix + status]
        )
    lines.append(f"  {counts['projects_with_no_id']:5}  {STATUS_WORDS[proof.NO_ID_GIVEN]}")
    if counts["projects_not_finished"]:
        lines.append(f"  {counts['projects_not_finished']:5}  not finished: see below")
    return lines + _problem_lines(run, "Not checked, with what went wrong:")


def _problem_lines(run: Run, title: str) -> list[str]:
    lines = []
    if run.problems:
        lines.append(title)
        lines.extend(f"  {problem['what']}: {problem['rule']}" for problem in run.problems)
        if run.problems_left_out:
            lines.append(f"  ... and {run.problems_left_out} more")
    lines.append(f"This is run {run.id} in the table of runs.")
    return lines


def main(
    argv: list[str],
    settings: Settings | None = None,
    mirrors: Mapping[str, MirrorNode] | None = None,
) -> int:
    try:
        arguments = _arguments(argv)
    except ValueError as problem:
        print(f"{problem}\n{USAGE}")
        return 2
    settings = settings or Settings()
    try:
        conninfo = settings.database_conninfo()
        with recorded_run(conninfo, arguments.step) as run:
            if arguments.step == parse_pages.STEP:
                paths = data_paths(settings)
                projects = ProjectStore(conninfo)
                parse_pages.parse_saved_pages(
                    RawStore(paths.raw_dir), projects, run, limit=arguments.limit
                )
                ends = paths.page_list.with_name(event_ends.FILE_NAME)  # typed by hand
                parse_pages.apply_event_ends(projects, ends, SITE, run)
            else:
                if mirrors is None:
                    # Every network that a page can name. An id with no network is asked on
                    # the ones of check_ids.NETWORKS_WHEN_OPEN only.
                    mirrors = {name: MirrorNode(name) for name in MIRROR_URLS}
                days = arguments.max_age_days
                check_ids.check_ids(
                    LedgerStore(conninfo),
                    mirrors,
                    run,
                    max_age=check_ids.MAX_AGE if days is None else timedelta(days=days),
                )
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
    except check_ids.NodeIsAway as away:
        print(f"Stopped: {away}. Nothing more was asked. Try again later.")
        return 1
    lines = parse_lines(run) if arguments.step == parse_pages.STEP else check_lines(run)
    print("\n".join(lines))
    return 1 if run.problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
