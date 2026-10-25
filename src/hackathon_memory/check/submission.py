"""Check one submission: its code, its Hedera proof, its life, and whether it was seen before
(design 12.1, screen S3, with the rules of 7.2, 7.3, 7.4 and 8.4).

A judge pastes the link of a repository and, if they want, the hackathon it was sent to.
Programs read everything here, and no model writes anything:

* GitHub's API gives the dates of the code and the README, through the polite client of the
  pipeline (collect/github.py): the tool's name and contact address in every request, the pause,
  the limit counted on disk and the switch COLLECT_GITHUB. An answer that was saved before, also
  for a project of the collection, is read again and never asked twice.
* The Hedera IDs of the README are found by the parser's rules (parse/hedera_ids.py). The mirror
  node is asked about each one, on the network that the README names or on both, as the step of
  the pipeline asks (check/asking.py), and the proof rule judges it against the window of the
  event (check/proof.py).
* The life rule (check/life.py) reads the last push of the code and the last activity of the
  submission's own IDs: those that no project with other code names.
* What the code says about Hedera (design 7.3, collect/github_code.py): the saved reading of the
  repository's archive, or one made now within the limits of a check (50 MB, 30 seconds).
* "Seen before" (design 8.4, search/seen.py): the projects of the collection with the same
  repository, or with the same Hedera ID on the same network that the ledger found, unless the
  ID is a shared service.
* The ledger story (design 7.5): the history of the README's own IDs whose kind fits, read from
  the mirror node and kept, so that a second check within MAX_AGE reads it from the table, set
  side by side with the README's words and what the code calls.

At most MAX_IDS IDs are asked about, the first ones of the README: each one takes up to eight
questions of the mirror node, and a person waits for the answer.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from hackathon_memory.check import asking
from hackathon_memory.check.history import read_history
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.life import Life, life_of
from hackathon_memory.check.numbers import Numbers
from hackathon_memory.check.proof import (
    NO_ID_GIVEN,
    ORDER,
    PROOF_FOUND,
    WINDOW_NOT_KNOWN,
    Window,
    best,
    counts_from_the_code,
    judge,
    window_of,
)
from hackathon_memory.check.story import (
    OwnId,
    Story,
    merged,
    services_in_code,
    set_up_in_code,
    story_of,
)
from hackathon_memory.collect.github import GitHubClient, repository_of
from hackathon_memory.collect.github_code import CodeRead, read_code_now, saved_code
from hackathon_memory.collect.github_commits import Version, fetch_versions, saved_version
from hackathon_memory.collect.github_facts import FOUND as CODE_FOUND
from hackathon_memory.collect.github_facts import RepositoryFacts, fetch_facts, saved_facts
from hackathon_memory.collect.github_once import AnswersRun
from hackathon_memory.collect.github_readmes import FOUND as README_FOUND
from hackathon_memory.collect.github_readmes import Readme, fetch_readmes, saved_readme
from hackathon_memory.collect.polite import PoliteClient
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.code_ids import CodeIdStore
from hackathon_memory.db.history import KINDS_THAT_FIT, HistoryStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.hedera import registry
from hackathon_memory.hedera.mirror import MirrorError, MirrorNode
from hackathon_memory.parse.hedera_code import CodeScan
from hackathon_memory.parse.hedera_ids import ACCOUNT, FoundId, find_ids
from hackathon_memory.search import seen

MAX_IDS = 5
# The own IDs of the code that a check asks the ledger about, the ones in the most files first: a
# person waits, and each one can take two questions.
MAX_CODE_IDS = 10
NETWORKS_WHEN_OPEN = ("testnet", "mainnet")  # as the step of the pipeline asks
MAX_AGE = timedelta(days=7)  # an answer of the node younger than this is taken from the table
NOT_ASKED = "not_asked"  # no network could be asked about the ID just now
# The steps of a check, as it reports them while it runs (web/checks.py), and their states:
# SAVED is done at once from what the tool kept, SKIPPED is a step with nothing to read.
GITHUB, CODE, LEDGER, HISTORY = "github", "code", "ledger", "history"
RUNNING, DONE, SAVED, SKIPPED = "running", "done", "saved", "skipped"
# The IDs of the ledger story: their kind fits the README. Without a hackathon, the dates of an
# ID are not judged, and its kind may still fit.
STORY_STATUSES = (*KINDS_THAT_FIT, WINDOW_NOT_KNOWN)
LONGEST_TEXT = 4000  # the characters of the README that the search by meaning reads, as an idea

GITHUB_AWAY = "GitHub did not answer. Try again in a moment."
NO_SUCH_CODE = (
    "GitHub has no public repository at this link: it was deleted, made private, or never "
    "existed. Check the link."
)
BLOCKED_CODE = "GitHub blocks this repository, so its code cannot be read."

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,}).*?^ {0,3}\1[ \t]*$", re.MULTILINE | re.DOTALL)
_IMAGE = re.compile(r"!\[[^\]\n]*\]\([^)\n]*\)")
_LINK = re.compile(r"\[([^\]\n]*)\]\([^)\n]*\)")
_TAG = re.compile(r"<[^>\n]+>")
_ADDRESS = re.compile(r"https?://\S+")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*")
_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_CELL = re.compile(r"\s*\|\s*")
_RULE = re.compile(r"^[\s:·-]*$")  # a row of dashes, such as the one under a table's head


@dataclass(frozen=True)
class EventDays:
    """The event that a submission was sent to: from the tables, or with days typed in."""

    name: str
    starts_at: datetime | None
    ends_on: date | None
    typed: bool = False
    key: str = ""  # how the register names it: "site/short-name", or "days/first/last"

    @property
    def window(self) -> Window | None:
        return window_of(self.starts_at, self.ends_on)


@dataclass(frozen=True)
class IdResult:
    """One ID of the README, with the status that counts and the facts behind it."""

    found: FoundId
    status: str
    network: str | None  # the network of the status that counts; None when none was asked
    facts: LedgerFacts | None
    shared: bool = False  # a shared service: many teams name it (design 8.4)
    named_elsewhere: bool = False  # a project with other code names it: not a sign of life
    in_code: str | None = None  # an ID of the code: the first file where it stands


@dataclass(frozen=True)
class SeenBefore:
    project_id: int
    by: str  # "repository", or the network and the ID that the two share ("testnet:0.0.5")


@dataclass
class SubmissionCheck:
    repository: str
    event: EventDays | None  # None: no hackathon given, so the dates are shown and not judged
    code: RepositoryFacts | None = None
    readme: Readme | None = None
    version: Version | None = None  # the newest commit, which a registration names
    hedera_code: CodeRead | None = None  # what the code says about Hedera
    ids: list[IdResult] = field(default_factory=list)
    ids_left_out: int = 0
    proof: str = NO_ID_GIVEN
    life: Life | None = None
    last_own_activity: datetime | None = None  # the newest activity of its own IDs, a sign
    ledger_read_at: datetime | None = None  # the oldest answer of the mirror node about them
    seen: list[SeenBefore] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    story: Story | None = None  # the ledger story of its own IDs (design 7.5), or None
    code_ids_not_judged: int = 0  # own IDs of the code, not weighed for want of a hackathon

    @property
    def proven_by_code_only(self) -> bool:
        """True when only IDs of the code prove the use of Hedera (design 7.3)."""
        proofs = [one for one in self.ids if one.status == PROOF_FOUND]
        return bool(proofs) and all(one.in_code for one in proofs)

    @property
    def readme_text(self) -> str:
        return self.readme.text if self.readme and self.readme.status == README_FOUND else ""


def repository_link(text: str) -> str | None:
    """The link of a GitHub repository in one spelling, from what a person pasted: with or
    without "https://", and with a path after the name of the repository. None for another
    link."""
    text = text.strip()
    if text and "://" not in text:
        text = f"https://{text}"
    return repository_of(text)


def typed_days(starts: str, ends: str) -> tuple[date, date] | None:
    """The first and the last day that a person typed, or None when they do not make a time."""
    try:
        first, last = date.fromisoformat(starts), date.fromisoformat(ends)
    except ValueError:
        return None
    if not (2015 <= first.year <= 2100 and first <= last):
        return None
    return first, last


def event_of_days(first: date, last: date) -> EventDays:
    return EventDays("the days typed in", datetime.combine(first, time.min, tzinfo=UTC), last,
                     typed=True, key=registry.days_key(first, last))  # fmt: skip


def read_code(
    client: PoliteClient | None,
    store: RawStore,
    repository: str,
    *,
    collector: str,
) -> tuple[RepositoryFacts | None, Readme | None, Version | None, list[str]]:
    """The facts, the README and the version of a repository: the saved answers, or asked for
    once now. With no client, only what was saved. Returns them with what went wrong, in plain
    words."""
    problems: list[str] = []
    facts, readme = saved_facts(store, repository), saved_readme(store, repository)
    version = saved_version(store, repository)
    if client is not None and facts is None:
        _note(fetch_facts(client, store, [repository], collector=collector), problems)
        facts = saved_facts(store, repository)
    code_is_there = facts is not None and facts.status == CODE_FOUND
    if client is not None and readme is None and code_is_there:
        _note(fetch_readmes(client, store, [repository], collector=collector), problems)
        readme = saved_readme(store, repository)
    if client is not None and version is None and code_is_there:
        _note(fetch_versions(client, store, [repository], collector=collector), problems)
        version = saved_version(store, repository)
    return facts, readme, version, problems


def read_again(
    client: PoliteClient, store: RawStore, repository: str, *, collector: str
) -> tuple[Readme | None, Version | None, list[str]]:
    """The README and the version of a repository, asked for now, for a registration: it needs
    the team's line in the README, and stamps the newest version (design 9.2). `store` is a new
    one, since a saved answer is never replaced."""
    problems: list[str] = []
    _note(fetch_readmes(client, store, [repository], collector=collector), problems)
    _note(fetch_versions(client, store, [repository], collector=collector), problems)
    return saved_readme(store, repository), saved_version(store, repository), problems


def _note(done: AnswersRun, problems: list[str]) -> None:
    if done.stopped:
        problems.append(f"GitHub was not asked: {done.stopped}")
    elif done.failed and GITHUB_AWAY not in problems:
        problems.append(GITHUB_AWAY)


def judge_ids(
    found: list[FoundId],
    window: Window | None,
    mirrors: Mapping[str, MirrorNode],
    ledger: LedgerStore,
    *,
    now: Callable[[], datetime],
    counts: Counter[str] | None = None,
) -> list[IdResult]:
    """The status of each ID by the proof rule, on the network that its text names, or the best
    of both networks. An ID that no network could be asked about is NOT_ASKED."""
    counts = Counter() if counts is None else counts
    results = []
    for item in found:
        on: dict[str, tuple[str, LedgerFacts]] = {}
        for network in [item.network] if item.network else NETWORKS_WHEN_OPEN:
            mirror = mirrors.get(network)
            if mirror is None:
                continue
            try:
                facts = asking.facts_of(ledger, mirror, item.entity_id, item.said_kind,
                                        max_age=MAX_AGE, now=now, counts=counts)  # fmt: skip
                used = asking.used_inside(ledger, mirror, facts, window, now=now, counts=counts)
            except MirrorError:
                counts["errors_of_the_node"] += 1
                continue
            on[network] = (judge(facts, item.said_kind, window, used), facts)
        if not on:
            results.append(IdResult(item, NOT_ASKED, None, None))
            continue
        network = min(on, key=lambda name: ORDER.index(on[name][0]))
        results.append(IdResult(item, on[network][0], network, on[network][1]))
    return results


def judge_code_ids(
    scan: CodeScan | None,
    readme: list[FoundId],
    window: Window | None,
    mirrors: Mapping[str, MirrorNode],
    ledger: LedgerStore,
    code_ids: CodeIdStore,
    repository: str,
    *,
    now: Callable[[], datetime],
    counts: Counter[str] | None = None,
) -> tuple[list[IdResult], int]:
    """The IDs of the code that count for the submission (design 7.3): its own (no page or README
    of the collection names one, nor the code of another repository, nor its own README) and made
    on the ledger during the hackathon (counts_from_the_code). Without a hackathon none can be
    weighed: then the number of its own IDs of the code comes back, to be said."""
    counts = Counter() if counts is None else counts
    if scan is None or not scan.ids:
        return [], 0
    named = {one.entity_id for one in readme}
    candidates = sorted((one for one in scan.ids.values() if one.entity_id not in named),
                        key=lambda one: -one.seen.files)  # fmt: skip
    elsewhere = code_ids.named_elsewhere([one.entity_id for one in candidates], repository)
    own = [one for one in candidates if one.entity_id not in elsewhere]
    if window is None:
        return [], len({one.entity_id for one in own})
    numbers = Numbers(ledger.dated_numbers())
    results = []
    for one in own[:MAX_CODE_IDS]:
        for network in [one.network] if one.network else NETWORKS_WHEN_OPEN:
            mirror = mirrors.get(network)
            if mirror is None or not numbers.could_be_made_inside(one.entity_id, network, window):
                continue
            try:
                # an account first: most IDs of the code are accounts (pipeline/code_ids.py)
                facts = asking.facts_of(ledger, mirror, one.entity_id, ACCOUNT, max_age=MAX_AGE,
                                        now=now, counts=counts)  # fmt: skip
            except MirrorError:
                counts["errors_of_the_node"] += 1
                continue
            if counts_from_the_code(facts, window):
                found = FoundId(one.entity_id, network, None, "")
                results.append(IdResult(found, PROOF_FOUND, network, facts,
                                        in_code=one.seen.examples[0]))  # fmt: skip
                break
    return results, 0


def histories(
    ids: list[IdResult],
    mirrors: Mapping[str, MirrorNode],
    store: HistoryStore,
    *,
    now: Callable[[], datetime],
    counts: Counter[str] | None = None,
) -> tuple[list[OwnId], list[tuple[str, datetime, str, bool]]]:
    """The own IDs of a README whose kind fits, each on the network of its status, and the
    events of their histories: kept ones younger than MAX_AGE, or read now and kept. An ID that
    a project with other code names, or a shared service, is not the team's own (design 8.4)."""
    counts = Counter() if counts is None else counts
    own: list[OwnId] = []
    events: list[tuple[str, datetime, str, bool]] = []
    for one in ids:
        if (one.status not in STORY_STATUSES or one.network is None or one.facts is None
                or one.shared or one.named_elsewhere):  # fmt: skip
            continue
        entity, network, kind = one.found.entity_id, one.network, one.facts.kind
        kept = store.saved(entity, network, since=now() - MAX_AGE)
        if kept is None:
            mirror = mirrors.get(network)
            try:
                if mirror is None:
                    raise MirrorError(f"no mirror node for {network}")
                read = read_history(mirror, one.facts.ledger_id or entity, kind or "",
                                    made_at=one.facts.created_at)  # fmt: skip
            except MirrorError:
                counts["histories_not_read"] += 1
                own.append(OwnId(entity, network, kind, None))
                continue
            kept = read, now()
            store.save(entity, network, kind or "", read, kept[1])
            counts["histories_read_now"] += 1
        else:
            counts["histories_from_the_table"] += 1
        history, asked_at = kept
        own.append(OwnId(entity, network, kind, asked_at, history.cut))
        events += [(stamp, datetime.fromtimestamp(float(stamp), tz=UTC), service, kind == ACCOUNT)
                   for stamp, service in history.events.items()]  # fmt: skip
    return own, events


