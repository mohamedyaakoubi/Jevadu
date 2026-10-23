"""The version of a repository's code, asked for once through GitHub's API (design 7.3 and 9.3):
the ID of the newest commit of its default branch, and the date of that commit.

One request for each repository: GET /repos/{owner}/{repo}/commits?per_page=1. Read on 18 October
2026, the answer is a list of one commit: its "sha", 40 letters computed from every file of that
version and its history, and "commit.committer.date". The same answer also holds the names and
the email addresses of the people who made the commit, its message, and their GitHub accounts.
None of it is kept (design rule 11): before an answer is saved, only the ID and the date stay.

* 200: the version.
* 409: the repository is empty and has no commit yet (GitHub's answer for an empty repository).
* 404: no such repository any more, or a private one.
* 403 or 451 with "Repository access blocked": blocked.

The register writes this ID next to the fingerprint of the link (hedera/registry.py), so a record
says which code existed, and not only which address.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from hackathon_memory.collect.github import SITE, api_message
from hackathon_memory.collect.github_once import AnswersRun, fetch_once
from hackathon_memory.collect.polite import FetchResult, PoliteClient
from hackathon_memory.collect.rawstore import RawStore, SavedPage

SUFFIX = ".json"
FOUND = "found"
EMPTY = "empty"  # 409: a repository with no commit
GONE = "gone"  # 404: deleted, made private, or never public
BLOCKED = "blocked"
STATUSES = (FOUND, EMPTY, GONE, BLOCKED)
_SHA = re.compile(r"^[0-9a-f]{40}$")


def commits_address(repository: str) -> str:
    """The address of the newest commit of a repository in GitHub's API."""
    owner, name = repository.removeprefix("https://github.com/").split("/")
    return f"https://{SITE}/repos/{owner}/{name}/commits?per_page=1"


def kept_of(fetch: FetchResult) -> tuple[bytes, dict, dict | None]:
    """What is saved of an answer: the ID and the date of the commit, the facts of the answer,
    and what was taken out."""
    if fetch.status != 200:
        return fetch.body, {"message": api_message(fetch.body)}, None
    try:
        answer = json.loads(fetch.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return b"{}", {"kept": "nothing", "why": "the answer is not JSON"}, None
    first = answer[0] if isinstance(answer, list) and answer else None
    sha = first.get("sha") if isinstance(first, dict) else None
    if not isinstance(sha, str) or not _SHA.match(sha):
        return b"{}", {"kept": "nothing", "why": "no commit ID in the answer"}, None
    committer = (first.get("commit") or {}).get("committer") or {}
    date = committer.get("date") if isinstance(committer, dict) else None
    kept = {"sha": sha, "date": date if isinstance(date, str) else None}
    taken_out = {"fields_dropped": len(set(first) - {"sha"}), "people_dropped": True}
    return json.dumps(kept, sort_keys=True).encode("utf-8"), {}, taken_out


@dataclass(frozen=True)
class Version:
    status: str  # FOUND, EMPTY, GONE or BLOCKED
    sha: str | None  # the commit ID, 40 letters
    made_at: datetime | None  # when that commit was made
    sha256: str  # the fingerprint of the saved answer
    fetched_at: str


def read_version(saved: SavedPage) -> Version:
    """What a saved answer says about the version of its repository."""
    meta = saved.meta
    status = meta["status"]
    if status == 200:
        kept = json.loads(saved.read().decode("utf-8") or "{}")
        sha, date = kept.get("sha"), kept.get("date")
        made = datetime.fromisoformat(date.replace("Z", "+00:00")) if date else None
        found = isinstance(sha, str) and bool(_SHA.match(sha))
        return Version(FOUND if found else GONE, sha if found else None, made, meta["sha256"],
                       meta["fetched_at"])  # fmt: skip
    kind = EMPTY if status == 409 else BLOCKED if status in (403, 451) else GONE
    return Version(kind, None, None, meta["sha256"], meta["fetched_at"])


def saved_version(store: RawStore, repository: str) -> Version | None:
    """The saved version of a repository, or None when it was never asked for."""
    saved = store.load(commits_address(repository), SUFFIX)
    return read_version(saved) if saved is not None else None


def fetch_versions(
    client: PoliteClient,
    store: RawStore,
    repositories: list[str],
    *,
    collector: str,
    limit: int | None = None,
) -> AnswersRun:
    """Ask for the version of every repository that has none saved yet, one after the other."""
    return fetch_once(
        client,
        store,
        repositories,
        address_of=commits_address,
        keep=kept_of,
        status_of=lambda saved: read_version(saved).status,
        statuses=STATUSES,
        suffix=SUFFIX,
        collector=collector,
        limit=limit,
    )
