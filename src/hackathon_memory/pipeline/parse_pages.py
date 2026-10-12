"""The step that reads the saved pages and keeps what they say (design 6.1).

It sends no request: it works on the pages that a collector saved. It is safe to run again. A
page that was parsed before, by the same parser, is passed over without being opened.

A page that cannot be read does not stop the step. It is named in the run, with the rule that
failed, and the other pages are kept. Two kinds of page are not read: a page that is not built
as the parser expects, and a page whose file no longer has the fingerprint that was written
when it was saved. The second one must never happen (design rule 5), so it is said loudly.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from hackathon_memory.collect.rawstore import RawStore, fingerprint
from hackathon_memory.db.projects import SAME, ProjectStore
from hackathon_memory.db.runs import Run
from hackathon_memory.parse.ethglobal_page import (
    PARSER_VERSION,
    PageShapeChanged,
    read_project_page,
)
from hackathon_memory.parse.event_ends import EventEndsError, read_event_ends
from hackathon_memory.parse.project import ProjectPage
from hackathon_memory.parse.winner_entries import PARSER_VERSION as WINNER_PARSER
from hackathon_memory.parse.winner_entries import (
    WinnerEntriesError,
    entry_files,
    read_entries,
)

STEP = "parse"
EDITED = "the file of the page does not have the fingerprint that was written when it was saved"


def parse_saved_pages(
    raw: RawStore,
    projects: ProjectStore,
    run: Run,
    *,
    limit: int | None = None,
    read: Callable[[bytes, str], ProjectPage] = read_project_page,
    parser: str = PARSER_VERSION,
) -> None:
    """Read every saved page that is not parsed yet, and count what was done in `run`.

    With `limit`, at most that many pages are read, the ones that were saved first.
    """
    already = projects.already_parsed()
    read_now = 0
    for page in sorted(raw.saved(), key=lambda saved: (saved.meta["fetched_at"], saved.url)):
        run.counts["pages"] += 1
        sha256 = page.meta["sha256"]
        if already.get(page.url) == (sha256, parser):
            run.counts[SAME] += 1
            continue
        if limit is not None and read_now >= limit:
            run.counts["left_for_later"] += 1
            continue
        read_now += 1
        body = page.read()
        if fingerprint(body) != sha256:
            run.counts["not_read"] += 1
            run.problem(page.url, EDITED)
            continue
        try:
            project = read(body, page.url)
        except PageShapeChanged as changed:
            # The message of the parser names a rule. It never holds text of the page.
            run.counts["not_read"] += 1
            run.problem(page.url, str(changed))
            continue
        run.counts[projects.save(project, sha256)] += 1
        if project.people_words_hidden:
            run.counts["words_about_people_hidden"] += project.people_words_hidden


def parse_winner_entries(folder: Path, projects: ProjectStore, run: Run) -> None:
    """Keep the winner entries that a person copied by hand into `folder` (design 4.6).

    A record that changed is read again, and one that did not is passed over. A file that
    cannot be read is named in the run, and nothing of it is used.
    """
    already = projects.already_parsed()
    for path in entry_files(folder):
        try:
            entries = read_entries(path)
        except WinnerEntriesError as wrong:
            run.counts["winner_files_not_read"] += 1
            run.problem(path.name, str(wrong))
            continue
        for entry in entries:
            run.counts["winner_entries"] += 1
            if already.get(entry.page.page) == (entry.sha256, WINNER_PARSER):
                run.counts["winner_entries_same"] += 1
                continue
            run.counts["winner_entries_" + projects.save(entry.page, entry.sha256)] += 1


def apply_event_ends(projects: ProjectStore, path: Path, site: str, run: Run) -> None:
    """Write the ends of events that a person typed into `path` (design 7.2).

    A file that cannot be read is named in the run, and nothing of it is used: half a file
    could leave one event with an end and another without one, with no sign of it.
    """
    try:
        ends = read_event_ends(path)
    except EventEndsError as wrong:
        run.counts["event_ends_not_read"] += 1
        run.problem("the ends of events typed by hand", str(wrong))
        return
    done = projects.set_event_ends(site, ends)
    for key, value in (
        ("event_ends_written", done.written),
        ("event_ends_same", done.same),
        ("events_without_an_end", done.without_end),
    ):
        if value:
            run.counts[key] += value
    for slug in done.unknown:
        run.problem(f"{path.name}: {slug}", "no saved project names this event")
    for slug in done.before_start:
        run.problem(f"{path.name}: {slug}", "the last day is before the start of the event")