def story_of_check(check: SubmissionCheck, own: list[OwnId], events: list[tuple]) -> Story | None:
    """The ledger story of a checked submission: its README in the place of the page, and the
    days of its hackathon when one is given. None when the README names no own ID that fits."""
    if not own:
        return None
    scan = check.hedera_code.scan if check.hedera_code is not None else None
    found = [(one.kind, one.name) for one in scan.found()] if scan is not None else None
    event = check.event
    return story_of(own, merged(events), readme_prose(check.readme_text),
                    services_in_code(found) if found is not None else None,
                    starts_at=event.starts_at if event is not None else None,
                    ends_on=event.ends_on if event is not None else None,
                    set_up=set_up_in_code(found or []))  # fmt: skip


def readme_prose(text: str) -> str:
    """The prose of a README, line by line, for the ledger story (design 7.5): no code, no images,
    no addresses, no HTML, links as their words, and none of the marks of Markdown (headings,
    lists, bold, code quotes, the bars of a table). A word in an address or a block of code does
    not name a service."""
    text = _FENCE.sub(" ", text)
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _ADDRESS.sub(" ", _TAG.sub(" ", text))
    lines = []
    for line in text.splitlines():
        line = _LIST_MARK.sub("", _HEADING.sub("", line))
        line = line.replace("**", "").replace("__", "").replace("`", "")
        line = _CELL.sub(" · ", line.strip().strip("|"))
        lines.append("" if _RULE.match(line) else " ".join(line.split()))
    return "\n".join(lines)


