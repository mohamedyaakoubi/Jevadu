"""The README of each project's code, asked for once through GitHub's API (design 7.3).

Many project pages give no Hedera id. The README of the code often does: a team writes down its
token, its topic or its contract for the people who run the code. 653 of the 658 pages of
ETHGlobal link to their code on GitHub.

One request for each repository: GET /repos/{owner}/{repo}/readme. The answer is saved once and
never asked for again:

* 200: the README. Its text is decoded from base64 and, before it is saved, its part about the
  team is cut out and the words about people are hidden (parse/markdown.py). Next to it are the
  fingerprint of what GitHub sent, the numbers of what was taken out, and the README's name,
  path, size and version (sha).
* 404: the repository has no README, or it is not there any more. What GitHub sent is saved as
  it came: a short message that holds no text of a page.
* 403 or 451 with "Repository access blocked": saved as it came.

A README that is not text (not UTF-8, or too large for this endpoint) is saved as an empty page,
and the small file next to it says why.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass

from hackathon_memory.collect.github import api_message, readme_address
from hackathon_memory.collect.github_once import AnswersRun, fetch_once
from hackathon_memory.collect.polite import FetchResult, PoliteClient
from hackathon_memory.collect.rawstore import RawStore, SavedPage
from hackathon_memory.parse.markdown import hide_in_markdown

SUFFIX = ".txt"
# What a saved answer says about the README.
FOUND = "found"
NONE = "none"  # no README: none in the repository, or no repository
BLOCKED = "blocked"
NOT_TEXT = "not_text"
STATUSES = (FOUND, NONE, BLOCKED, NOT_TEXT)

_FACTS = ("name", "path", "size", "sha", "html_url", "encoding")


@dataclass(frozen=True)
class Readme:
    status: str  # FOUND, NONE, BLOCKED or NOT_TEXT
    text: str  # the README with people taken out. Empty unless FOUND.
    name: str | None  # the name of the file, such as README.md
    sha256: str  # the fingerprint of the saved page
    fetched_at: str
    taken_out: dict  # numbers only: what was cut and hidden before saving


def kept_of(fetch: FetchResult) -> tuple[bytes, dict, dict | None]:
    """What is saved of an answer: the page, the facts of the answer, and what was taken out."""
    if fetch.status != 200:
        return fetch.body, {"message": api_message(fetch.body)}, None
    try:
        answer = json.loads(fetch.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return b"", {"kept": NOT_TEXT, "why": "the answer is not JSON"}, None
    if not isinstance(answer, dict):
        return b"", {"kept": NOT_TEXT, "why": "the answer is not an object"}, None
    facts = {key: answer.get(key) for key in _FACTS}
    if answer.get("encoding") != "base64" or not isinstance(answer.get("content"), str):
        return b"", {**facts, "kept": NOT_TEXT, "why": "no text in base64 in the answer"}, None
    try:
        text = base64.b64decode(answer["content"]).decode("utf-8")
    except (binascii.Error, ValueError):  # UnicodeDecodeError is a ValueError
        return b"", {**facts, "kept": NOT_TEXT, "why": "the README is not text in UTF-8"}, None
    done = hide_in_markdown(text)
    taken_out = {
        "words_hidden": done.words_hidden,
        "team_parts_cut": done.team_parts_cut,
        "team_lines_cut": done.team_lines_cut,
        "ids_in_the_cut": done.ids_in_the_cut,
    }
    return done.text.encode("utf-8"), facts, taken_out


def read_readme(saved: SavedPage) -> Readme:
    """What a saved answer says about the README of its repository."""
    meta = saved.meta
    answer = meta.get("answer") or {}
    status = meta["status"]
    if status == 200 and answer.get("kept") != NOT_TEXT:
        kind, text = FOUND, saved.read().decode("utf-8")
    elif status == 200:
        kind, text = NOT_TEXT, ""
    elif status in (403, 451):
        kind, text = BLOCKED, ""
    else:
        kind, text = NONE, ""
    return Readme(
        status=kind,
        text=text,
        name=answer.get("name"),
        sha256=meta["sha256"],
        fetched_at=meta["fetched_at"],
        taken_out=meta.get("team_cut") or {},
    )


def saved_readme(store: RawStore, repository: str) -> Readme | None:
    """The saved README of a repository, or None when it was never asked for."""
    saved = store.load(readme_address(repository), SUFFIX)
    return read_readme(saved) if saved is not None else None


def fetch_readmes(
    client: PoliteClient,
    store: RawStore,
    repositories: list[str],
    *,
    collector: str,
    limit: int | None = None,
) -> AnswersRun:
    """Ask for the README of every repository that has none saved yet, one after the other.

    With `limit`, at most that many are asked for in this run. A README that fails is counted
    and asked for again by a later run. A stop (the switch, a no, too many requests) ends the
    run, and what was saved stays saved.
    """
    return fetch_once(
        client,
        store,
        repositories,
        address_of=readme_address,
        keep=kept_of,
        status_of=lambda saved: read_readme(saved).status,
        statuses=STATUSES,
        suffix=SUFFIX,
        collector=collector,
        limit=limit,
    )
