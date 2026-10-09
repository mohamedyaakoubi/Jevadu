"""A quick look at ETHGlobal: at most three requests, nothing saved, no person printed.

    python -m hackathon_memory.collect ethglobal --look

Why. To write the page shape (design 5.7), someone must see the structure of a real prize page
and of a real project page. The other way is that the maintainer saves two pages by hand from a browser (README.md, step 9b). This is the way that needs no manual work. It also
answers the question that matters most, early: does ETHGlobal accept an honest request at all?
If its server refuses, nothing is worked around (design rule 10).

What it does, inside the promises of design 5.7:

* robots.txt, then the FIRST prize page of the maintainer's list, then the FIRST project page that this
  prize page links to. Three requests at most, two seconds apart, with the name of the tool and the
  maintainer's address in each one. Never any other page.
* It prints the SHAPE of the two pages with the skeleton printer: every text only as its length,
  no heading except plain section words, no name, no link target except its shape. Nothing is saved
  to disk. The pages stay in memory and are gone when the command ends.

It still needs the maintainer's yes for these three pages (design rule 17), the switch
COLLECT_ETHGLOBAL=on, the contact address and the list of prize pages.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from hackathon_memory.collect.ethglobal import (
    ROBOTS_URL,
    SITE,
    data_paths,
    extract_project_links,
    is_allowed_url,
    load_prize_pages,
)
from hackathon_memory.collect.polite import (
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    FetchResult,
    PoliteClient,
    StopCollecting,
)
from hackathon_memory.collect.robots import RobotsRules
from hackathon_memory.collect.skeleton import path_shape, skeleton
from hackathon_memory.settings import Settings

LOOK_REQUESTS = 3  # robots.txt, one prize page, one project page


@dataclass
class LookReport:
    lines: list[str] = field(default_factory=list)
    requests_made: int = 0
    stopped: str | None = None


class Looker:
    def __init__(
        self,
        client: PoliteClient,
        prize_page: str,
        log: Callable[[str], None] = print,
    ) -> None:
        self.client = client
        self.prize_page = prize_page
        self.log = log

    def run(self) -> LookReport:
        report = LookReport()
        say = report.lines.append
        try:
            rules = self._robots(report)
            agent = self.client.identity.name

            if not rules.allows(agent, self.prize_page):
                raise StopCollecting(
                    f"robots.txt of {SITE} does not allow this tool to read the prize page"
                )
            prize = self._get(self.prize_page, report)
            if prize is None:
                return self._finish(report)
            self._describe("prize page", prize, report)

            links = extract_project_links(prize.body, self.prize_page, "a[href]")
            say(f"Links on the prize page that go to a showcase project: {len(links)}")
            shapes = Counter(path_shape(link) for link in links)
            for shape, count in shapes.most_common(3):
                say(f"  {count:3}  {shape}")
            if not links:
                say(
                    "No project link was found, so no project page is read. "
                    "The shape of the prize page must be studied first."
                )
                return self._finish(report)

            project_url = links[0]
            if not rules.allows(agent, project_url):
                raise StopCollecting(
                    f"robots.txt of {SITE} does not allow this tool to read the project page"
                )
            project = self._get(project_url, report)
            if project is None:
                return self._finish(report)
            say(f"First project page read: {project_url}")
            self._describe("project page", project, report)
        except StopCollecting as stop:
            report.stopped = str(stop)
            say(f"STOPPED: {stop}")
        return self._finish(report)

    # ------------------------------------------------------------------ steps

    def _robots(self, report: LookReport) -> RobotsRules:
        fetched = self._get(ROBOTS_URL, report, allow_missing=True)
        if fetched is None or fetched.status == 404:
            report.lines.append("robots.txt: none (404), so nothing is forbidden by it.")
            return RobotsRules("")
        report.lines.append(f"robots.txt: read, {len(fetched.body)} bytes. It is obeyed.")
        rules = RobotsRules(fetched.body.decode("utf-8", errors="replace"))
        delay = rules.crawl_delay(self.client.identity.name)
        if delay:
            self.client.raise_pause_to(delay)
        return rules

    def _get(self, url: str, report: LookReport, allow_missing: bool = False) -> FetchResult | None:
        try:
            fetched = self.client.get(url)
        except FetchFailed as error:
            raise StopCollecting(f"{url} could not be read: {error}") from None
        if fetched.status == 404 and allow_missing:
            return fetched
        if fetched.status != 200:
            raise StopCollecting(f"{url} answered {fetched.status}")
        return fetched

    def _describe(self, what: str, fetched: FetchResult, report: LookReport) -> None:
        report.lines.append(
            f"--- The {what}: status {fetched.status}, {len(fetched.body)} bytes, "
            f"type {fetched.content_type or 'not given'}"
        )
        report.lines.append(skeleton(fetched.body))

    def _finish(self, report: LookReport) -> LookReport:
        report.requests_made = self.client.requests_made
        report.lines.append(
            f"Requests sent: {report.requests_made} (at most {LOOK_REQUESTS}). "
            "Nothing was saved to disk."
        )
        return report


def build_looker(
    settings: Settings, *, env_file: Path | None = None, **client_options: object
) -> Looker:
    """Everything a look needs. Refuses (CollectorRefused) when a promise cannot be kept."""
    if not settings.collect_ethglobal:
        raise CollectorRefused(
            "The switch for ethglobal.com is off. Set COLLECT_ETHGLOBAL=on in .env to allow it "
            "(design rule 17: only after the maintainer's yes for these three pages)."
        )
    identity = CollectorIdentity.from_settings(settings)
    prize_list, _, _ = data_paths(settings)
    first = load_prize_pages(prize_list)[0]

    def still_enabled() -> bool:
        return Settings(_env_file=env_file or ".env").collect_ethglobal

    client = PoliteClient(
        site=SITE,
        identity=identity,
        allow=is_allowed_url,
        is_enabled=still_enabled,
        max_requests=LOOK_REQUESTS,
        **client_options,  # type: ignore[arg-type]
    )
    return Looker(client, first)


def look_plan(settings: Settings) -> list[str]:
    """What a look would read, in plain words. Makes no request."""
    prize_list, _, _ = data_paths(settings)
    lines = [
        "A look would send at most three requests, two seconds apart, and save nothing:",
        f"  1. {ROBOTS_URL}",
    ]
    try:
        first = load_prize_pages(prize_list)[0]
    except CollectorRefused as refusal:
        lines.append(f"  2. (the first prize page of your list) {refusal}")
        return lines
    lines.append(f"  2. {first}")
    lines.append("  3. the first showcase project that this prize page links to")
    lines.append("It prints the shape of the two pages (no text, no person). It needs your yes.")
    return lines
