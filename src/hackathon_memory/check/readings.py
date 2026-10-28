"""What a reading of a project changed (design 7.3, 28 October 2026).

A reading asks GitHub and the ledger again about a project. What the tool holds about it before
and after the reading is a ProjectState; `changes_of` says what differs, each change a sentence
in plain words, in a fixed order: the repository, its README, its code, its Hedera IDs and their
status on the ledger, and the transactions of its own IDs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

GONE = "gone"  # the code of the repository can no longer be read (db/repositories.py)
# The words of the proof marks (web/app.py, PROOF_SHORT), for the status of one ID.
STATUS_WORDS = {
    "proof_found": "found",
    "dates_do_not_fit": "dates don't fit",
    "found_but_empty": "empty ID",
    "another_kind": "wrong kind of ID",
    "not_found": "ID not found",
}


@dataclass(frozen=True)
class ProjectState:
    """What the tool holds about one project, to compare before and after a reading."""

    code_status: str | None = None  # "found" or GONE, None for a project with no repository
    last_push_at: datetime | None = None
    readme_sha256: str | None = None
    code_commit: str | None = None  # the commit whose code was read
    services_in_code: frozenset[str] = frozenset()  # the Hedera services that its code calls
    ids: frozenset[str] = frozenset()  # the Hedera IDs that it names
    statuses: Mapping[str, str] = field(default_factory=dict)  # an ID and its status
    own_events: int = 0  # the transactions of its own IDs that its histories hold


def in_words(moment: datetime) -> str:
    return f"{moment.day} {moment:%B} {moment.year}"


def listed(names: Iterable[str]) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def changes_of(before: ProjectState, after: ProjectState) -> tuple[str, ...]:
    """What a reading changed, in plain words; empty when nothing did."""
    found: list[str] = []
    if after.code_status != before.code_status and after.code_status == GONE:
        found.append("The repository can no longer be read on GitHub.")
    elif before.code_status == GONE and after.code_status not in (None, GONE):
        found.append("The repository can be read on GitHub again.")
    if after.last_push_at is not None and after.last_push_at != before.last_push_at:
        was = f" (before: {in_words(before.last_push_at)})" if before.last_push_at else ""
        found.append(f"Last push on GitHub: {in_words(after.last_push_at)}{was}.")
    if after.readme_sha256 != before.readme_sha256:
        if after.readme_sha256 and before.readme_sha256:
            found.append("The README changed.")
        elif after.readme_sha256:
            found.append("A README was found.")
        else:
            found.append("The README is no longer found.")
    if after.code_commit and after.code_commit != before.code_commit:
        found.append(f"New code read, at commit {after.code_commit[:7]}.")
    added = sorted(after.services_in_code - before.services_in_code)
    removed = sorted(before.services_in_code - after.services_in_code)
    if added:
        found.append(f"Its code now calls {listed(added)}.")
    if removed:
        found.append(f"Its code no longer calls {listed(removed)}.")
    found += [f"New Hedera ID: {one}." for one in sorted(after.ids - before.ids)]
    found += [f"Hedera ID no longer named: {one}." for one in sorted(before.ids - after.ids)]
    for entity, status in sorted(after.statuses.items()):
        old = before.statuses.get(entity)
        if old is not None and old != status:
            found.append(f"{entity} on the ledger: {STATUS_WORDS.get(status, status)} "
                         f"(before: {STATUS_WORDS.get(old, old)}).")  # fmt: skip
    new = after.own_events - before.own_events
    if new > 0:
        found.append(f"{new:,} new transaction{'s' if new != 1 else ''} of its own IDs.")
    return tuple(found)
