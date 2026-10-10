"""The collector for ETHGlobal's showcase: only the projects that took a Hedera prize.

ETHGlobal said yes in writing on 9 October 2026, "as long as you honor your commitment", and
the maintainer said yes in the chat the same day. The commitments are design 5.7. Each one is
code, with a test:

* Only the pages we named. A run reads robots.txt and the project pages on its list, and nothing
  else. The list has two sources: the pages that the maintainer saw with a Hedera prize (a short
  list made by hand), and the winners that the walk through the Hedera list of the showcase
  found (ethglobal_find.py). The prize pages of an event do not list winners (read on
  10 October 2026), so they are not a starting point.
* The walk names a sponsor only by an id. Which id is Hedera is not guessed: it is the one id
  that all the pages seen by hand have (ethglobal_found.py).
* A page that does not show a Hedera prize is not kept.
* A hard limit of 300 requests over all runs, one at a time, two seconds apart (polite.py).
* The tool's name and the maintainer's address in each request (polite.py).
* No names, photos or profiles of team members. A public project page shows no team at all: the
  people are visible only to a visitor who is signed in. The shape below has tripwires, so if a
  page ever shows a profile link, an avatar or a data key that holds people, the run stops
  (teamcut.py).
* One run. A second run skips every page that is already saved, and every page that an earlier
  run read and did not keep. It makes no request at all when nothing is missing.
* A stop switch: COLLECT_ETHGLOBAL in .env, read again before every request.

What a project page looks like (3 real pages read on 10 October 2026, 2 of them winners of a
Hedera prize): a header with the name, a short line and the links to the demo and the code; a
box with the event and, for a winner, the block "Winner of" with one line per prize
("Hedera - <prize name> <place>"); the sections "Project Description" and "How it's Made"; the
data of the page as text in a script. The two metadata tags "author" and "twitter:creator" hold
the name of the site, not a person.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Collection
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from hackathon_memory.collect.ethglobal_found import (
    SponsorNotKnown,
    hedera_sponsor,
    load_found,
    winners_of,
)
from hackathon_memory.collect.ethglobal_site import (
    ROBOTS_URL,
    SITE,
    looks_like_a_project_page,
)
from hackathon_memory.collect.polite import (
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    PoliteClient,
    RequestCount,
    StopCollecting,
)
from hackathon_memory.collect.rawstore import RawStore, SavedPage
from hackathon_memory.collect.robots import RobotsRules, obey_crawl_delay, read_rules
from hackathon_memory.collect.teamcut import (
    CutPolicy,
    TeamShapeChanged,
    TeamTextRemains,
    cut_team,
)
from hackathon_memory.settings import Settings

# Pages in a row that cannot be saved safely. Three in a row means the shape is wrong, not bad luck.
MAX_UNSAFE_IN_A_ROW = 3

# Listed pages in a row that show no Hedera prize. One can be a mistake in a list. Three in a row
# mean that the list is wrong, and every further page would be a page that nobody was asked for.
MAX_WITHOUT_PRIZE_IN_A_ROW = 3

# robots.txt takes one of the 300 requests, so the list may hold 299 pages at most.
MAX_LISTED_PAGES = 299

# The line of a prize on a project page: the sponsor, a dash, the prize name, the place.
HEDERA_PRIZE_LINE = re.compile(r"^\s*hedera\s*[-‐-―]\s*\S", re.IGNORECASE)
_BEFORE_THE_DASH = re.compile(r"\s+[-\u2010-\u2015]\s+")


@dataclass(frozen=True)
class SiteShape:
    """What the pages of the site look like. Written from real pages, then checked by hand."""

    project_cut: CutPolicy
    verified_on: str | None  # the date it was checked against real pages, or None
    checked_pages: str = ""  # what that check looked at, in words (never page text)


ETHGLOBAL_SHAPE = SiteShape(
    project_cut=CutPolicy(
        rules=(),  # a visitor who is not signed in sees no team block
        json_blocklist=frozenset(
            {"members", "team", "teammembers", "users", "hackers", "authors", "contributors"}
        ),
        tripwires=(
            "#team",
            "[id*='team' i]",
            "[class*='avatar' i]",
            "[class*='team-member' i]",
            "a[href^='/hackers' i]",
            "a[href^='/users' i]",
            "a[href^='/u/' i]",
            "a[href^='/profile' i]",
        ),
        script_person_keys=frozenset(
            {
                "members",
                "teammembers",
                "team",
                "users",
                "user",
                "hackers",
                "hacker",
                "builders",
                "authors",
                "author",
                "creators",
                "creator",
                "contributors",
                "owner",
                "profile",
                "avatar",
                "email",
                "twitterhandle",
                "githubusername",
                "discordhandle",
            }
        ),
        site_names=frozenset({"ethglobal", "@ethglobal"}),
    ),
    verified_on="2026-10-10",
    checked_pages="3 public project pages, 2 of them winners of a Hedera prize",
)


def is_allowed_url(url: str, named: Collection[str]) -> bool:
    """True only for an address we named: robots.txt, or a project page that is on the list."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != SITE or parts.query or parts.fragment:
        return False
    if parts.port not in (None, 443) or parts.username or parts.password:
        return False
    path = parts.path.rstrip("/") or "/"
    if path == "/robots.txt":
        return True
    return looks_like_a_project_page(url) and f"https://{SITE}{path}" in named


