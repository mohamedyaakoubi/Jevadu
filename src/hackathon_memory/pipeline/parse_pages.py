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

from hackathon_memory.collect.rawstore import RawStore, fingerprint
from hackathon_memory.db.projects import SAME, ProjectStore
from hackathon_memory.db.runs import Run
from hackathon_memory.parse.ethglobal_page import (
    PARSER_VERSION,
    PageShapeChanged,
    read_project_page,
)
from hackathon_memory.parse.project import ProjectPage

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
