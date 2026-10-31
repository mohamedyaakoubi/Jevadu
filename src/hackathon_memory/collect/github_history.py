"""How a repository's code changed between two hackathons (design 8.7, 31 October 2026), asked
once through GitHub's API: the newest commit on or before a day, and the comparison of two commits.

* The newest commit on or before the last day of an event:
  GET /repos/{owner}/{repo}/commits?until={day}T23:59:59Z&per_page=1. "Only commits before this
  date will be returned" (GitHub's documentation, read on 31 October 2026). Kept as
  github_commits.py keeps the newest commit: its ID and its date, nothing else.
* The comparison of two commits: GET /repos/{owner}/{repo}/compare/{base}...{head}?per_page=1.
  Read on 31 October 2026: "status" ("ahead" when the second commit follows the first),
  "ahead_by", "behind_by", "total_commits", and "files", "up to 300 changed files for the entire
  comparison", each with its "additions" and "deletions". Kept: those numbers, how many files,
  and their lines added and removed. The commits of the answer hold the names and the addresses
  of the people who made them, and the files hold their names: none of it is kept (design rule
  11).

A commit carries the date that its maker gave it, and a history can be written again, so these
dates are the team's word, unlike the consensus time of the ledger. The card says so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from hackathon_memory.collect import github_commits
from hackathon_memory.collect.github import SITE, api_message
from hackathon_memory.collect.github_commits import STATUSES, SUFFIX, Version, kept_of, read_version
from hackathon_memory.collect.github_once import AnswersRun, fetch_once
from hackathon_memory.collect.polite import FetchResult, PoliteClient
from hackathon_memory.collect.rawstore import RawStore, SavedPage

FOUND, GONE, BLOCKED = github_commits.FOUND, github_commits.GONE, github_commits.BLOCKED
MOST_FILES = 300  # GitHub lists at most this many files of a comparison


def _owner_and_name(repository: str) -> tuple[str, str]:
    owner, name = repository.removeprefix("https://github.com/").split("/")
    return owner, name


def until_address(repository: str, day: date) -> str:
    """The address of the newest commit of a repository on or before `day`, in GitHub's API."""
    owner, name = _owner_and_name(repository)
    return (
        f"https://{SITE}/repos/{owner}/{name}/commits?until={day.isoformat()}T23:59:59Z&per_page=1"
    )


def compare_address(repository: str, base: str, head: str) -> str:
    """The address of the comparison of two commits of a repository, in GitHub's API."""
    owner, name = _owner_and_name(repository)
    return f"https://{SITE}/repos/{owner}/{name}/compare/{base}...{head}?per_page=1"


def compare_page(repository: str, base: str, head: str) -> str:
    """GitHub's own page of the same comparison, for a person."""
    return f"{repository}/compare/{base}...{head}"


def kept_change(fetch: FetchResult) -> tuple[bytes, dict, dict | None]:
    """What is saved of a comparison: its numbers only, the facts of the answer, and what was
    taken out."""
    if fetch.status != 200:
        return fetch.body, {"message": api_message(fetch.body)}, None
    try:
        answer = json.loads(fetch.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return b"{}", {"kept": "nothing", "why": "the answer is not JSON"}, None
    if not isinstance(answer, dict) or not isinstance(answer.get("total_commits"), int):
        return b"{}", {"kept": "nothing", "why": "no count of commits in the answer"}, None
    files = [one for one in answer.get("files") or [] if isinstance(one, dict)]
    kept = {
        "status": str(answer.get("status", "")),
        "ahead_by": answer.get("ahead_by"),
        "behind_by": answer.get("behind_by"),
        "total_commits": answer["total_commits"],
        "files": len(files),
        "additions": sum(one.get("additions", 0) for one in files),
        "deletions": sum(one.get("deletions", 0) for one in files),
    }
    taken_out = {"fields_dropped": len(set(answer) - set(kept)), "people_dropped": True,
                 "file_names_dropped": len(files)}  # fmt: skip
    return json.dumps(kept, sort_keys=True).encode("utf-8"), {}, taken_out


@dataclass(frozen=True)
class Change:
    """How the code changed from one commit to another, as GitHub counts it."""

    status: str  # "ahead" when the second commit follows the first
    commits: int
    files: int
    additions: int
    deletions: int

    @property
    def files_capped(self) -> bool:
        """GitHub lists at most 300 files, so the files and the lines are at least these."""
        return self.files >= MOST_FILES


def read_change(saved: SavedPage) -> Change | None:
    """What a saved comparison says, or None when it was not found or not read."""
    if saved.meta["status"] != 200:
        return None
    kept = json.loads(saved.read().decode("utf-8") or "{}")
    if not isinstance(kept.get("total_commits"), int):
        return None
    return Change(kept.get("status") or "", kept["total_commits"], int(kept.get("files") or 0),
                  int(kept.get("additions") or 0), int(kept.get("deletions") or 0))  # fmt: skip


def status_of_change(saved: SavedPage) -> str:
    status = saved.meta["status"]
    return FOUND if status == 200 else BLOCKED if status in (403, 451) else GONE


def saved_until(store: RawStore, repository: str, day: date) -> Version | None:
    """The saved newest commit on or before `day`, or None when it was never asked for."""
    saved = store.load(until_address(repository, day), SUFFIX)
    return read_version(saved) if saved is not None else None


def saved_change(store: RawStore, repository: str, base: str, head: str) -> Change | None:
    """The saved comparison of two commits, or None when it was never asked for or not found."""
    saved = store.load(compare_address(repository, base, head), SUFFIX)
    return read_change(saved) if saved is not None else None


def fetch_untils(client: PoliteClient, store: RawStore, wanted: list[tuple[str, date]], *,
                 collector: str, limit: int | None = None) -> AnswersRun:  # fmt: skip
    """Ask for the newest commit on or before each day of `wanted` that has none saved yet."""
    addresses = list(dict.fromkeys(until_address(repo, day) for repo, day in wanted))
    return fetch_once(client, store, addresses, address_of=lambda address: address, keep=kept_of,
                      status_of=lambda saved: read_version(saved).status, statuses=STATUSES,
                      suffix=SUFFIX, collector=collector, limit=limit)  # fmt: skip


def fetch_changes(client: PoliteClient, store: RawStore, wanted: list[tuple[str, str, str]], *,
                  collector: str, limit: int | None = None) -> AnswersRun:  # fmt: skip
    """Ask for each comparison of `wanted` (a repository, a commit and a later one) that has none
    saved yet."""
    addresses = list(dict.fromkeys(compare_address(*one) for one in wanted))
    return fetch_once(client, store, addresses, address_of=lambda address: address,
                      keep=kept_change, status_of=status_of_change, statuses=STATUSES,
                      suffix=SUFFIX, collector=collector, limit=limit)  # fmt: skip