def load_project_pages(path: Path) -> list[str]:
    """The list made by hand: one address per line, # for a comment."""
    if not path.exists():
        raise CollectorRefused(
            f"The list of project pages is missing: {path}. It is made by hand (or sent by "
            f"{SITE}): one address of a showcase project per line. The collector never walks "
            "through the whole showcase."
        )
    pages: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not looks_like_a_project_page(line):
            raise CollectorRefused(
                f"{path.name}, line {number}: not a project page of {SITE} "
                f"(expected https://{SITE}/showcase/<project>)"
            )
        pages.append(f"https://{SITE}{urlsplit(line).path.rstrip('/')}")
    pages = list(dict.fromkeys(pages))
    if not pages:
        raise CollectorRefused(f"The list of project pages is empty: {path}")
    if len(pages) > MAX_LISTED_PAGES:
        raise CollectorRefused(
            f"The list holds {len(pages)} pages. The promise is 300 requests at most, and "
            f"robots.txt is one of them, so the list may hold {MAX_LISTED_PAGES}."
        )
    return pages


def prize_lines(html: bytes) -> list[str]:
    """The lines of the "Winner of" blocks of a page, one for each prize, with plain spaces."""
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml")
    lines: list[str] = []
    for heading in soup.find_all("h3"):
        if " ".join(heading.get_text().split()).lower() != "winner of":
            continue
        block = heading.find_next_sibling()
        if block is not None:
            lines.extend(" ".join(line.get_text(" ").split()) for line in block.find_all("h4"))
    return lines


def took_a_hedera_prize(html: bytes) -> bool:
    """True if a "Winner of" block of the page has a line that starts with "Hedera -"."""
    return any(HEDERA_PRIZE_LINE.match(line) for line in prize_lines(html))


def prize_sponsors(html: bytes) -> list[str]:
    """The sponsors that the "Winner of" blocks name: the part of each line before the dash.

    Only for the message about a page that is not kept, so that a person can see why.
    """
    names = (_BEFORE_THE_DASH.split(line, maxsplit=1)[0][:60] for line in prize_lines(html))
    return list(dict.fromkeys(name for name in names if name))


@dataclass
class RunSummary:
    site: str = SITE
    started_at: str = ""
    finished_at: str = ""
    project_pages_planned: int = 0
    pages_saved: int = 0
    pages_already_saved: int = 0
    pages_not_found: list[str] = field(default_factory=list)
    # Pages that were read but NOT kept, because they show no Hedera prize.
    pages_without_hedera_prize: list[str] = field(default_factory=list)
    # Pages that were NOT saved because text of the team part also stands elsewhere in them.
    pages_skipped_team_text: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    # Pages that an earlier run read and did not keep. They are not asked for a second time.
    pages_not_kept_before: int = 0
    # Pages of the list that this run did not ask for, because it was told to read only some.
    pages_left_for_later: int = 0
    requests_made: int = 0
    stopped: str | None = None


