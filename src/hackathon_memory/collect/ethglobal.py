"""The collector for ETHGlobal's showcase: only the projects that took a Hedera prize.

ETHGlobal said yes in writing on 9 October 2026, "as long as you honor your commitment", and
the maintainer said yes in the chat the same day. The commitments are design 5.7. Each one is
code, with a test:

* Only the pages we named. A run reads the project pages on a short list that was made by hand
  (or sent by ETHGlobal), robots.txt, and nothing else. It never walks through the showcase.
  The prize pages of an event do not list winners (read on 10 October 2026), so they are not a
  starting point.
* A page that does not show a Hedera prize is not kept.
* A hard limit of 300 requests, one at a time, two seconds apart (polite.py).
* The tool's name and the maintainer's address in each request (polite.py).
* No names, photos or profiles of team members. A public project page shows no team at all: the
  people are visible only to a visitor who is signed in. The shape below has tripwires, so if a
  page ever shows a profile link, an avatar or a data key that holds people, the run stops
  (teamcut.py).
* One run. A second run skips every page that is already saved, and makes no request at all
  when nothing is missing.
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
import re
from collections.abc import Callable, Collection
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from hackathon_memory.collect.polite import (
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    PoliteClient,
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

SITE = "ethglobal.com"
ROBOTS_URL = f"https://{SITE}/robots.txt"
PROJECT_PAGE_PATH = re.compile(r"^/showcase/[A-Za-z0-9-]+$")
# robots.txt takes one of the 300 requests, so the list may hold 299 pages at most.
MAX_LISTED_PAGES = 299

# The line of a prize on a project page: the sponsor, a dash, the prize name, the place.
HEDERA_PRIZE_LINE = re.compile(r"^\s*hedera\s*[-‐-―]\s*\S", re.IGNORECASE)


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


def looks_like_a_project_page(url: str) -> bool:
    """The address has the form of one showcase project and nothing more."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != SITE or parts.query or parts.fragment:
        return False
    if parts.port not in (None, 443) or parts.username or parts.password:
        return False  # no other port, and no login written into the address
    return bool(PROJECT_PAGE_PATH.match(parts.path.rstrip("/")))


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


def took_a_hedera_prize(html: bytes) -> bool:
    """True if a "Winner of" block of the page has a line that starts with "Hedera -"."""
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml")
    for heading in soup.find_all("h3"):
        if " ".join(heading.get_text().split()).lower() != "winner of":
            continue
        block = heading.find_next_sibling()
        if block is None:
            continue
        for line in block.find_all("h4"):
            if HEDERA_PRIZE_LINE.match(" ".join(line.get_text(" ").split())):
                return True
    return False


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
        log: Callable[[str], None] = print,
    ) -> None:
        self.client = client
        self.store = store
        self.project_pages = project_pages
        self.shape = shape
        self.runs_dir = runs_dir
        self.log = log
        self._robots: RobotsRules | None = None
        self._unsafe_in_a_row = 0

    # ------------------------------------------------------------------ public

    def run(self) -> RunSummary:
        if self.shape.verified_on is None:
            raise CollectorRefused(
                f"The page shape of {SITE} has not been checked against real pages yet. "
                "No live run before that."
            )
        summary = RunSummary(started_at=_now(), project_pages_planned=len(self.project_pages))
        try:
            for url in self.project_pages:
                self._collect_project(url, summary)
        except StopCollecting as stop:
            summary.stopped = str(stop)
            self.log(f"STOPPED: {stop}")
        finally:
            summary.finished_at = _now()
            summary.requests_made = self.client.requests_made
            self._write_manifest(summary)
        return summary

    # ------------------------------------------------------------------ steps

    def _collect_project(self, url: str, summary: RunSummary) -> None:
        if self.store.has(url):
            summary.pages_already_saved += 1
            return
        self._fetch_and_save(url, self.shape.project_cut, summary)

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
            self.log(f"not kept {url}: the page shows no Hedera prize")
            return None
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
            self._robots = self._load_robots()
        agent = self.client.identity.name
        if not self._robots.allows(agent, url):
            raise StopCollecting(f"robots.txt of {SITE} does not allow this tool to read {url}")

    def _load_robots(self) -> RobotsRules:
        saved = self.store.load(ROBOTS_URL, suffix=".txt")
        if saved is not None:
            rules = RobotsRules(saved.read().decode("utf-8", errors="replace"))
            obey_crawl_delay(self.client, rules)
            return rules
        rules, fetched = read_rules(self.client, ROBOTS_URL, SITE)
        if fetched.status == 200:
            self.store.save(
                fetched,
                fetched.body,
                received=fetched.body,
                collector=f"{self.client.identity.name}/{self.client.identity.version}",
                suffix=".txt",
            )
        return rules

    def _write_manifest(self, summary: RunSummary) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = summary.started_at.replace("-", "").replace(":", "")
        path = self.runs_dir / f"{stamp}-ethglobal.json"
        path.write_text(
            json.dumps(asdict(summary), indent=2) + "\n", encoding="utf-8", newline="\n"
        )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------- building a real run


