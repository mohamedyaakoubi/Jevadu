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
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hackathon_memory.collect.github import GitHubClient, api_message, archive_address
from hackathon_memory.collect.github_once import AnswersRun, ask_each
from hackathon_memory.collect.polite import FetchFailed, FetchResult, StopCollecting
from hackathon_memory.collect.rawstore import RawStore, SavedPage
from hackathon_memory.parse.hedera_code import (
    BROKE_OFF,
    LIMIT_BYTES,
    LIMIT_SECONDS,
    CodeScan,
    scan_archive,
)

SUFFIX = ".json"
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


def saved_code(store: RawStore, repository: str) -> CodeRead | None:
    """The saved reading of a repository, or None when it was never read."""
    saved = store.load(archive_address(repository), SUFFIX)
    return read_saved(saved) if saved is not None else None


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


def read_code_now(
    client: GitHubClient | None,
    store: RawStore,
    repository: str,
    *,
    collector: str,
) -> tuple[CodeRead | None, str | None]:
    """The reading of one repository for the check of a submission: the saved one, or read now
    within the limits of a check. With no client, only the saved one. Returns it with what went
    wrong, in plain words. A reading that a limit cut is shown and not saved."""
    known = saved_code(store, repository)
    if known is not None or client is None:
        return known, None
    address = archive_address(repository)
    started = client.clock()
    try:
        fetch, scan = client.read_archive(
            address, scan_archive, max_bytes=LIVE_MAX_BYTES, seconds=LIVE_SECONDS
        )
    except FetchFailed:
        return None, GITHUB_AWAY
    except StopCollecting as stop:
        return None, f"GitHub was not asked for the code: {stop}"
    if scan is not None and scan.partial in (LIMIT_BYTES, LIMIT_SECONDS):
        return CodeRead(PARTIAL, scan, fetch.fetched_at, saved=False), None
    if scan is not None and scan.partial == BROKE_OFF:
        return None, BROKE_OFF_NOW
    took = client.clock() - started
    return save_reading(store, fetch, scan, collector, seconds=took), None
