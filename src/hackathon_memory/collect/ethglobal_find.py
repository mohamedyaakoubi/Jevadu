"""Find the projects that ETHGlobal's showcase ties to Hedera.

    python -m hackathon_memory.collect ethglobal --find

Why. The showcase has a list with the filter "partner: Hedera". It names every project that is
tied to Hedera, and the data of that list says, for each project, which sponsors gave it a
prize. No other page of the site lists the Hedera projects or the winners of the Hedera prizes.
So this walk reads the pages of that list, one after the other, and writes down each project.
Then a run reads the pages of these projects.

What it does, by the rules of design 5.7:

* It reads robots.txt, then the pages of the list in order: page 1, then the page that page 1
  links to, and so on to the last one. It follows no other link.
* The same polite client as the run: one request at a time, two seconds apart, the name of the
  tool and the maintainer's address in each one, and every request counted in the limit of the
  site.
* No page of the list is saved. From each page it keeps, for each project, the address, the
  event and the sponsor ids of its prizes (ethglobal_found.py). The row that two pages share is
  taken once.
* It stops at the first refusal, at a page that is not shaped as expected, and at the limit of
  requests. Nothing is tried again and nothing is worked around.
* It writes what it found after every page. When it is started again, it goes on at the next
  page, and when the last page was reached it sends no request at all.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from hackathon_memory.collect.ethglobal import (
    data_paths,
    identity_if_allowed,
    is_allowed_url,
    load_robots,
    polite_client,
)
from hackathon_memory.collect.ethglobal_found import FoundList, load_found, save_found
from hackathon_memory.collect.ethglobal_list import (
    MAX_LIST_PAGE,
    ListShapeChanged,
    is_list_url,
    list_url,
    read_list_page,
)
from hackathon_memory.collect.ethglobal_site import SITE
from hackathon_memory.collect.polite import (
    CollectorRefused,
    FetchFailed,
    PoliteClient,
    StopCollecting,
)
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.settings import Settings


@dataclass
class WalkSummary:
    site: str = SITE
    started_at: str = ""
    finished_at: str = ""
    first_page: int = 0  # the first page of the list that this walk asked for
    pages_read: int = 0  # in this walk
    projects_listed: int = 0  # in this walk
    projects_with_prize: int = 0  # in this walk
    complete: bool = False  # the last page of the list was reached, now or earlier
    requests_made: int = 0
    stopped: str | None = None


class ListWalker:
    def __init__(
        self,
        *,
        client: PoliteClient,
        store: RawStore,
        found_path: Path,
        runs_dir: Path,
        max_pages: int | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        if max_pages is not None and max_pages < 1:
            raise CollectorRefused("The number of pages to read must be 1 or more.")
        self.client = client
        self.store = store
        self.found_path = found_path
        self.runs_dir = runs_dir
        self.max_pages = max_pages
        self.log = log

    def run(self) -> WalkSummary:
        now = _now()
        found = load_found(self.found_path) or FoundList(started_at=now)
        summary = WalkSummary(started_at=now, first_page=found.pages_read + 1)
        try:
            if not found.complete:
                self._walk(found, summary)
        except StopCollecting as stop:
            summary.stopped = str(stop)
            self.log(f"STOPPED: {stop}")
        finally:
            summary.finished_at = _now()
            summary.complete = found.complete
            summary.requests_made = self.client.requests_made
            self._write_record(summary)
        return summary

    def _walk(self, found: FoundList, summary: WalkSummary) -> None:
        rules = load_robots(self.client, self.store)
        agent = self.client.identity.name
        while not found.complete:
            if self.max_pages is not None and summary.pages_read >= self.max_pages:
                return
            number = found.pages_read + 1
            if number > MAX_LIST_PAGE:
                raise StopCollecting(f"The list has more than {MAX_LIST_PAGE} pages. Stopped.")
            url = list_url(number)
            if not rules.allows(agent, url):
                raise StopCollecting(f"robots.txt of {SITE} does not allow this tool to read {url}")
            try:
                fetched = self.client.get(url)
            except FetchFailed as error:
                raise StopCollecting(
                    f"Page {number} of the list could not be read: {error}. "
                    "Start the command again to go on from this page."
                ) from None
            if fetched.status != 200:
                raise StopCollecting(f"Page {number} of the list answered {fetched.status}.")
            try:
                page = read_list_page(fetched.body)
            except ListShapeChanged as change:
                raise StopCollecting(
                    f"Page {number} of the list is not shaped as expected: {change}."
                ) from None
            if page.number != number:
                raise StopCollecting(
                    f"The site answered with page {page.number} of the list when page {number} "
                    "was asked for."
                )
            new_rows = found.add(page, _now())
            save_found(self.found_path, found)
            with_prize = sum(1 for row in new_rows if row.sponsors)
            summary.pages_read += 1
            summary.projects_listed += len(new_rows)
            summary.projects_with_prize += with_prize
            self.log(
                f"page {number}: {len(new_rows)} new projects, {with_prize} with a prize"
                + ("" if page.has_next else " (the last page)")
            )

    def _write_record(self, summary: WalkSummary) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = summary.started_at.replace("-", "").replace(":", "")
        path = self.runs_dir / f"{stamp}-ethglobal-list.json"
        path.write_text(
            json.dumps(asdict(summary), indent=2) + "\n", encoding="utf-8", newline="\n"
        )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_walker(
    settings: Settings,
    *,
    max_pages: int | None = None,
    env_file: Path | None = None,
    **client_options: object,
) -> ListWalker:
    """Everything a walk needs. Refuses (CollectorRefused) when a promise cannot be kept."""
    identity = identity_if_allowed(settings)
    paths = data_paths(settings)
    load_found(paths.found_list)  # a file that cannot be read refuses the walk before a request
    client = polite_client(
        identity,
        lambda url: is_list_url(url) or is_allowed_url(url, ()),  # the list, and robots.txt
        paths,
        env_file=env_file,
        **client_options,
    )
    return ListWalker(
        client=client,
        store=RawStore(paths.raw_dir),
        found_path=paths.found_list,
        runs_dir=paths.runs_dir,
        max_pages=max_pages,
    )


def walk_plan(settings: Settings) -> list[str]:
    """What a walk would read, and what the last one found. Makes no request."""
    paths = data_paths(settings)
    lines = [
        "A walk (--find) reads the Hedera list of the showcase, page by page, and saves no page:",
        f"  {list_url(1)}",
        "  then the page that each page links to, until the last one. 33 projects for each page.",
    ]
    try:
        found = load_found(paths.found_list)
    except CollectorRefused as refusal:
        lines.append(f"  {refusal}")
        return lines
    if found is None:
        lines.append("  No walk was made yet. The first one starts at page 1.")
        return lines
    lines.append(
        f"  Read so far: {found.pages_read} page(s), {found.listed} projects, "
        f"{len(found.with_prize)} of them with a prize of some sponsor."
    )
    if found.page_ends_not_shared:
        lines.append(
            f"  At {found.page_ends_not_shared} page end(s) the next page did not start with "
            "the same row: the list may have moved while it was read, and a row may be missing."
        )
    lines.append(
        "  The last page of the list was reached. A new walk sends no request."
        if found.complete
        else f"  The end of the list is not reached. The next walk starts at page "
        f"{found.pages_read + 1}."
    )
    return lines
