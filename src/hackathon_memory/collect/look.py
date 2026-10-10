"""A quick look at ETHGlobal: at most two requests, nothing saved, no person printed.

    python -m hackathon_memory.collect ethglobal --look

Why. Before a run on the whole list, one page of the list is read to see that everything works:
the site answers an honest request, the team cut passes on a real page, and the page shows a
Hedera prize. If the site refuses, nothing is worked around (design rule 10).

What it does, inside the promises of design 5.7:

* robots.txt, then the FIRST project page of the list. Two requests at most, two seconds apart,
  with the name of the tool and the maintainer's address in each one. Never any other page.
* It prints the SHAPE of the page with the skeleton printer: every text only as its length, no
  heading except plain section words, no name, no link target except its shape. Then it says
  whether the team cut passes (it names a rule that fails, never a text) and whether the page
  shows a Hedera prize. Nothing is saved to disk. The page stays in memory and is gone when the
  command ends.

It still needs the maintainer's yes for these two pages (design rule 17), the switch
COLLECT_ETHGLOBAL=on, the contact address and the list of project pages.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from hackathon_memory.collect.ethglobal import (
    ETHGLOBAL_SHAPE,
    ROBOTS_URL,
    SITE,
    SiteShape,
    data_paths,
    identity_if_allowed,
    is_allowed_url,
    load_project_pages,
    polite_client,
    took_a_hedera_prize,
)
from hackathon_memory.collect.polite import (
    CollectorRefused,
    FetchFailed,
    FetchResult,
    PoliteClient,
    StopCollecting,
)
from hackathon_memory.collect.robots import RobotsRules, read_rules
from hackathon_memory.collect.skeleton import skeleton
from hackathon_memory.collect.teamcut import CutFailed, cut_team
from hackathon_memory.settings import Settings

LOOK_REQUESTS = 2  # robots.txt and one project page


@dataclass
class LookReport:
    lines: list[str] = field(default_factory=list)
    requests_made: int = 0
    stopped: str | None = None


class Looker:
    def __init__(
        self,
        client: PoliteClient,
        project_page: str,
        shape: SiteShape = ETHGLOBAL_SHAPE,
        log: Callable[[str], None] = print,
    ) -> None:
        self.client = client
        self.project_page = project_page
        self.shape = shape
        self.log = log

    def run(self) -> LookReport:
        report = LookReport()
        say = report.lines.append
        try:
            rules = self._robots(report)
            agent = self.client.identity.name
            if not rules.allows(agent, self.project_page):
                raise StopCollecting(
                    f"robots.txt of {SITE} does not allow this tool to read the project page"
                )
            fetched = self._get(self.project_page, report)
            if fetched is None:
                return self._finish(report)
            say(f"First project page of the list: {self.project_page}")
            self._describe("project page", fetched, report)
            self._judge(fetched, report)
        except StopCollecting as stop:
            report.stopped = str(stop)
            say(f"STOPPED: {stop}")
        return self._finish(report)

    # ------------------------------------------------------------------ steps

    def _robots(self, report: LookReport) -> RobotsRules:
        rules, fetched = read_rules(self.client, ROBOTS_URL, SITE)
        if fetched.status == 404:
            report.lines.append("robots.txt: none (404), so nothing is forbidden by it.")
        else:
            report.lines.append(f"robots.txt: read, {len(fetched.body)} bytes. It is obeyed.")
        return rules

    def _get(self, url: str, report: LookReport) -> FetchResult | None:
        try:
            fetched = self.client.get(url)
        except FetchFailed as error:
            raise StopCollecting(f"{url} could not be read: {error}") from None
        if fetched.status != 200:
            raise StopCollecting(f"{url} answered {fetched.status}")
        return fetched

    def _describe(self, what: str, fetched: FetchResult, report: LookReport) -> None:
        report.lines.append(
            f"--- The {what}: status {fetched.status}, {len(fetched.body)} bytes, "
            f"type {fetched.content_type or 'not given'}"
        )
        report.lines.append(skeleton(fetched.body))

    def _judge(self, fetched: FetchResult, report: LookReport) -> None:
        try:
            body, cut = cut_team(fetched.body, self.shape.project_cut)
        except CutFailed as failure:
            report.lines.append(
                f"Team cut: REFUSED ({type(failure).__name__}: {failure}). "
                "A run would stop on this page."
            )
            return
        report.lines.append(
            f"Team cut: passed ({cut.elements_removed} element(s) removed, "
            f"{cut.json_keys_removed} data key(s) removed, "
            f"{cut.strings_guarded} string(s) guarded)."
        )
        report.lines.append(
            "Hedera prize on the page: "
            + (
                "yes, the page would be kept."
                if took_a_hedera_prize(body)
                else "NO, the page would be read but not kept."
            )
        )

    def _finish(self, report: LookReport) -> LookReport:
        report.requests_made = self.client.requests_made
        report.lines.append(
            f"Requests sent: {report.requests_made} (at most {LOOK_REQUESTS}). "
            "Nothing was saved to disk."
        )
        return report


def build_looker(
    settings: Settings,
    *,
    env_file: Path | None = None,
    shape: SiteShape = ETHGLOBAL_SHAPE,
    **client_options: object,
) -> Looker:
    """Everything a look needs. Refuses (CollectorRefused) when a promise cannot be kept."""
    identity = identity_if_allowed(settings)
    first = load_project_pages(data_paths(settings).page_list)[0]
    client = polite_client(
        identity,
        lambda url: is_allowed_url(url, {first}),
        env_file=env_file,
        max_requests=LOOK_REQUESTS,
        **client_options,
    )
    return Looker(client, first, shape)


def look_plan(settings: Settings) -> list[str]:
    """What a look would read, in plain words. Makes no request."""
    page_list = data_paths(settings).page_list
    lines = [
        "A look would send at most two requests, two seconds apart, and save nothing:",
        f"  1. {ROBOTS_URL}",
    ]
    try:
        first = load_project_pages(page_list)[0]
    except CollectorRefused as refusal:
        lines.append(f"  2. (the first project page of your list) {refusal}")
        return lines
    lines.append(f"  2. {first}")
    lines.append("It prints the shape of the page (no text, no person), says whether the team cut")
    lines.append("passes and whether the page shows a Hedera prize. It needs your yes.")
    return lines
