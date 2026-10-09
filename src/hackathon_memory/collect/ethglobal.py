"""The collector for ETHGlobal's showcase: only the projects that took a Hedera prize.

ETHGlobal said yes in writing on 9 October 2026, "as long as you honor your commitment", and
the maintainer said yes in the chat the same day. The commitments are design section 5.7. Each
one is code, with a test:

* Only the pages we named. The run starts from a short list of Hedera prize pages that the
  maintainer checked by hand, and follows only the project links on those pages.
* A hard limit of 300 requests, one at a time, two seconds apart (polite.py).
* The tool's name and the maintainer's address in each request (polite.py).
* The team part of every page is cut out before the page is saved (teamcut.py).
* One run. A second run skips every page that is already saved, and makes no request at all
  when nothing is missing.
* A stop switch: COLLECT_ETHGLOBAL in .env, read again before every request.

THE PAGE SHAPE BELOW HAS NOT BEEN CHECKED AGAINST A REAL PAGE (`verified_on` is None). Until
it is, the collector refuses to run live. Design rule: "send one real request and look
at the answer before you write a collector", and design rule 18 forbids looking with any
tool that does not carry the maintainer's address. So the maintainer saves one prize page and one
project page by hand from a browser, and the shape is written from those.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from hackathon_memory.collect.polite import (
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    FetchResult,
    PoliteClient,
    StopCollecting,
)
from hackathon_memory.collect.rawstore import RawStore, SavedPage
from hackathon_memory.collect.robots import RobotsRules
from hackathon_memory.collect.teamcut import (
    CutPolicy,
    CutRule,
    TeamShapeChanged,
    TeamTextRemains,
    cut_team,
)
from hackathon_memory.settings import Settings

# Pages in a row that cannot be saved safely. Three in a row means the shape is wrong, not bad luck.
MAX_UNSAFE_IN_A_ROW = 3

SITE = "ethglobal.com"
ROBOTS_URL = f"https://{SITE}/robots.txt"
PRIZE_PAGE_PATH = re.compile(r"^/events/[a-z0-9-]+/prizes/hedera$")
PROJECT_PAGE_PATH = re.compile(r"^/showcase/[A-Za-z0-9-]+$")


@dataclass(frozen=True)
class SiteShape:
    """What the pages of the site look like. Written from a real page, then checked by hand."""

    project_links_selector: str
    project_cut: CutPolicy
    prize_cut: CutPolicy
    verified_on: str | None  # the date it was checked against a real page, or None


# A guess, NOT checked. The collector will not run live with it.
ETHGLOBAL_SHAPE = SiteShape(
    project_links_selector="main a[href]",
    project_cut=CutPolicy(
        rules=(CutRule("#team", required=True),),
        json_blocklist=frozenset(
            {"members", "team", "teammembers", "users", "hackers", "authors", "contributors"}
        ),
    ),
    prize_cut=CutPolicy(rules=(CutRule("#team", required=False),)),
    verified_on=None,
)


def is_allowed_url(url: str) -> bool:
    """True only for an address we named: robots.txt, a Hedera prize page, a showcase project."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != SITE or parts.query or parts.fragment:
        return False
    if parts.port not in (None, 443) or parts.username or parts.password:
        return False  # no other port, and no login written into the address
    path = parts.path.rstrip("/") or "/"
    return path == "/robots.txt" or bool(
        PRIZE_PAGE_PATH.match(path) or PROJECT_PAGE_PATH.match(path)
    )


def load_prize_pages(path: Path) -> list[str]:
    """The list the maintainer checked by hand: one address per line, # for a comment."""
    if not path.exists():
        raise CollectorRefused(
            f"The list of Hedera prize pages is missing: {path}. The maintainer writes it by hand "
            "(design 15, step 9). The collector never walks through the whole showcase."
        )
    pages: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = urlsplit(line)
        if not is_allowed_url(line) or not PRIZE_PAGE_PATH.match(parts.path.rstrip("/")):
            raise CollectorRefused(
                f"{path.name}, line {number}: not a Hedera prize page of {SITE} "
                f"(expected https://{SITE}/events/<event>/prizes/hedera)"
            )
        pages.append(f"https://{SITE}{parts.path.rstrip('/')}")
    if not pages:
        raise CollectorRefused(f"The list of Hedera prize pages is empty: {path}")
    return list(dict.fromkeys(pages))


def extract_project_links(html: bytes, base_url: str, selector: str) -> list[str]:
    """The project pages that a prize page links to, in order, once each."""
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml")
    found: list[str] = []
    for anchor in soup.select(selector):
        absolute = urljoin(base_url, str(anchor.get("href", "")))
        parts = urlsplit(absolute)
        if parts.hostname == SITE and PROJECT_PAGE_PATH.match(parts.path.rstrip("/")):
            found.append(f"https://{SITE}{parts.path.rstrip('/')}")
    return list(dict.fromkeys(found))


