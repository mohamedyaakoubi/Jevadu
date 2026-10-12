"""Ask GitHub once for each repository, and save every answer (design 7.3).

The README of a repository and the facts of a repository are asked for in the same way: one
request for each repository, one after the other, and every answer saved, so that none is asked
for twice. What is kept of an answer differs, so each kind gives its own `keep`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from hackathon_memory.collect.polite import (
    FetchFailed,
    FetchResult,
    PoliteClient,
    StopCollecting,
)
from hackathon_memory.collect.rawstore import RawStore, SavedPage

# What is saved of an answer: the page, the facts of the answer, and the numbers of what was
# taken out before saving (or None).
Keep = Callable[[FetchResult], tuple[bytes, dict, dict | None]]


@dataclass
class AnswersRun:
    """What a run that asks GitHub did."""

    repositories: int = 0
    already_saved: int = 0
    asked: int = 0
    failed: int = 0
    left_for_later: int = 0
    stopped: str | None = None  # why the run stopped before the end, in plain words
    by_status: dict[str, int] = field(default_factory=dict)


def fetch_once(
    client: PoliteClient,
    store: RawStore,
    repositories: list[str],
    *,
    address_of: Callable[[str], str],
    keep: Keep,
    status_of: Callable[[SavedPage], str],
    statuses: Iterable[str],
    suffix: str,
    collector: str,
    limit: int | None = None,
) -> AnswersRun:
    """Ask for the address of every repository that has no saved answer yet, one after the other.

    With `limit`, at most that many are asked for in this run. An answer that fails is counted
    and asked for again by a later run. A stop (the switch, a no, too many requests) ends the
    run, and what was saved stays saved.
    """
    run = AnswersRun(repositories=len(repositories), by_status=dict.fromkeys(statuses, 0))
    for repository in repositories:
        address = address_of(repository)
        if store.has(address, suffix):
            run.already_saved += 1
            continue
        if run.stopped is not None or (limit is not None and run.asked >= limit):
            run.left_for_later += 1
            continue
        try:
            fetch = client.get(address)
        except FetchFailed:
            run.asked += 1
            run.failed += 1
            continue
        except StopCollecting as stop:
            run.stopped = str(stop)
            run.left_for_later += 1
            continue
        run.asked += 1
        body, facts, taken_out = keep(fetch)
        saved = store.save(
            fetch,
            body,
            received=fetch.body,
            collector=collector,
            team_cut=taken_out,
            answer=facts,
            suffix=suffix,
        )
        status = status_of(saved)
        run.by_status[status] = run.by_status.get(status, 0) + 1
    return run
