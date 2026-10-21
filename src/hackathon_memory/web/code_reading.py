"""What the code of a repository says about Hedera, as a card and a check show it (design 7.3,
12.1 S2 and S3): read from the tables for a project of the collection, or from the reading of a
check. Each file found links to GitHub at the commit that was read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

import psycopg

from hackathon_memory.collect.github_code import LIVE_MAX_BYTES, LIVE_SECONDS, CodeRead
from hackathon_memory.parse.hedera_code import (
    FEATURE,
    IMPORT,
    LIMIT_BYTES,
    LIMIT_SECONDS,
    MENTION,
    PACKAGE,
    SIGN,
    UNREADABLE,
)

KINDS = (PACKAGE, FEATURE, SIGN, IMPORT, MENTION)  # their order on the screen
# Why a reading stopped before the end of the archive, in plain words.
PARTIAL_WORDS = {
    UNREADABLE: "GitHub's archive could not be read to its end, so this is what its readable "
    "part shows.",
    LIMIT_BYTES: f"The archive is larger than {LIVE_MAX_BYTES // 1_000_000} MB, the most that a "
    "check reads, so this is what its first part shows.",
    LIMIT_SECONDS: f"The download took longer than {LIVE_SECONDS:.0f} seconds, the most that a "
    "check waits, so this is what arrived by then.",
}


@dataclass(frozen=True)
class FoundLine:
    """One thing found: its kind, its name, in how many files, and the first files, each with
    its link on GitHub."""

    kind: str
    name: str
    files: int
    examples: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True)
class CodeView:
    status: str  # read, partial, gone or blocked
    read_at: datetime | None
    commit: str | None
    files: int | None  # the files of the project's own code that were read
    partial: str | None  # why the reading stopped before the end, in plain words
    found: tuple[FoundLine, ...]
    saved: bool = True  # False: read during a check within its limits, and not kept

    def of(self, kind: str) -> tuple[FoundLine, ...]:
        return tuple(one for one in self.found if one.kind == kind)

    @property
    def only_mentions(self) -> bool:
        return bool(self.found) and all(one.kind == MENTION for one in self.found)


def file_link(repository: str, commit: str | None, path: str) -> str | None:
    """The file on GitHub as it was read, at its commit; None when the commit is not known."""
    return f"{repository}/blob/{commit}/{quote(path, safe='/')}" if commit else None


def _line(
    repository: str, commit: str | None, kind: str, name: str, files: int, examples: object
) -> FoundLine:
    paths = tuple(str(path) for path in examples)  # type: ignore[attr-defined]
    linked = tuple((path, file_link(repository, commit, path)) for path in paths)
    return FoundLine(kind, name, files, linked)


def _words(partial: str | None) -> str | None:
    return PARTIAL_WORDS.get(partial, partial) if partial else None


def view_of_read(repository: str, read: CodeRead | None) -> CodeView | None:
    """The view of a reading that a check made or found saved."""
    if read is None:
        return None
    when = datetime.fromisoformat(read.fetched_at.replace("Z", "+00:00"))
    scan = read.scan
    if scan is None:
        return CodeView(read.status, when, None, None, None, (), read.saved)
    found = tuple(_line(repository, scan.commit, one.kind, one.name, one.files, one.examples)
                  for one in scan.found())  # fmt: skip
    return CodeView(read.status, when, scan.commit, scan.files, _words(scan.partial), found,
                    read.saved)  # fmt: skip


def view_of_repository(conn: psycopg.Connection, repository: str) -> CodeView | None:
    """The view of the saved reading of a repository of the collection, from the tables; None
    when its code was not read."""
    row = conn.execute(
        "SELECT id, archive_status, archive_read_at, archive_commit, archive_files, "
        "archive_partial FROM repositories WHERE url = %s",
        (repository,),
    ).fetchone()
    if row is None or row[1] is None:
        return None
    repository_id, status, read_at, commit, files, partial = row
    rows = conn.execute(
        "SELECT kind, name, files, examples FROM hedera_in_code WHERE repository_id = %s "
        "ORDER BY array_position(%s::text[], kind), name",
        (repository_id, list(KINDS)),
    ).fetchall()
    found = tuple(_line(repository, commit, *one) for one in rows)
    return CodeView(status, read_at, commit, files, _words(partial), found)
