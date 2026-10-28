"""GitHub's answers, asked again as the repositories change (design 7.3, 25 October 2026).

A repository lives on after its event: a team pushes, rewrites its README, renames the
repository, makes it private or deletes it. So an answer of GitHub is asked again once it is old.

The first answer for each address stays where it was saved, as every saved answer does
(collect/rawstore.py). An answer asked again is saved in a folder of its own, one for its address
and its moment:

    data/raw/api.github.com/again/<key of the address>/<moment>/<key><suffix>, and its .meta.json

The newest answer is the one that every step and screen reads (`Answers.load`).

A request asked again carries the ETag of the newest answer (If-None-Match). GitHub answers 304
when nothing changed, and "making a conditional request does not count against your primary
rate limit if a 304 response is returned" (GitHub's "Best practices for using the REST API",
read on 25 October 2026). A 304 is saved too, as a record with no body, so the tool knows the
newest moment at which GitHub confirmed an answer: `Answers.load` gives the newest answer that
holds content, with that moment as its time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

from hackathon_memory.collect.polite import FetchFailed, FetchResult, PoliteClient, StopCollecting
from hackathon_memory.collect.rawstore import RawStore, SavedPage, page_key

AGAIN = "again"
NOT_MODIFIED = 304

# What is saved of an answer: the page, the facts of the answer, and the numbers of what was
# taken out before saving (or None). The same as collect/github_once.py.
Keep = Callable[[FetchResult], tuple[bytes, dict, dict | None]]


def moment_of(stamp: str) -> datetime:
    """A time as the saved answers write it ("2026-10-25T10:15:00Z")."""
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _as_of(saved: SavedPage, confirmed: str | None) -> SavedPage:
    """The answer, with the newest moment at which GitHub confirmed it as its time. The time of
    the answer itself stays as "answered_at". Nothing on disk changes."""
    if confirmed is None or confirmed <= saved.meta["fetched_at"]:
        return saved
    meta = {**saved.meta, "answered_at": saved.meta["fetched_at"], "fetched_at": confirmed}
    return replace(saved, meta=meta)


class Answers(RawStore):
    """GitHub's saved answers: the first ones, and those asked again since. Reads give the
    newest; `save` keeps the first answer of an address, `store_for` makes the folder of an
    answer asked again."""

    def _moments(self, url: str) -> list[Path]:
        folder = self.folder / AGAIN / page_key(url)
        if not folder.is_dir():
            return []
        return sorted((one for one in folder.iterdir() if one.is_dir()), reverse=True)

    def load(self, url: str, suffix: str = ".html") -> SavedPage | None:
        """The newest answer for `url` that holds content, with the newest moment at which GitHub
        gave or confirmed it as its time; None when it was never asked for."""
        confirmed: str | None = None
        for folder in self._moments(url):
            saved = RawStore(folder).load(url, suffix)
            if saved is None:
                continue  # a crash left half an answer: the older ones count
            confirmed = confirmed or saved.meta["fetched_at"]
            if saved.meta["status"] != NOT_MODIFIED:
                return _as_of(saved, confirmed)
        first = super().load(url, suffix)
        return _as_of(first, confirmed) if first is not None else None

    def store_for(self, fetch: FetchResult) -> RawStore:
        """A new folder for an answer asked again, named after its moment."""
        base = self.folder / AGAIN / page_key(fetch.url)
        name = moment_of(fetch.fetched_at).strftime("%Y%m%dT%H%M%SZ")
        folder, number = base / name, 1
        while folder.exists():  # two answers in one second: the later one sorts after
            number += 1
            folder = base / f"{name}-{number}"
        return RawStore(folder)


def etag_of(saved: SavedPage) -> str | None:
    """The ETag that GitHub gave with an answer, when it was kept."""
    return (saved.meta.get("answer") or {}).get("etag") or None


@dataclass
class AgainRun:
    """What a run that asked GitHub again did."""

    repositories: int = 0
    fresh: int = 0  # its newest answer is younger than the age
    never_asked: int = 0  # the steps ask for it the first time
    asked: int = 0
    unchanged: int = 0  # 304, or an answer that keeps the same
    changed: list[str] = field(default_factory=list)  # the repositories whose answer changed
    answered: list[str] = field(default_factory=list)  # the repositories asked, answered or 304
    failed: int = 0
    left_for_later: int = 0
    stopped: str | None = None  # why the run stopped before the end, in plain words
    by_status: dict[str, int] = field(default_factory=dict)


def ask_again(
    client: PoliteClient,
    answers: Answers,
    repositories: Iterable[str],
    *,
    address_of: Callable[[str], str],
    keep: Keep,
    status_of: Callable[[SavedPage], str],
    statuses: Iterable[str],
    suffix: str,
    collector: str,
    older_than: timedelta,
    now: Callable[[], datetime],
    limit: int | None = None,
) -> AgainRun:
    """Ask again, one after the other, for the address of every repository whose newest answer
    is older than `older_than`, with the ETag of that answer. An address that was never asked
    for is left to the steps, which ask for it the first time. With `limit`, at most that many
    requests in this run. A stop (the switch, a no, too many requests, the limit of the day) ends
    the run, and what was saved stays saved."""
    repositories = list(repositories)
    run = AgainRun(repositories=len(repositories), by_status=dict.fromkeys(statuses, 0))
    for repository in repositories:
        address = address_of(repository)
        newest = answers.load(address, suffix)
        if newest is None:
            run.never_asked += 1
            continue
        if now() - moment_of(newest.meta["fetched_at"]) < older_than:
            run.fresh += 1
            continue
        if run.stopped is not None or (limit is not None and run.asked >= limit):
            run.left_for_later += 1
            continue
        etag = etag_of(newest)
        try:
            fetch = client.get(address, etag=etag)
        except FetchFailed:
            run.asked += 1
            run.failed += 1
            continue
        except StopCollecting as stop:
            run.stopped = str(stop)
            run.left_for_later += 1
            continue
        run.asked += 1
        run.answered.append(repository)
        store = answers.store_for(fetch)
        if fetch.status == NOT_MODIFIED:
            store.save(fetch, b"", received=b"", collector=collector, answer={"etag": etag},
                       suffix=suffix)  # fmt: skip
            run.unchanged += 1
            continue
        body, facts, taken_out = keep(fetch)
        if fetch.etag:
            facts = {**facts, "etag": fetch.etag}
        saved = store.save(fetch, body, received=fetch.body, collector=collector,
                           team_cut=taken_out, answer=facts, suffix=suffix)  # fmt: skip
        status = status_of(saved)
        run.by_status[status] = run.by_status.get(status, 0) + 1
        if (saved.meta["sha256"], saved.meta["status"]) == (newest.meta["sha256"],
                                                            newest.meta["status"]):  # fmt: skip
            run.unchanged += 1
        else:
            run.changed.append(repository)
    return run
