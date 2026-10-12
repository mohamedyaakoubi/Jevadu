"""The collector for ETHGlobal's showcase: the projects that the showcase ties to Hedera.

ETHGlobal was asked before any program read its showcase, and it agreed in writing to a slow,
signed read of its Hedera prize projects (9 October 2026). On 10 October 2026 the maintainer
decided to read the other projects that the showcase ties to Hedera in exactly the same way,
so that the tool can show what is built on Hedera and not only what wins. The way a page is read
is design 5.7. Each rule is code, with a test:

* Only named pages. A run reads robots.txt and the project pages on its list, and nothing else.
  The list has two sources: the pages that the maintainer saw with a Hedera prize (a short list
  made by hand), and every project that the walk found in the showcase list with the filter
  "partner: Hedera" (ethglobal_find.py). The prize pages of an event do not list winners (read
  on 10 October 2026), so they are not a starting point.
* Every page of that list is kept, with or without a prize. Whether a project took a Hedera
  prize is read later from its own page, in the block "Winner of".
* The list names a sponsor only by an id. Which id is Hedera is not guessed: it is the one id
  that all the pages seen by hand have (ethglobal_found.py). The run compares the list with each
  page, and three pages in a row that differ stop it.
* A fixed limit of requests for this site over all runs, one at a time, two seconds apart
  (polite.py, ethglobal_site.py).
* The tool's name and the maintainer's address in each request (polite.py).
* No names, photos or profiles of team members. A public project page shows no team at all: the
  people are visible only to a visitor who is signed in. The shape below has tripwires, so if a
  page ever shows a profile link, an avatar or a data key that holds people, the run stops
  (teamcut.py).
* One run. A second run skips every page that is already saved, and every page that an earlier
  run read and did not keep. It makes no request at all when nothing is missing.
* A stop switch: COLLECT_ETHGLOBAL in .env, read again before every request.

What a project page looks like (92 real pages read on 10 October 2026, all winners of a Hedera
prize): a header with the name, a short line and the links to the demo and the code; a box with
the event and, for a winner, the block "Winner of" with one line per prize ("Hedera - <prize
name> <place>"); the sections "Project Description" and "How it's Made"; the data of the page as
text in a script. The two metadata tags "author" and "twitter:creator" hold the name of the
site, not a person. The data of a page also holds scores that the site computes: they are never
read out (design 3.3).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Collection
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from hackathon_memory.collect.ethglobal_found import (
    SponsorNotKnown,
    hedera_sponsor,
    load_found,
    winners_of,
)
from hackathon_memory.collect.ethglobal_site import (
    REQUEST_LIMIT,
    ROBOTS_URL,
    SITE,
    looks_like_a_project_page,
)
from hackathon_memory.collect.polite import (
    PAUSE_SECONDS,
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    PoliteClient,
    RequestCount,
    StopCollecting,
    TooManyRequests,
)
from hackathon_memory.collect.rawstore import RawStore, SavedPage
from hackathon_memory.collect.robots import RobotsRules, obey_crawl_delay, read_rules
from hackathon_memory.collect.teamcut import (
    CutPolicy,
    TeamShapeChanged,
    TeamTextRemains,
    cut_team,
)
from hackathon_memory.parse.ethglobal_page import prize_sponsors, took_a_hedera_prize
from hackathon_memory.settings import Settings

# Pages in a row that cannot be saved safely. Three in a row means the shape is wrong, not bad luck.
MAX_UNSAFE_IN_A_ROW = 3

# Pages in a row, seen by hand and not in the Hedera list, that show no Hedera prize. One can be
# a mistake in the hand-made list. Three in a row mean that this list is wrong.
MAX_WITHOUT_PRIZE_IN_A_ROW = 3

# Pages in a row where the list and the page do not agree about a Hedera prize. Three in a row
# mean that the tool took the wrong sponsor id for Hedera, and a person must look.
MAX_DIFFERENT_IN_A_ROW = 3

# robots.txt takes one of the requests of the site, so a run may read one page less.
MAX_LISTED_PAGES = REQUEST_LIMIT - 1


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
            f"The list holds {len(pages)} pages. The limit for {SITE} is {REQUEST_LIMIT} "
            f"requests, and robots.txt is one of them, so the list may hold {MAX_LISTED_PAGES}."
        )
    return pages


@dataclass
class RunSummary:
    site: str = SITE
    started_at: str = ""
    finished_at: str = ""
    project_pages_planned: int = 0
    pages_saved: int = 0
    pages_already_saved: int = 0
    pages_not_found: list[str] = field(default_factory=list)
    # Pages that were read but NOT kept: they are not in the Hedera list of the showcase, and
    # they show no Hedera prize.
    pages_without_hedera_prize: list[str] = field(default_factory=list)
    # Pages that were kept, where the list and the page do not agree about a Hedera prize.
    pages_that_differ_from_the_list: list[str] = field(default_factory=list)
    # Pages that were NOT saved because text of the team part also stands elsewhere in them.
    pages_skipped_team_text: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    # Pages that an earlier run read and did not keep. They are not asked for a second time.
    pages_not_kept_before: int = 0
    # Pages of the list that this run did not ask for, because it was told to read only some.
    pages_left_for_later: int = 0
    requests_made: int = 0
    pause_seconds: float = 0.0  # the pause between two requests in this run
    cooldowns_waited: int = 0  # how often this run waited for the end of a cooldown
    # What the answers of the site said about limits and caches: header names and values.
    site_headers: dict[str, str] = field(default_factory=dict)
    cache_answers: dict[str, int] = field(default_factory=dict)
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
        in_the_list: Collection[str] = (),
        hedera_in_the_list: Collection[str] = (),
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
        # The pages that the walk found in the Hedera list of the showcase. All of them are kept.
        self.in_the_list = frozenset(in_the_list)
        # Those of them that the list marks with the sponsor id of Hedera.
        self.hedera_in_the_list = frozenset(hedera_in_the_list)
        # A run can be made in parts: the first pages, a look at what was saved, then the rest.
        self.max_new_pages = max_new_pages
        self.log = log
        self._robots: RobotsRules | None = None
        self._unsafe_in_a_row = 0
        self._without_prize_in_a_row = 0
        self._different_in_a_row = 0
        self._limits_said = False

    # ------------------------------------------------------------------ public

    def run(self) -> RunSummary:
        if self.shape.verified_on is None:
            raise CollectorRefused(
                f"The page shape of {SITE} has not been checked against real pages yet. "
                "No live run before that."
            )
        not_kept_before = read_and_not_kept(self.runs_dir)
        summary = RunSummary(
            started_at=_now(),
            project_pages_planned=len(self.project_pages),
            pause_seconds=self.client.pause_in_use(),
        )
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
                    self._fetch_and_save_when_allowed(url, summary)
        except StopCollecting as stop:
            summary.stopped = str(stop)
            self.log(f"STOPPED: {stop}")
        finally:
            summary.finished_at = _now()
            summary.requests_made = self.client.requests_made
            summary.cooldowns_waited = self.client.cooldowns_waited
            summary.site_headers = dict(self.client.site_headers)
            summary.cache_answers = dict(self.client.cache_answers)
            self._write_manifest(summary)
        return summary

    # ------------------------------------------------------------------ steps

    def _fetch_and_save_when_allowed(self, url: str, summary: RunSummary) -> None:
        """One page. After "too many requests" the same page is asked for again, but only when
        the run was told to wait for the end of a cooldown. The client does the waiting, and it
        stops for good when the site has said it too often."""
        while True:
            try:
                self._fetch_and_save(url, self.shape.project_cut, summary)
                return
            except TooManyRequests as slow_down:
                if not self.client.wait_for_cooldown:
                    raise
                self.log(f"WAITING: {slow_down}")

    def _fetch_and_save(self, url: str, policy: CutPolicy, summary: RunSummary) -> SavedPage | None:
        self._check_robots(url)
        try:
            fetched = self.client.get(url)
        except FetchFailed as error:
            summary.errors.append({"url": url, "kind": str(error)})
            return None
        if not self._limits_said and self.client.site_headers:
            # Said once, early, so that a person can see what the site counts while a run goes.
            self._limits_said = True
            self.log(f"the site says about limits and caches: {self.client.site_headers}")
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
        has_prize = took_a_hedera_prize(body)
        listed = url in self.in_the_list
        if not listed and not has_prize:
            # A page seen by hand that the showcase does not tie to Hedera, and that shows no
            # Hedera prize: it is not a Hedera project, so it is not kept.
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
        if listed:
            self._compare_with_the_list(url, has_prize, body, summary)
        return saved

    def _compare_with_the_list(
        self, url: str, has_prize: bool, body: bytes, summary: RunSummary
    ) -> None:
        """The list and the page must agree about a Hedera prize. The page is kept either way."""
        if has_prize == (url in self.hedera_in_the_list):
            self._different_in_a_row = 0
            return
        summary.pages_that_differ_from_the_list.append(url)
        self._different_in_a_row += 1
        shown = ", ".join(prize_sponsors(body)) or "no prize"
        self.log(
            f"differs {url}: the list "
            + ("names" if not has_prize else "does not name")
            + f" a Hedera prize, and the page shows: {shown}"
        )
        if self._different_in_a_row >= MAX_DIFFERENT_IN_A_ROW:
            raise StopCollecting(
                f"{self._different_in_a_row} pages in a row do not agree with the list about a "
                "Hedera prize. The sponsor id that was taken for Hedera is probably wrong. "
                "Nothing more is read."
            )

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


def pages_in_run_records(runs_dir: Path, *keys: str) -> set[str]:
    """The pages that the records of the earlier runs name under these keys.

    A record that cannot be read refuses the run: it is not taken for an empty one. A key that
    an older record does not have yet counts as an empty list.
    """
    pages: set[str] = set()
    for record in sorted(runs_dir.glob(f"*{RUN_RECORD_END}")):
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
            if data["site"] != SITE:
                raise ValueError("not a record of this site")
            for key in keys:
                named = data.get(key, [])
                if not isinstance(named, list) or not all(isinstance(p, str) for p in named):
                    raise ValueError("not a list of addresses")
                pages.update(named)
        except (OSError, ValueError, KeyError, TypeError):
            raise CollectorRefused(
                f"The record of an earlier run cannot be read: {record}. Repair it or move it "
                "away. It may name pages that must not be asked for again."
            ) from None
    return pages


def read_and_not_kept(runs_dir: Path) -> set[str]:
    """The pages that an earlier run asked for and did not keep.

    A page that was read and not kept (it is not a Hedera project, or it was not safe to save)
    is not asked for a second time: the answer would be the same, and a page is read once. A
    page that was missing or that failed is not in this set, so a later run tries it again.
    """
    return pages_in_run_records(runs_dir, "pages_without_hedera_prize", "pages_skipped_team_text")


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

    pages: list[str]  # the pages seen by hand first, then the projects that the walk found
    by_hand: int
    from_walk: int  # projects of the walk that the hand-made list does not name
    in_the_list: frozenset[str] = frozenset()  # every project of the walk
    hedera_in_the_list: frozenset[str] = frozenset()  # those with the sponsor id of Hedera
    notes: tuple[str, ...] = ()  # for the plan, in plain words


def planned_pages(paths: DataPaths) -> PagePlan:
    """What a run would read. Refuses when the sources do not give a list that can be trusted."""
    found = load_found(paths.found_list)
    if found is None:
        by_hand = load_project_pages(paths.page_list)
        note = "No walk through the Hedera list was made: only the pages seen by hand are read."
        return PagePlan(by_hand, len(by_hand), 0, notes=(note,))
    if not paths.page_list.exists():
        raise CollectorRefused(
            f"The walk found {found.listed} projects, but the list names a sponsor only by an "
            "id. To learn which id is Hedera, the tool needs one project that you saw yourself "
            'with "Winner of" and a line that starts with "Hedera". Put its address into '
            f"{paths.page_list}."
        )
    by_hand = load_project_pages(paths.page_list)
    try:
        sponsor = hedera_sponsor(found, by_hand)
    except SponsorNotKnown as unsure:
        raise CollectorRefused(
            f"{unsure} The list of pages by hand is {paths.page_list}."
        ) from None
    listed = [project.page for project in found.projects]
    winners = winners_of(found, sponsor)
    pages = list(dict.fromkeys([*by_hand, *listed]))
    if len(pages) > MAX_LISTED_PAGES:
        raise CollectorRefused(
            f"The run would read {len(pages)} pages. The limit for {SITE} is {REQUEST_LIMIT} "
            f"requests, and robots.txt is one of them, so a run may read {MAX_LISTED_PAGES}."
        )
    other_prize = len(found.with_prize) - len(winners)
    notes = [
        f"The walk found {found.listed} projects in the Hedera list of the showcase. "
        f"{len(winners)} took a Hedera prize (the pages seen by hand say that the sponsor with "
        f"the id {sponsor} is Hedera), {other_prize} took a prize of another sponsor only, and "
        f"{found.listed - len(found.with_prize)} took no prize."
    ]
    if not found.complete:
        notes.append(
            f"The walk is not finished: {found.pages_read} page(s) of the list were read. "
            "There may be more projects."
        )
    outside = sum(1 for page in by_hand if page not in set(listed))
    if outside:
        notes.append(
            f"{outside} page(s) seen by hand are not in the list. The run reads them too, and "
            "keeps them only if they show a Hedera prize."
        )
    return PagePlan(
        pages,
        len(by_hand),
        len(pages) - len(by_hand),
        frozenset(listed),
        frozenset(winners),
        tuple(notes),
    )


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

    Every request is counted in one file, so the limit of the site holds over all runs together.
    The same file remembers a refusal of the site: then nothing is built, and nothing is sent.
    """
    client_options.setdefault("max_requests", REQUEST_LIMIT)
    pause = client_options.get("pause_seconds")
    if pause is not None and float(pause) < PAUSE_SECONDS:  # type: ignore[arg-type]
        raise CollectorRefused(
            f"The pause between two requests is never shorter than {PAUSE_SECONDS:.0f} seconds."
        )
    count = request_count(paths)
    try:
        refused = count.refusal()
    except StopCollecting as stop:
        raise CollectorRefused(str(stop)) from None
    if refused:
        raise CollectorRefused(refusal_line(refused))
    if count.wait_left() > 0 and not client_options.get("wait_for_cooldown"):
        raise CollectorRefused(
            cooldown_line(count) + " Start the command again then, or add --wait to let it wait."
        )

    def still_enabled() -> bool:
        # Read again before every request, so that turning the switch off stops a run at once.
        return Settings(_env_file=env_file or ".env").collect_ethglobal

    return PoliteClient(
        site=SITE,
        identity=identity,
        allow=allow,
        is_enabled=still_enabled,
        count=count,
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
    planned = planned_pages(paths)
    project_pages = planned.pages
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
            f"that are the limit for {SITE}. Make the list shorter."
        )
    return EthGlobalCollector(
        client=client,
        store=store,
        project_pages=project_pages,
        shape=shape,
        runs_dir=paths.runs_dir,
        in_the_list=planned.in_the_list,
        hedera_in_the_list=planned.hedera_in_the_list,
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
        "One request at a time, two seconds apart, "
        f"at most {REQUEST_LIMIT} requests over all runs.",
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

    to_fetch = [page for page in pages if state(page) == "to fetch"]
    lines.append(
        f"The run has {len(pages)} page(s): {sum(1 for page in pages if store.has(page))} saved, "
        f"{len(to_fetch)} to fetch."
    )
    lines.append("It would read, in this order (robots.txt first, only if a page is missing):")
    lines.append(f"  {ROBOTS_URL}  ({'saved' if store.has(ROBOTS_URL, '.txt') else 'to fetch'})")
    if len(pages) <= PLAN_LISTS_EVERY_PAGE_UP_TO:
        lines.extend(f"  {page}  ({state(page)})" for page in pages)
    else:
        lines.extend(f"  {page}  (to fetch)" for page in to_fetch[:PLAN_SHOWS_FIRST])
        if len(to_fetch) > PLAN_SHOWS_FIRST:
            lines.append(f"  ... and {len(to_fetch) - PLAN_SHOWS_FIRST} more pages to fetch")
    lines.append("  and nothing else.")
    lines.append(f"That is {requests_needed(pages, store, not_kept_before)} request(s).")
    return lines


# A plan names every page while the list is short. A long list is shown by its numbers and by the
# first pages that are still to fetch.
PLAN_LISTS_EVERY_PAGE_UP_TO = 30
PLAN_SHOWS_FIRST = 10


def request_count(paths: DataPaths) -> RequestCount:
    """The count of all requests to this site, with the limit of this site."""
    return RequestCount(paths.request_count, SITE, limit=REQUEST_LIMIT)


def _count_line(paths: DataPaths) -> str:
    count = request_count(paths)
    try:
        lines = [f"Requests sent to the site so far: {count.sent()} of {count.limit}."]
        refused = count.refusal()
        if refused:
            lines.append(refusal_line(refused))
        if count.wait_left() > 0:
            lines.append(cooldown_line(count))
        if count.min_pause() > PAUSE_SECONDS:
            lines.append(
                f'Since the site said "too many requests", the pause between two requests is '
                f"{count.min_pause():.0f} seconds."
            )
    except StopCollecting as stop:
        return str(stop)
    return "\n".join(lines)


def cooldown_line(count: RequestCount) -> str:
    until = count.not_before()
    return (
        f'{SITE} said "too many requests". The cooldown runs until '
        f"{until.strftime('%Y-%m-%d %H:%M:%S')} UTC, {count.wait_left() / 60:.0f} minute(s) from "
        "now. Nothing is sent before."
    )


def refusal_line(refused: dict) -> str:
    """What to tell a person when the site has said no and nobody has decided how to go on."""
    wait = refused.get("asked_to_wait")
    return (
        f"{SITE} refused a request on {refused['at']} (answer {refused['status']}"
        + (f", it asks to wait: {wait}" if wait else "")
        + "). The tool sends nothing to this site until the maintainer has decided how to go "
        'on. Then: python -m hackathon_memory.collect ethglobal --after-refusal "<the decision>"'
    )


def clear_refusal(settings: Settings, decision: str) -> list[str]:
    """The maintainer decided how to go on after a no of the site. Sends no request.

    Returns what holds from now on, in plain words.
    """
    if not decision.strip():
        raise CollectorRefused("Say in a few words what was decided, and by whom.")
    count = request_count(data_paths(settings))
    try:
        if not count.clear_refusal(decision.strip()):
            return ["There is no refusal to clear."]
        lines = ["The refusal is cleared, and the decision is written next to the count."]
        if count.wait_left() > 0:
            lines.append(cooldown_line(count))
        return lines
    except StopCollecting as stop:
        raise CollectorRefused(str(stop)) from None