@dataclass(frozen=True)
class DataPaths:
    """Where the collector keeps its files. All of them are in the data folder, outside git."""

    page_list: Path  # the list of project pages that was made by hand
    raw_dir: Path  # the saved pages
    runs_dir: Path  # one record for each run


def data_paths(settings: Settings) -> DataPaths:
    root = Path(settings.data_dir)
    return DataPaths(
        page_list=root / "by-hand" / SITE / "project-pages.txt",
        raw_dir=root / "raw" / SITE,
        runs_dir=root / "runs",
    )


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
    *,
    env_file: Path | None = None,
    **client_options: object,
) -> PoliteClient:
    """A client for this site that may read only what `allow` names."""

    def still_enabled() -> bool:
        # Read again before every request, so that turning the switch off stops a run at once.
        return Settings(_env_file=env_file or ".env").collect_ethglobal

    return PoliteClient(
        site=SITE,
        identity=identity,
        allow=allow,
        is_enabled=still_enabled,
        **client_options,  # type: ignore[arg-type]
    )


def build_collector(
    settings: Settings,
    *,
    env_file: Path | None = None,
    shape: SiteShape = ETHGLOBAL_SHAPE,
    **client_options: object,
) -> EthGlobalCollector:
    """Everything a live run needs. Refuses (CollectorRefused) when a promise cannot be kept."""
    identity = identity_if_allowed(settings)
    paths = data_paths(settings)
    project_pages = load_project_pages(paths.page_list)
    named = frozenset(project_pages)
    client = polite_client(
        identity, lambda url: is_allowed_url(url, named), env_file=env_file, **client_options
    )
    return EthGlobalCollector(
        client=client,
        store=RawStore(paths.raw_dir),
        project_pages=project_pages,
        shape=shape,
        runs_dir=paths.runs_dir,
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
        "One request at a time, two seconds apart, at most 300 requests.",
        "Page shape checked against real pages: "
        + (
            f"{shape.verified_on} ({shape.checked_pages})"
            if shape.verified_on
            else "NO: a live run refuses"
        ),
        f"List of project pages: {page_list}",
    ]
    try:
        pages = load_project_pages(page_list)
    except CollectorRefused as refusal:
        lines.append(f"  {refusal}")
        return lines
    store = RawStore(paths.raw_dir)
    lines.append("It would read, in this order (robots.txt first, only if a page is missing):")
    lines.append(f"  {ROBOTS_URL}  ({'saved' if store.has(ROBOTS_URL, '.txt') else 'to fetch'})")
    for page in pages:
        lines.append(f"  {page}  ({'saved' if store.has(page) else 'to fetch'})")
    lines.append("  and nothing else. A page that shows no Hedera prize is read but not kept.")
    return lines