def readme_words(text: str) -> str:
    """The words of a README for the search by meaning: no code, no images, no addresses, no
    HTML, and at most LONGEST_TEXT characters."""
    text = _FENCE.sub(" ", text)
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _ADDRESS.sub(" ", _TAG.sub(" ", text))
    return " ".join(text.split())[:LONGEST_TEXT]


def check_submission(
    conninfo: str,
    repository: str,
    event: EventDays | None,
    *,
    client: GitHubClient | None,
    store: RawStore,
    collector: str,
    mirrors: Mapping[str, MirrorNode],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    problems: list[str] | None = None,
    progress: Callable[[str, str], None] = lambda step, state: None,
) -> SubmissionCheck:
    """Check the repository, for the hackathon when one is given: without one, the dates of the
    IDs and of the code are shown and not judged. `problems` holds what the caller already knows
    went wrong, such as a GitHub that may not be asked now. `progress` hears each step start and
    end, with its state."""
    check = SubmissionCheck(repository, event, problems=list(problems or []))
    progress(GITHUB, RUNNING)
    kept = [saved_facts(store, repository), saved_readme(store, repository),
            saved_version(store, repository)]  # fmt: skip
    check.code, check.readme, check.version, asked = read_code(client, store, repository,
                                                               collector=collector)  # fmt: skip
    progress(GITHUB, SAVED if all(one is not None for one in kept) else DONE)
    check.problems.extend(asked)
    if check.code is not None and check.code.status != CODE_FOUND:
        check.problems.append(NO_SUCH_CODE if check.code.status != "blocked" else BLOCKED_CODE)
        progress(CODE, SKIPPED)
    elif check.code is not None:
        progress(CODE, RUNNING)
        read_before = saved_code(store, repository) is not None
        check.hedera_code, trouble = read_code_now(client, store, repository, collector=collector)
        check.problems.extend([trouble] if trouble else [])
        progress(CODE, SAVED if read_before else DONE)
    else:
        progress(CODE, SKIPPED)
    found = find_ids(check.readme_text)
    check.ids_left_out = max(0, len(found) - MAX_IDS)
    window = event.window if event is not None else None
    scan = check.hedera_code.scan if check.hedera_code is not None else None
    progress(LEDGER, RUNNING if found or (scan and scan.ids) else SKIPPED)
    asked_node: Counter[str] = Counter()
    judged = judge_ids(found[:MAX_IDS], window, mirrors, LedgerStore(conninfo), now=now,
                       counts=asked_node)  # fmt: skip
    from_code, check.code_ids_not_judged = judge_code_ids(
        scan, found, window, mirrors, LedgerStore(conninfo), CodeIdStore(conninfo), repository,
        now=now, counts=asked_node,
    )  # fmt: skip
    if found or (scan and scan.ids):
        progress(LEDGER, DONE if asked_node["answers_from_the_node"] else SAVED)
    keys = [f"{one.network}:{one.found.entity_id}" for one in judged
            if one.network and one.status in seen.CONFIRMED]  # fmt: skip
    known = seen.submission_matches(conninfo, repository, keys)
    check.ids = [
        IdResult(one.found, one.status, one.network, one.facts,
                 shared=f"{one.network}:{one.found.entity_id}" in known.shared,
                 named_elsewhere=one.found.entity_id in known.named_by_other_code)
        for one in judged
    ] + from_code  # fmt: skip
    if found and all(one.status == NOT_ASKED for one in check.ids):
        check.problems.append("The mirror node of Hedera did not answer. Try again in a moment.")
    check.proof = best([one.status for one in check.ids if one.status != NOT_ASKED])
    if found and check.proof == NO_ID_GIVEN:
        check.proof = NOT_ASKED
    mine = [one.facts for one in check.ids if one.facts is not None
            and one.status in seen.CONFIRMED and not one.named_elsewhere]  # fmt: skip
    own = [facts.last_activity_at for facts in mine if facts.last_activity_at]
    check.ledger_read_at = min((facts.asked_at for facts in mine), default=None)
    pushed = check.code.pushed_at if check.code and check.code.status == CODE_FOUND else None
    check.last_own_activity = max(own) if own else None
    check.life = life_of(event_end=event.ends_on if event is not None else None, last_push=pushed,
                         last_ledger_activity=check.last_own_activity, now=now())  # fmt: skip
    check.seen = [SeenBefore(pid, "repository") for pid in known.same_repository]
    for key, projects in known.same_id.items():
        for pid in projects:
            if all(one.project_id != pid for one in check.seen):
                check.seen.append(SeenBefore(pid, key))
    progress(HISTORY, RUNNING)
    read: Counter[str] = Counter()
    own, events = histories(check.ids, mirrors, HistoryStore(conninfo), now=now, counts=read)
    progress(HISTORY, SKIPPED if not own else DONE if read["histories_read_now"] else SAVED)
    check.story = story_of_check(check, own, events)
    return check
