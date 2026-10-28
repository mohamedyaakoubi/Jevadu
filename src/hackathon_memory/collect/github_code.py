"""Where Hedera stands in the code of each repository, read once from its archive (design 7.3).

Two requests for each repository, one after the other: GitHub's API answers with the address of
the archive of the default branch, and the archive is downloaded from GitHub's archive host as a
stream. It is read on this computer, file after file (parse/hedera_code.py), and nothing of it is
kept: only what was found is saved, as a small record, with the fingerprint of the archive. A
package file can name its authors, and a settings file can hold a key, so no file is kept.

* An archive read to its end: saved, status READ.
* An archive that GitHub sent broken: saved, status PARTIAL, with the reason.
* A download that broke off on the way: not saved; a later run asks again.
* No such repository (404), or one that GitHub blocks: the answer is saved as it came.

The step of the pipeline reads every repository whole, with no limit. The check of a
submission reads with a limit of bytes and of seconds, since a person waits, and saves only a
reading that reached the end: the step reads a large repository whole later.

A newer reader finds more (FORMAT of parse/hedera_code.py: the IDs of the code since format 3).
A repository read by an older reader is read again, once, when asked for (fetch_code_again, and
the check of a submission). A saved reading is never edited, so a reading made again is saved in
a folder of its own, one for each version of the reader, and the newest reading that holds code
is the one used.

A repository whose newest commit is not the commit of its newest reading is read again too
(read_new_commits, 25 October 2026): its reading is saved with the answers asked again
(collect/answers.py), and the newest reading counts by its time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hackathon_memory.collect.answers import AgainRun, Answers
from hackathon_memory.collect.github import GitHubClient, api_message, archive_address
from hackathon_memory.collect.github_commits import FOUND as VERSION_FOUND
from hackathon_memory.collect.github_commits import saved_version
from hackathon_memory.collect.github_once import AnswersRun, ask_each
from hackathon_memory.collect.polite import FetchFailed, FetchResult, StopCollecting
from hackathon_memory.collect.rawstore import RawStore, SavedPage
from hackathon_memory.parse.hedera_code import (
    BROKE_OFF,
    FORMAT,
    LIMIT_BYTES,
    LIMIT_SECONDS,
    CodeScan,
    scan_archive,
)

SUFFIX = ".json"
FIRST_READ_AGAIN = 3  # the first version of the reader whose readings were made again
READ = "read"
PARTIAL = "partial"
GONE = "gone"
BLOCKED = "blocked"
STATUSES = (READ, PARTIAL, GONE, BLOCKED)

# The check of a submission: 95 of 100 repositories of the collection are smaller than 52 MB
# (their sizes on GitHub, 21 October 2026), and a person waits for the answer.
LIVE_MAX_BYTES = 50_000_000
LIVE_SECONDS = 30.0

BROKE_OFF_NOW = "The download of the code broke off. Check the repository again in a moment."
GITHUB_AWAY = "GitHub did not send the code of the repository just now."


@dataclass(frozen=True)
class CodeRead:
    """What the code of a repository says about Hedera, or why it could not be read."""

    status: str  # READ, PARTIAL, GONE or BLOCKED
    scan: CodeScan | None  # None for GONE and BLOCKED
    fetched_at: str
    saved: bool = True  # False: read for a check within its limits, and not kept


def read_saved(saved: SavedPage) -> CodeRead:
    """What a saved record says about a repository."""
    status = saved.meta["status"]
    if status != 200:
        return CodeRead(BLOCKED if status in (403, 451) else GONE, None, saved.meta["fetched_at"])
    scan = CodeScan.from_json(saved.read())
    return CodeRead(PARTIAL if scan.partial else READ, scan, saved.meta["fetched_at"])


def again_store(store: RawStore, version: int = FORMAT) -> RawStore:
    """Where the readings made again by the reader of `version` are saved."""
    return RawStore(store.folder / f"code-format-{version}")


def saved_code(store: RawStore, repository: str) -> CodeRead | None:
    """The newest saved reading of a repository that holds its code, else its newest reading, or
    None when it was never read. The readings made again for a newer reader and those of a newer
    commit (with Answers as `store`) count by their time."""
    address = archive_address(repository)
    found = [again_store(store, version).load(address, SUFFIX)
             for version in range(FORMAT, FIRST_READ_AGAIN - 1, -1)]  # fmt: skip
    found.append(store.load(address, SUFFIX))
    readings = [read_saved(saved) for saved in found if saved is not None]
    if not readings:
        return None
    with_code = [one for one in readings if one.scan is not None]
    return max(with_code or readings, key=lambda one: one.fetched_at)


def is_older(read: CodeRead | None) -> bool:
    """True for a reading of the code made by an older version of the reader."""
    return read is not None and read.scan is not None and read.scan.format < FORMAT


def save_reading(
    store: RawStore,
    fetch: FetchResult,
    scan: CodeScan | None,
    collector: str,
    *,
    seconds: float | None = None,
) -> CodeRead:
    """Save a reading, or the answer of the API when there is no archive, and read it back.
    `seconds` is how long the two requests and the reading took, pauses included: what a
    person waits for in a check."""
    if scan is None:  # GitHub said that there is no such repository, or that it is blocked
        saved = store.save(fetch, fetch.body, received=fetch.body, collector=collector,
                           answer={"message": api_message(fetch.body)}, suffix=SUFFIX)  # fmt: skip
    else:
        answer: dict[str, object] = {"archive_bytes": scan.archive_bytes}
        if seconds is not None:
            answer["seconds"] = round(seconds, 2)
        saved = store.save(fetch, scan.to_json(), received=b"",
                           received_sha256=scan.archive_sha256, collector=collector,
                           answer=answer, suffix=SUFFIX)  # fmt: skip
    return read_saved(saved)


def _reader(client: GitHubClient, store: RawStore, collector: str) -> Callable[[str], str | None]:
    """What reads one archive whole and saves the reading into `store`."""

    def ask(address: str) -> str | None:
        started = client.clock()
        fetch, scan = client.read_archive(address, scan_archive)
        if scan is not None and scan.partial == BROKE_OFF:
            return None  # not saved: a later run asks again
        took = client.clock() - started
        return save_reading(store, fetch, scan, collector, seconds=took).status

    return ask


def fetch_code(
    client: GitHubClient,
    store: RawStore,
    repositories: list[str],
    *,
    collector: str,
    limit: int | None = None,
) -> AnswersRun:
    """Read the archive of every repository that has no saved reading yet, one after the other
    and whole. With `limit`, at most that many in this run."""
    return ask_each(store, repositories, address_of=archive_address,
                    ask=_reader(client, store, collector), statuses=STATUSES, suffix=SUFFIX,
                    limit=limit)  # fmt: skip


def fetch_code_again(
    client: GitHubClient,
    store: RawStore,
    repositories: list[str],
    *,
    collector: str,
    limit: int | None = None,
) -> AnswersRun:
    """Read again, once and whole, the archive of every repository whose newest reading an older
    reader made, into the folder of this reader. With `limit`, at most that many in this run."""
    older = [one for one in repositories if is_older(saved_code(store, one))]
    again = again_store(store)
    return ask_each(again, older, address_of=archive_address,
                    ask=_reader(client, again, collector), statuses=STATUSES, suffix=SUFFIX,
                    limit=limit)  # fmt: skip


def read_code_now(
    client: GitHubClient | None,
    store: RawStore,
    repository: str,
    *,
    collector: str,
    commit: str | None = None,
) -> tuple[CodeRead | None, str | None]:
    """The reading of one repository for the check of a submission: the saved one, or read now
    within the limits of a check. With no client, only the saved one. Returns it with what went
    wrong, in plain words. A reading that a limit cut is shown and not saved. A reading that an
    older reader made is made again now, and kept when that fails; so is a reading of another
    commit than `commit`, the newest one, when `store` keeps the answers asked again."""
    known = saved_code(store, repository)
    stale = (isinstance(store, Answers) and commit is not None and known is not None
             and known.scan is not None and known.scan.commit not in (None, commit))  # fmt: skip
    older = is_older(known) or stale
    if (known is not None and not older) or client is None:
        return known, None
    address = archive_address(repository)
    started = client.clock()
    try:
        fetch, scan = client.read_archive(
            address, scan_archive, max_bytes=LIVE_MAX_BYTES, seconds=LIVE_SECONDS
        )
    except FetchFailed:
        return (known, None) if older else (None, GITHUB_AWAY)
    except StopCollecting as stop:
        return (known, None) if older else (None, f"GitHub was not asked for the code: {stop}")
    if scan is not None and scan.partial in (LIMIT_BYTES, LIMIT_SECONDS):
        return CodeRead(PARTIAL, scan, fetch.fetched_at, saved=False), None
    if older and (scan is None or scan.partial == BROKE_OFF):
        return known, None  # gone or broken now: the older reading stays the one used
    if scan is not None and scan.partial == BROKE_OFF:
        return None, BROKE_OFF_NOW
    took = client.clock() - started
    if stale and isinstance(store, Answers):  # a reading of a newer commit
        target: RawStore = store.store_for(fetch)
    else:
        target = again_store(store) if older else store
    return save_reading(target, fetch, scan, collector, seconds=took), None


def read_new_commits(
    client: GitHubClient,
    answers: Answers,
    repositories: list[str],
    *,
    collector: str,
    limit: int | None = None,
) -> AgainRun:
    """Read again, whole, the archive of every repository whose newest commit (its saved
    version) is not the commit of its newest reading, and save the reading with the answers
    asked again. A repository with no saved version, or with no code, is left alone. With
    `limit`, at most that many archives in this run."""
    run = AgainRun(repositories=len(repositories), by_status=dict.fromkeys(STATUSES, 0))
    for repository in repositories:
        version, known = saved_version(answers, repository), saved_code(answers, repository)
        if version is None or version.status != VERSION_FOUND or version.sha is None:
            run.never_asked += 1
            continue
        if known is not None and known.scan is not None and known.scan.commit == version.sha:
            run.fresh += 1
            continue
        if run.stopped is not None or (limit is not None and run.asked >= limit):
            run.left_for_later += 1
            continue
        started = client.clock()
        try:
            fetch, scan = client.read_archive(archive_address(repository), scan_archive)
        except FetchFailed:
            run.asked += 1
            run.failed += 1
            continue
        except StopCollecting as stop:
            run.stopped = str(stop)
            run.left_for_later += 1
            continue
        run.asked += 1
        if scan is not None and scan.partial == BROKE_OFF:
            run.failed += 1  # not saved: a later run asks again
            continue
        took = client.clock() - started
        read = save_reading(answers.store_for(fetch), fetch, scan, collector, seconds=took)
        run.by_status[read.status] = run.by_status.get(read.status, 0) + 1
        run.changed.append(repository)
    return run
