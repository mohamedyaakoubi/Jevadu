"""Command line for the steps of the path.

    python -m hackathon_memory.pipeline parse              read every saved page that is new
    python -m hackathon_memory.pipeline parse --limit 50   read at most 50, the first ones saved
    python -m hackathon_memory.pipeline readmes            ask GitHub for the missing READMEs,
                                                           then read every saved one
    python -m hackathon_memory.pipeline readmes --repos 5  ask for at most 5 new READMEs
    python -m hackathon_memory.pipeline readmes --no-requests    read the saved ones only
    python -m hackathon_memory.pipeline code               the facts of each repository, in
                                                           the same way (same options)
    python -m hackathon_memory.pipeline check              check the Hedera ids on the ledger
    python -m hackathon_memory.pipeline check --max-age-days 0   ask the ledger about every id again
    python -m hackathon_memory.pipeline embed              make the embedding of every project
                                                           whose text changed (it costs money)
    python -m hackathon_memory.pipeline all                parse, readmes, code, check and
                                                           embed, in this order
    python -m hackathon_memory.pipeline cards --set evals/sets/tuning.json
                                                           the cards of the LLM for the pages
                                                           of a set (it costs money)
    python -m hackathon_memory.pipeline cards --export FILE   write every card to a file
    python -m hackathon_memory.pipeline cards --restore FILE  put the cards of a file back, for a
                                                           database built again (no model)

"parse" sends no request: it works on the pages that are saved, and on the winner entries that a
person copied by hand into data/by-hand (design 4.6). It also writes the last day of
each event that a person typed into data/by-hand/ethglobal.com/event-ends.txt, because the proof
rule needs it and no page gives it (design 7.2). "readmes" and "code" ask GitHub's API, which the
maintainer allowed, and only when the switch COLLECT_GITHUB is on in .env; --wait lets it wait
for the end of a cooldown (design 7.3). "check" asks the Hedera mirror node, a public API made
for programs, and no site (design rule 17). "embed" calls Google's embedding model through the
meter and its budget (design 11.4). "cards" calls the REWRITE layer of Gemini, through the meter
too, for the pages of a set only: it is not part of "all" (design 6.2, open question Q29).

A step prints numbers. For a page or an id that it could not handle it prints the address or
the id and the rule that failed. It never prints text of a page, and never the connection text
of the database.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import psycopg

from hackathon_memory import __version__
from hackathon_memory.check import proof
from hackathon_memory.collect import github
from hackathon_memory.collect.ethglobal import data_paths
from hackathon_memory.collect.ethglobal_site import SITE
from hackathon_memory.collect.github_facts import fetch_facts
from hackathon_memory.collect.github_once import AnswersRun
from hackathon_memory.collect.github_readmes import fetch_readmes
from hackathon_memory.collect.polite import CollectorRefused
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.cards import CardStore
from hackathon_memory.db.embeddings import EmbeddingStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.projects import CHANGED, NEW, SAME, ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import Run, recorded_run
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.finops.meter import metered_client
from hackathon_memory.hedera.mirror import MIRROR_URLS, MirrorNode
from hackathon_memory.llm.client import GoogleSetupError
from hackathon_memory.parse import event_ends, event_years
from hackathon_memory.pipeline import check_ids, code, embed, parse_pages, readmes
from hackathon_memory.read import cards as card_step
from hackathon_memory.read import restore
from hackathon_memory.read.sets import SetError, pages_of
from hackathon_memory.settings import Settings, SettingsError

USAGE = (
    "usage: python -m hackathon_memory.pipeline parse [--limit N]\n"
    "       python -m hackathon_memory.pipeline readmes [--repos N | --no-requests] [--wait]\n"
    "       python -m hackathon_memory.pipeline code [--repos N | --no-requests] [--wait]\n"
    "       python -m hackathon_memory.pipeline check [--max-age-days N]\n"
    "       python -m hackathon_memory.pipeline embed [--limit N]\n"
    "       python -m hackathon_memory.pipeline all [the options of the steps]\n"
    "       python -m hackathon_memory.pipeline cards --set FILE [--limit N]"
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


# The whole path, in its order (design 14.3: one command processes the projects).
ALL = "all"
ALL_STEPS = (parse_pages.STEP, readmes.STEP, code.STEP, check_ids.STEP, embed.STEP)


class _Quiet(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse would exit; the caller prints the usage
        raise ValueError(message)


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = _Quiet(prog="python -m hackathon_memory.pipeline", add_help=False)
    parser.add_argument("step", choices=[*ALL_STEPS, card_step.STEP, ALL])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-age-days", type=float)
    parser.add_argument("--repos", type=int)
    parser.add_argument("--no-requests", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--set", dest="set_file")
    parser.add_argument("--export", dest="export_file")
    parser.add_argument("--restore", dest="restore_file")
    arguments = parser.parse_args(argv)
    every = arguments.step == ALL  # the options of every step go with it
    is_parse = every or arguments.step == parse_pages.STEP
    is_check = every or arguments.step == check_ids.STEP
    is_readmes = every or arguments.step in (readmes.STEP, code.STEP)  # the steps of GitHub
    is_embed = every or arguments.step == embed.STEP
    is_cards = arguments.step == card_step.STEP
    sources = [arguments.set_file, arguments.export_file, arguments.restore_file]
    if is_cards != (sum(one is not None for one in sources) == 1) or (
        not is_cards and any(one is not None for one in sources)
    ):
        raise ValueError(
            "cards needs --set (the file of a set of pages), or --export or --restore (a file "
            "of cards), only one of them, and these go with cards only"
        )
    if arguments.limit is not None and (arguments.export_file or arguments.restore_file):
        raise ValueError("--limit goes with --set, not with --export or --restore")
    limited = is_parse or is_embed or is_cards
    if arguments.limit is not None and (not limited or arguments.limit < 1):
        raise ValueError("--limit goes with parse, embed or cards, and must be 1 or more")
    if arguments.max_age_days is not None and (not is_check or arguments.max_age_days < 0):
        raise ValueError("--max-age-days goes with check, and must be 0 or more")
    if arguments.repos is not None and (not is_readmes or arguments.repos < 1):
        raise ValueError("--repos goes with readmes or code, and must be 1 or more")
    if (arguments.no_requests or arguments.wait) and not is_readmes:
        raise ValueError("--no-requests and --wait go with readmes or code")
    if arguments.no_requests and (arguments.repos is not None or arguments.wait):
        raise ValueError("--no-requests sends nothing, so --repos and --wait do not go with it")
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
    if counts["winner_entries"] or counts["winner_files_not_read"]:
        lines.append(
            f"Winner entries, copied by hand or read from a saved winners page: "
            f"{counts['winner_entries']}. New: "
            f"{counts['winner_entries_new']}. Read again: {counts['winner_entries_changed']}. "
            f"The same as before: {counts['winner_entries_same']}. Files not read: "
            f"{counts['winner_files_not_read']}."
        )
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
    if counts["event_years_written"]:
        lines.append(f"Years of events typed by hand: {counts['event_years_written']} written.")
    if counts["event_days_written"]:
        lines.append(f"Days of events typed by hand: {counts['event_days_written']} written.")
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


def _github_fetch(
    settings: Settings,
    arguments: argparse.Namespace,
    run: Run,
    ask: Callable[..., AnswersRun],
) -> tuple[Callable[[list[str]], AnswersRun] | None, str | None]:
    """What asks GitHub for the missing answers with `ask` (the READMEs or the facts), or None
    with the reason in plain words."""
    if arguments.no_requests:
        return None, None
    if not settings.collect_github:
        return None, "COLLECT_GITHUB is off in .env, so nothing was asked of GitHub."
    try:
        client = github.github_client(settings, wait_for_cooldown=arguments.wait)
    except CollectorRefused as refused:
        run.problem("GitHub", str(refused))
        return None, "Nothing was asked of GitHub (see below)."
    store = RawStore(github.raw_dir(settings))
    collector = f"{settings.collector_name.strip()}/{__version__}"

    def fetch(wanted: list[str]) -> AnswersRun:
        return ask(client, store, wanted, collector=collector, limit=arguments.repos)

    return fetch, None


def _problem_lines(run: Run, title: str) -> list[str]:
    lines = []
    if run.problems:
        lines.append(title)
        lines.extend(f"  {problem['what']}: {problem['rule']}" for problem in run.problems)
        if run.problems_left_out:
            lines.append(f"  ... and {run.problems_left_out} more")
    lines.append(f"This is run {run.id} in the table of runs.")
    return lines


@dataclass
class _Services:
    """What the steps need from outside. A test hands in stand-ins."""

    mirrors: Mapping[str, MirrorNode] | None = None
    google: object = None


def _run_step(
    step: str,
    arguments: argparse.Namespace,
    settings: Settings,
    conninfo: str,
    services: _Services,
) -> tuple[Run, list[str]]:
    """Run one step in its own row of the table of runs. Returns the run and its lines."""
    note: str | None = None
    with recorded_run(conninfo, step) as run:
        if step == parse_pages.STEP:
            paths = data_paths(settings)
            projects = ProjectStore(conninfo)
            parse_pages.parse_saved_pages(
                RawStore(paths.raw_dir), projects, run, limit=arguments.limit
            )
            # The winner entries: copied by hand into the folder of what a person typed, or read
            # from a saved winners page in the folder of saved pages.
            parse_pages.parse_winner_entries(
                paths.page_list.parent.parent, projects, run, saved=paths.raw_dir.parent
            )
            ends = paths.page_list.with_name(event_ends.FILE_NAME)  # typed by hand
            parse_pages.apply_event_ends(projects, ends, SITE, run)
            years = paths.page_list.parent.parent / event_years.FILE_NAME  # typed by hand
            parse_pages.apply_event_years(projects, years, run)
        elif step == readmes.STEP:
            fetch, note = _github_fetch(settings, arguments, run, fetch_readmes)
            readmes.read_readmes(
                RepositoryStore(conninfo),
                ProjectStore(conninfo),
                RawStore(github.raw_dir(settings)),
                run,
                fetch=fetch,
            )
        elif step == code.STEP:
            fetch, note = _github_fetch(settings, arguments, run, fetch_facts)
            code.read_code(
                RepositoryStore(conninfo), RawStore(github.raw_dir(settings)), run, fetch=fetch
            )
        elif step == card_step.STEP and arguments.export_file:
            run.counts["cards_written"] = restore.export_cards(
                conninfo, Path(arguments.export_file)
            )
        elif step == card_step.STEP and arguments.restore_file:
            saved = restore.read_saved(Path(arguments.restore_file))
            restore.restore_cards(CardStore(conninfo), saved, run)
        elif step == card_step.STEP:
            pages = pages_of(Path(arguments.set_file))  # a wrong set stops before Google
            google = services.google
            if google is None:
                google = metered_client(settings, "rewrite", run_id=f"pipeline-run-{run.id}")
            card_step.make_cards(
                CardStore(conninfo),
                google,
                run,
                pages=pages,
                model=settings.gemini_rewrite_model,
                thinking_level=settings.gemini_rewrite_thinking_level,
                limit=arguments.limit,
            )
        elif step == embed.STEP:
            google = services.google
            if google is None:
                google = metered_client(settings, "embed_document", run_id=f"pipeline-run-{run.id}")
            embed.embed_pages(
                EmbeddingStore(conninfo),
                google,
                run,
                model=settings.gemini_embedding_model,
                limit=arguments.limit,
            )
        else:
            mirrors = services.mirrors
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
    if step == parse_pages.STEP:
        lines = parse_lines(run)
    elif step == readmes.STEP:
        lines = readmes.readme_lines(run) + ([note] if note else [])
        lines += _problem_lines(run, "Stopped or not done, and why:")
    elif step == code.STEP:
        lines = code.code_lines(run) + ([note] if note else [])
        lines += _problem_lines(run, "Stopped or not done, and why:")
    elif step == embed.STEP:
        lines = embed.embed_lines(run) + _problem_lines(run, "Not made, with what went wrong:")
    elif step == card_step.STEP and arguments.export_file:
        lines = [f"Cards written to {arguments.export_file}: {run.counts['cards_written']}."]
    elif step == card_step.STEP and arguments.restore_file:
        lines = restore.restore_lines(run) + _problem_lines(run, "Not put back, and why:")
    elif step == card_step.STEP:
        lines = card_step.cards_lines(run) + _problem_lines(run, "Not made, with what went wrong:")
    else:
        lines = check_lines(run)
    return run, lines


def main(
    argv: list[str],
    settings: Settings | None = None,
    mirrors: Mapping[str, MirrorNode] | None = None,
    google: object = None,
) -> int:
    try:
        arguments = _arguments(argv)
    except ValueError as problem:
        print(f"{problem}\n{USAGE}")
        return 2
    settings = settings or Settings()
    steps = ALL_STEPS if arguments.step == ALL else (arguments.step,)
    problems = False
    try:
        conninfo = settings.database_conninfo()
        for step in steps:
            run, lines = _run_step(step, arguments, settings, conninfo, _Services(mirrors, google))
            if len(steps) > 1:
                print(f"== {step} ==")
            print("\n".join(lines), flush=True)  # each step as soon as it is done
            problems = problems or bool(run.problems)
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
    except embed.GoogleIsAway as away:
        print(f"Stopped: {away}. What was made is kept. Try again later.")
        return 1
    except BudgetExceeded as over:
        print(f"Stopped by the budget: {over}")
        return 1
    except (GoogleSetupError, SetError) as problem:
        print(f"Stopped: {problem}")
        return 1
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