@dataclass
class RunSummary:
    site: str = SITE
    started_at: str = ""
    finished_at: str = ""
    prize_pages_planned: int = 0
    project_links_found: int = 0
    pages_saved: int = 0
    pages_already_saved: int = 0
    pages_not_found: list[str] = field(default_factory=list)
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
        prize_pages: list[str],
        shape: SiteShape = ETHGLOBAL_SHAPE,
        runs_dir: Path,
        log: Callable[[str], None] = print,
    ) -> None:
        self.client = client
        self.store = store
        self.prize_pages = prize_pages
        self.shape = shape
        self.runs_dir = runs_dir
        self.log = log
        self._robots: RobotsRules | None = None
        self._unsafe_in_a_row = 0

    # ------------------------------------------------------------------ public

    def run(self) -> RunSummary:
        if self.shape.verified_on is None:
            raise CollectorRefused(
                f"The page shape of {SITE} has not been checked against a real page yet. "
                "The maintainer saves one prize page and one project page by hand, and the shape "
                "is written from them. No live run before that."
            )
        summary = RunSummary(
            started_at=_now(),
            prize_pages_planned=len(self.prize_pages),
        )
        try:
            project_urls = self._collect_prize_pages(summary)
            summary.project_links_found = len(project_urls)
            for url in project_urls:
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

    def _collect_prize_pages(self, summary: RunSummary) -> list[str]:
        urls: list[str] = []
        for prize_url in self.prize_pages:
            saved = self.store.load(prize_url) or self._fetch_and_save(
                prize_url, self.shape.prize_cut, summary
            )
            if saved is None:
                continue
            urls.extend(
                extract_project_links(saved.read(), prize_url, self.shape.project_links_selector)
            )
        return list(dict.fromkeys(urls))

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
        if saved is None:
            fetched = self._fetch_robots()
            text = fetched.body.decode("utf-8", errors="replace") if fetched.status == 200 else ""
            if fetched.status == 200:
                self.store.save(
                    fetched,
                    fetched.body,
                    received=fetched.body,
                    collector=f"{self.client.identity.name}/{self.client.identity.version}",
                    suffix=".txt",
                )
        else:
            text = saved.read().decode("utf-8", errors="replace")
        rules = RobotsRules(text)
        delay = rules.crawl_delay(self.client.identity.name)
        if delay:
            self.client.raise_pause_to(delay)
        return rules

    def _fetch_robots(self) -> FetchResult:
        try:
            fetched = self.client.get(ROBOTS_URL)
        except FetchFailed as error:
            raise StopCollecting(f"robots.txt of {SITE} could not be read: {error}") from None
        if fetched.status not in (200, 404):
            # Anything else is unclear. We do not guess in our own favour.
            raise StopCollecting(f"robots.txt of {SITE} answered {fetched.status}. Stopped.")
        return fetched

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


def data_paths(settings: Settings) -> tuple[Path, Path, Path]:
    """The prize-page list, the folder of saved pages, and the folder of run records."""
    root = Path(settings.data_dir)
    return (
        root / "by-hand" / SITE / "prize-pages.txt",
        root / "raw" / SITE,
        root / "runs",
    )


def build_collector(
    settings: Settings,
    *,
    env_file: Path | None = None,
    shape: SiteShape = ETHGLOBAL_SHAPE,
    **client_options: object,
) -> EthGlobalCollector:
    """Everything a live run needs. Refuses (CollectorRefused) when a promise cannot be kept."""
    if not settings.collect_ethglobal:
        raise CollectorRefused(
            "The switch for ethglobal.com is off. Set COLLECT_ETHGLOBAL=on in .env to allow a "
            "run (design rule 17: only after the maintainer's yes for this site)."
        )
    identity = CollectorIdentity.from_settings(settings)
    prize_list, raw_dir, runs_dir = data_paths(settings)
    prize_pages = load_prize_pages(prize_list)

    def still_enabled() -> bool:
        # Read again before every request, so that turning the switch off stops a run at once.
        return Settings(_env_file=env_file or ".env").collect_ethglobal

    client = PoliteClient(
        site=SITE,
        identity=identity,
        allow=is_allowed_url,
        is_enabled=still_enabled,
        **client_options,  # type: ignore[arg-type]
    )
    return EthGlobalCollector(
        client=client,
        store=RawStore(raw_dir),
        prize_pages=prize_pages,
        shape=shape,
        runs_dir=runs_dir,
    )


def plan(settings: Settings, shape: SiteShape = ETHGLOBAL_SHAPE) -> list[str]:
    """What a live run would do, in plain words. Makes no request."""
    prize_list, raw_dir, _ = data_paths(settings)
    lines = [
        f"Site: {SITE}",
        f"Switch COLLECT_ETHGLOBAL: {'on' if settings.collect_ethglobal else 'off'}",
        f"Tool name in every request: {settings.collector_name or '(empty: the run will refuse)'}",
        "Contact address in every request: "
        + ("set" if settings.collector_contact_email.get_secret_value() else "(empty: refuse)"),
        "One request at a time, two seconds apart, at most 300 requests.",
        f"Page shape checked against a real page: {shape.verified_on or 'NO: a live run refuses'}",
        f"List of prize pages: {prize_list}",
    ]
    try:
        pages = load_prize_pages(prize_list)
    except CollectorRefused as refusal:
        lines.append(f"  {refusal}")
        return lines
    store = RawStore(raw_dir)
    lines.append("It would read, in this order (robots.txt first, only if a page is missing):")
    lines.append(f"  {ROBOTS_URL}  ({'saved' if store.has(ROBOTS_URL, '.txt') else 'to fetch'})")
    for page in pages:
        lines.append(f"  {page}  ({'saved' if store.has(page) else 'to fetch'})")
    lines.append("  then the showcase pages that those prize pages link to, and nothing else.")
    return lines