class EthGlobalCollector:
    def __init__(
        self,
        *,
        client: PoliteClient,
        store: RawStore,
        project_pages: list[str],
        shape: SiteShape = ETHGLOBAL_SHAPE,
        runs_dir: Path,
        max_new_pages: int | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        if max_new_pages is not None and max_new_pages < 1:
            raise CollectorRefused("The number of pages to read must be 1 or more.")
        self.client = client
        self.store = store
        self.project_pages = project_pages
        self.shape = shape
        self.runs_dir = runs_dir
        # A run can be made in parts: the first pages, a look at what was saved, then the rest.
        self.max_new_pages = max_new_pages
        self.log = log
        self._robots: RobotsRules | None = None
        self._unsafe_in_a_row = 0
        self._without_prize_in_a_row = 0

    # ------------------------------------------------------------------ public

    def run(self) -> RunSummary:
        if self.shape.verified_on is None:
            raise CollectorRefused(
                f"The page shape of {SITE} has not been checked against real pages yet. "
                "No live run before that."
            )
        not_kept_before = read_and_not_kept(self.runs_dir)
        summary = RunSummary(started_at=_now(), project_pages_planned=len(self.project_pages))
        asked = 0
        try:
            for url in self.project_pages:
                if self.store.has(url):
                    summary.pages_already_saved += 1
                elif url in not_kept_before:
                    summary.pages_not_kept_before += 1
                elif self.max_new_pages is not None and asked >= self.max_new_pages:
                    summary.pages_left_for_later += 1
                else:
                    asked += 1
                    self._fetch_and_save(url, self.shape.project_cut, summary)
        except StopCollecting as stop:
            summary.stopped = str(stop)
            self.log(f"STOPPED: {stop}")
        finally:
            summary.finished_at = _now()
            summary.requests_made = self.client.requests_made
            self._write_manifest(summary)
        return summary

    # ------------------------------------------------------------------ steps

    def _fetch_and_save(self, url: str, policy: CutPolicy, summary: RunSummary) -> SavedPage | None:
        self._check_robots(url)
        try:
            fetched = self.client.get(url)
        except FetchFailed as error:
            summary.errors.append({"url": url, "kind": str(error)})
            return None
        if fetched.status in (404, 410):
            summary.pages_not_found.append(url)
            return None
        if fetched.status != 200:
            summary.errors.append({"url": url, "kind": f"status {fetched.status}"})
            return None
        try:
            body, report = cut_team(fetched.body, policy)
        except TeamShapeChanged as error:
            # The page is not shaped as expected, so the next ones will not be either. Stop.
            raise StopCollecting(
                f"The team part could not be cut safely on {url}: {error}"
            ) from None
        except TeamTextRemains:
            # This one page is not safe to save. The others may be. Skip it and say so.
            summary.pages_skipped_team_text.append(url)
            self._unsafe_in_a_row += 1
            self.log(f"skipped {url}: text of the team part is also elsewhere in the page")
            if self._unsafe_in_a_row >= MAX_UNSAFE_IN_A_ROW:
                raise StopCollecting(
                    f"{self._unsafe_in_a_row} pages in a row could not be saved safely. "
                    "The page shape is probably not what the collector expects."
                ) from None
            return None
        self._unsafe_in_a_row = 0
        if not took_a_hedera_prize(body):
            # The email promised the projects that took a Hedera prize. Nothing else is kept.
            summary.pages_without_hedera_prize.append(url)
            self._without_prize_in_a_row += 1
            shown = ", ".join(prize_sponsors(body)) or "no prize"
            self.log(f"not kept {url}: the page shows no Hedera prize (it shows: {shown})")
            if self._without_prize_in_a_row >= MAX_WITHOUT_PRIZE_IN_A_ROW:
                raise StopCollecting(
                    f"{self._without_prize_in_a_row} pages in a row show no Hedera prize. "
                    "The list of pages is probably wrong. Nothing more is read."
                )
            return None
        self._without_prize_in_a_row = 0
        saved = self.store.save(
            fetched,
            body,
            received=fetched.body,
            collector=f"{self.client.identity.name}/{self.client.identity.version}",
            team_cut=report.as_dict(),
        )
        summary.pages_saved += 1
        self.log(f"saved {url}")
        return saved

    def _check_robots(self, url: str) -> None:
        if self._robots is None:
            self._robots = load_robots(self.client, self.store)
        agent = self.client.identity.name
        if not self._robots.allows(agent, url):
            raise StopCollecting(f"robots.txt of {SITE} does not allow this tool to read {url}")

    def _write_manifest(self, summary: RunSummary) -> None:
        """One record for each run. A later run reads them, so none is written over or half."""
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = summary.started_at.replace("-", "").replace(":", "")
        path = self.runs_dir / f"{stamp}{RUN_RECORD_END}"
        number = 2
        while path.exists():  # two runs in the same second
            path = self.runs_dir / f"{stamp}-{number}{RUN_RECORD_END}"
            number += 1
        temporary = path.with_name(path.name + ".part")
        temporary.write_text(
            json.dumps(asdict(summary), indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        os.replace(temporary, path)


RUN_RECORD_END = "-ethglobal.json"


def read_and_not_kept(runs_dir: Path) -> set[str]:
    """The pages that an earlier run asked for and did not keep, from the records of the runs.

    A page with no Hedera prize, or a page that was not safe to save, is not asked for a second
    time: the answer would be the same, and the site was promised that a page is read once. A
    page that was missing or that failed is not in this set, so a later run tries it again.
    A record that cannot be read refuses the run: it is not taken for an empty one.
    """
    pages: set[str] = set()
    for record in sorted(runs_dir.glob(f"*{RUN_RECORD_END}")):
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
            for key in ("pages_without_hedera_prize", "pages_skipped_team_text"):
                if not all(isinstance(page, str) for page in data[key]):
                    raise ValueError("not a list of addresses")
                pages.update(data[key])
        except (OSError, ValueError, KeyError, TypeError):
            raise CollectorRefused(
                f"The record of an earlier run cannot be read: {record}. Repair it or move it "
                "away. It may name pages that must not be asked for again."
            ) from None
    return pages


def load_robots(client: PoliteClient, store: RawStore) -> RobotsRules:
    """The rules of the site: the saved copy if there is one, else one request (kept if 200)."""
    saved = store.load(ROBOTS_URL, suffix=".txt")
    if saved is not None:
        rules = RobotsRules(saved.read().decode("utf-8", errors="replace"))
        obey_crawl_delay(client, rules)
        return rules
    rules, fetched = read_rules(client, ROBOTS_URL, SITE)
    if fetched.status == 200:
        store.save(
            fetched,
            fetched.body,
            received=fetched.body,
            collector=f"{client.identity.name}/{client.identity.version}",
            suffix=".txt",
        )
    return rules


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------- building a real run


@dataclass(frozen=True)
class DataPaths:
    """Where the collector keeps its files. All of them are in the data folder, outside git."""

    page_list: Path  # the list of project pages that was made by hand
    found_list: Path  # what the walk through the Hedera list found
    raw_dir: Path  # the saved pages
    runs_dir: Path  # one record for each run
    request_count: Path  # how many requests were sent to the site, over all runs


def data_paths(settings: Settings) -> DataPaths:
    root = Path(settings.data_dir)
    return DataPaths(
        page_list=root / "by-hand" / SITE / "project-pages.txt",
        found_list=root / "found" / SITE / "hedera-list.json",
        raw_dir=root / "raw" / SITE,
        runs_dir=root / "runs",
        request_count=root / "requests" / f"{SITE}.json",
    )


@dataclass(frozen=True)
class PagePlan:
    """The project pages that a run reads, and where they come from."""

    pages: list[str]  # the pages seen by hand first, then the winners that the walk found
    by_hand: int
    from_walk: int  # winners of the walk that the hand-made list does not name
    notes: tuple[str, ...] = ()  # for the plan, in plain words


def planned_pages(paths: DataPaths) -> PagePlan:
    """What a run would read. Refuses when the sources do not give a list that can be trusted."""
    found = load_found(paths.found_list)
    if found is None:
        by_hand = load_project_pages(paths.page_list)
        return PagePlan(by_hand, len(by_hand), 0, ("No walk through the Hedera list was made.",))
    if not paths.page_list.exists():
        raise CollectorRefused(
            f"The walk found {len(found.with_prize)} projects with a prize, but the list names a "
            "sponsor only by an id. To learn which id is Hedera, the tool needs one project that "
            'you saw yourself with "Winner of" and a line that starts with "Hedera". Put its '
            f"address into {paths.page_list}."
        )
    by_hand = load_project_pages(paths.page_list)
    try:
        sponsor = hedera_sponsor(found, by_hand)
    except SponsorNotKnown as unsure:
        raise CollectorRefused(
            f"{unsure} The list of pages by hand is {paths.page_list}."
        ) from None
    winners = winners_of(found, sponsor)
    pages = list(dict.fromkeys([*by_hand, *winners]))
    if len(pages) > MAX_LISTED_PAGES:
        raise CollectorRefused(
            f"The run would read {len(pages)} pages. The promise is 300 requests at most, and "
            f"robots.txt is one of them, so a run may read {MAX_LISTED_PAGES}."
        )
    notes = [
        f"The walk found {len(found.with_prize)} projects with a prize of some sponsor. The "
        f"pages seen by hand say that the sponsor with the id {sponsor} is Hedera: "
        f"{len(winners)} projects took its prize."
    ]
    if not found.complete:
        notes.append(
            f"The walk is not finished: {found.pages_read} page(s) of the list were read. "
            "There may be more winners."
        )
    not_winners = sum(1 for page in by_hand if page not in set(winners))
    if not_winners:
        notes.append(
            f"{not_winners} page(s) seen by hand are not among these winners. The run reads "
            "them too, and keeps them only if they show a Hedera prize."
        )
    return PagePlan(pages, len(by_hand), len(pages) - len(by_hand), tuple(notes))


def requests_needed(
    project_pages: list[str], store: RawStore, not_kept_before: Collection[str] = ()
) -> int:
    """How many requests a run would send: robots.txt, and the pages that no run has read yet."""
    missing = sum(
        1 for page in project_pages if page not in not_kept_before and not store.has(page)
    )
    if missing == 0:
        return 0
    return missing + (0 if store.has(ROBOTS_URL, ".txt") else 1)


def identity_if_allowed(settings: Settings) -> CollectorIdentity:
    """The name and the address for the requests. Refuses while the switch of the site is off."""
    if not settings.collect_ethglobal:
        raise CollectorRefused(
            f"The switch for {SITE} is off. Set COLLECT_ETHGLOBAL=on in .env to allow it "
            "(design rule 17: only after the maintainer's yes for the pages that will be read)."
        )
    return CollectorIdentity.from_settings(settings)


def polite_client(
    identity: CollectorIdentity,
    allow: Callable[[str], bool],
    paths: DataPaths,
    *,
    env_file: Path | None = None,
    **client_options: object,
) -> PoliteClient:
    """A client for this site that may read only what `allow` names.

    Every request is counted in one file, so the limit of 300 holds over all runs together.
    """

    def still_enabled() -> bool:
        # Read again before every request, so that turning the switch off stops a run at once.
        return Settings(_env_file=env_file or ".env").collect_ethglobal

    return PoliteClient(
        site=SITE,
        identity=identity,
        allow=allow,
        is_enabled=still_enabled,
        count=RequestCount(paths.request_count, SITE),
        **client_options,  # type: ignore[arg-type]
    )


def build_collector(
    settings: Settings,
    *,
    max_new_pages: int | None = None,
    env_file: Path | None = None,
    shape: SiteShape = ETHGLOBAL_SHAPE,
    **client_options: object,
) -> EthGlobalCollector:
    """Everything a live run needs. Refuses (CollectorRefused) when a promise cannot be kept.

    The whole list must fit into the requests that are left, also when this run reads only a
    part of it (`max_new_pages`): a job that cannot be finished is not started.
    """
    identity = identity_if_allowed(settings)
    paths = data_paths(settings)
    project_pages = planned_pages(paths).pages
    named = frozenset(project_pages)
    client = polite_client(
        identity, lambda url: is_allowed_url(url, named), paths, env_file=env_file, **client_options
    )
    store = RawStore(paths.raw_dir)
    needed = requests_needed(project_pages, store, read_and_not_kept(paths.runs_dir))
    try:
        left = client.count.left()
    except StopCollecting as stop:
        raise CollectorRefused(str(stop)) from None
    if needed > left:
        raise CollectorRefused(
            f"The run needs {needed} requests, and {left} are left of the {client.count.limit} "
            f"that were promised to {SITE}. Make the list shorter, or ask the site for more."
        )
    return EthGlobalCollector(
        client=client,
        store=store,
        project_pages=project_pages,
        shape=shape,
        runs_dir=paths.runs_dir,
        max_new_pages=max_new_pages,
    )


def plan(settings: Settings, shape: SiteShape = ETHGLOBAL_SHAPE) -> list[str]:
    """What a live run would do, in plain words. Makes no request."""
    paths = data_paths(settings)
    page_list = paths.page_list
    lines = [
        f"Site: {SITE}",
        f"Switch COLLECT_ETHGLOBAL: {'on' if settings.collect_ethglobal else 'off'}",
        f"Tool name in every request: {settings.collector_name or '(empty: the run will refuse)'}",
        "Contact address in every request: "
        + ("set" if settings.collector_contact_email.get_secret_value() else "(empty: refuse)"),
        "One request at a time, two seconds apart, at most 300 requests over all runs.",
        _count_line(paths),
        "Page shape checked against real pages: "
        + (
            f"{shape.verified_on} ({shape.checked_pages})"
            if shape.verified_on
            else "NO: a live run refuses"
        ),
        f"Project pages seen by hand: {page_list}",
    ]
    try:
        planned = planned_pages(paths)
        not_kept_before = read_and_not_kept(paths.runs_dir)
    except CollectorRefused as refusal:
        lines.append(f"  {refusal}")
        return lines
    pages = planned.pages
    lines.append(
        f"  {planned.by_hand} page(s) by hand, and {planned.from_walk} more from the walk."
    )
    lines.extend(f"  {note}" for note in planned.notes)
    store = RawStore(paths.raw_dir)

    def state(page: str) -> str:
        if store.has(page):
            return "saved"
        return (
            "read before and not kept: not asked for again"
            if page in not_kept_before
            else "to fetch"
        )

    lines.append("It would read, in this order (robots.txt first, only if a page is missing):")
    lines.append(f"  {ROBOTS_URL}  ({'saved' if store.has(ROBOTS_URL, '.txt') else 'to fetch'})")
    lines.extend(f"  {page}  ({state(page)})" for page in pages)
    lines.append("  and nothing else. A page that shows no Hedera prize is read but not kept.")
    lines.append(f"That is {requests_needed(pages, store, not_kept_before)} request(s).")
    return lines


def _count_line(paths: DataPaths) -> str:
    count = RequestCount(paths.request_count, SITE)
    try:
        return f"Requests sent to the site so far: {count.sent()} of {count.limit}."
    except StopCollecting as stop:
        return str(stop)
