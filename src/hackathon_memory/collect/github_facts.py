"""The facts of each repository, asked for once through GitHub's API (design 7.3).

One request for each repository: GET /repos/{owner}/{repo}. The life rule needs two dates of it
(design 7.4): when the repository was made, and when code was last pushed to it.

The answer also holds the account that owns the repository: its photo, and for some accounts a
name and an email address (GitHub's page of the endpoint, read on 12 October 2026). The tool
keeps none of it (design rule 11). So before an answer is saved, only a fixed list of fields is
kept: the link, the dates, the state, the language, the size, and the license by its short
name. The description of the repository is kept with the words about people hidden. The answer
of a fork also holds the repository it comes from, with its owner: it is dropped too.

* 200: the facts, as said.
* 404: no such repository any more, or a private one. What GitHub sent is saved as it came.
* 403 or 451 with "Repository access blocked": saved as it came.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from hackathon_memory.collect.github import SITE, api_message
from hackathon_memory.collect.github_once import AnswersRun, fetch_once
from hackathon_memory.collect.polite import FetchResult, PoliteClient
from hackathon_memory.collect.rawstore import RawStore, SavedPage
from hackathon_memory.parse.people import hide_in_text

SUFFIX = ".json"
FOUND = "found"
GONE = "gone"  # 404: deleted, made private, or never public
BLOCKED = "blocked"
STATUSES = (FOUND, GONE, BLOCKED)

# The fields of the answer that are kept. Every other field is dropped before saving.
KEPT = (
    "html_url",
    "description",
    "fork",
    "archived",
    "disabled",
    "created_at",
    "updated_at",
    "pushed_at",
    "size",
    "language",
    "default_branch",
    "visibility",
    "topics",
)


def facts_address(repository: str) -> str:
    """The address of the facts of a repository in GitHub's API."""
    owner, name = repository.removeprefix("https://github.com/").split("/")
    return f"https://{SITE}/repos/{owner}/{name}"


def kept_of(fetch: FetchResult) -> tuple[bytes, dict, dict | None]:
    """What is saved of an answer: the kept fields, the facts of the answer, what was taken
    out."""
    if fetch.status != 200:
        return fetch.body, {"message": api_message(fetch.body)}, None
    try:
        answer = json.loads(fetch.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return b"{}", {"kept": "nothing", "why": "the answer is not JSON"}, None
    if not isinstance(answer, dict):
        return b"{}", {"kept": "nothing", "why": "the answer is not an object"}, None
    kept = {key: answer.get(key) for key in KEPT}
    license_ = answer.get("license")
    kept["license"] = license_.get("spdx_id") if isinstance(license_, dict) else None
    hidden = 0
    if isinstance(kept["description"], str):
        kept["description"], hidden = hide_in_text(kept["description"])
    dropped = sorted(set(answer) - set(KEPT) - {"license"})
    taken_out = {
        "fields_dropped": len(dropped),
        "owner_dropped": "owner" in dropped,
        "words_hidden": hidden,
    }
    body = json.dumps(kept, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return body, {}, taken_out


@dataclass(frozen=True)
class RepositoryFacts:
    status: str  # FOUND, GONE or BLOCKED
    created_at: datetime | None
    pushed_at: datetime | None  # the last push of code to any branch
    archived: bool | None
    fork: bool | None
    language: str | None
    current_url: str | None  # the link today, which differs when the repository was moved
    sha256: str
    fetched_at: str
    default_branch: str | None = None  # the branch that GitHub opens first, such as main

    @property
    def read_at(self) -> datetime:
        """When GitHub gave this answer."""
        return datetime.fromisoformat(self.fetched_at.replace("Z", "+00:00"))


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_facts(saved: SavedPage) -> RepositoryFacts:
    """What a saved answer says about its repository."""
    meta = saved.meta
    status = meta["status"]
    if status == 200:
        kept = json.loads(saved.read().decode("utf-8") or "{}")
        url = kept.get("html_url")
        branch = kept.get("default_branch")
        return RepositoryFacts(
            status=FOUND,
            created_at=_moment(kept.get("created_at")),
            pushed_at=_moment(kept.get("pushed_at")),
            archived=kept.get("archived"),
            fork=kept.get("fork"),
            language=kept.get("language"),
            current_url=url.lower() if isinstance(url, str) else None,
            sha256=meta["sha256"],
            fetched_at=meta["fetched_at"],
            default_branch=branch if isinstance(branch, str) and branch else None,
        )
    return RepositoryFacts(
        status=BLOCKED if status in (403, 451) else GONE,
        created_at=None,
        pushed_at=None,
        archived=None,
        fork=None,
        language=None,
        current_url=None,
        sha256=meta["sha256"],
        fetched_at=meta["fetched_at"],
    )


def saved_facts(store: RawStore, repository: str) -> RepositoryFacts | None:
    """The saved facts of a repository, or None when they were never asked for."""
    saved = store.load(facts_address(repository), SUFFIX)
    return read_facts(saved) if saved is not None else None


def fetch_facts(
    client: PoliteClient,
    store: RawStore,
    repositories: list[str],
    *,
    collector: str,
    limit: int | None = None,
) -> AnswersRun:
    """Ask for the facts of every repository that has none saved yet, one after the other."""
    return fetch_once(
        client,
        store,
        repositories,
        address_of=facts_address,
        keep=kept_of,
        status_of=lambda saved: read_facts(saved).status,
        statuses=STATUSES,
        suffix=SUFFIX,
        collector=collector,
        limit=limit,
    )
