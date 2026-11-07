"""The answers of GitHub that a check saved, shared between the copies of the public copy on Vercel
(design 12.5, migration 0033, 7 November 2026).

Each copy of the site has its own data folder in /tmp, and a request may land on any copy
(web/vercel_app.py). So a check that one copy made and saved as files was asked of GitHub again on
another, and a comparison could wait for a README that its copy did not hold. Around a check and a
comparison on the public copy:

* `restore` writes into this copy's folder the files that any copy kept for the repository, when
  this copy does not hold them yet;
* `persist` keeps the files that this copy wrote while it checked the repository.

A saved file is never changed (collect/rawstore.py), so a kept row is never changed either. The
files linked from the deployment are not kept: every copy has them.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

LONGEST_FILE = 5_000_000  # bytes: an answer of GitHub or a reading of code is far smaller


def written_since(folder: Path, since: float) -> list[Path]:
    """The files written in `folder` at or after `since` (a time of time.time()), not the links to
    the deployment's files, and none that is too large to keep."""
    found = []
    for root, _, names in os.walk(folder):
        for name in names:
            path = Path(root) / name
            try:
                if path.is_symlink():
                    continue
                stat = path.stat()
            except OSError:
                continue
            if stat.st_mtime >= since and stat.st_size <= LONGEST_FILE:
                found.append(path)
    return found


def persist(conninfo: str, data: Path, folder: Path, repository: str, since: float) -> int:
    """Keep the files that this copy wrote in `folder` since `since`, for `repository`. Returns how
    many were new."""
    files = written_since(folder, since)
    if not files:
        return 0
    kept = 0
    with psycopg.connect(conninfo, connect_timeout=5) as conn:
        for path in files:
            kept += conn.execute(
                "INSERT INTO kept_answers (path, repository, body) VALUES (%s, %s, %s) "
                "ON CONFLICT (path) DO NOTHING",
                (path.relative_to(data).as_posix(), repository, path.read_bytes()),
            ).rowcount
    return kept


def restore(conninfo: str, data: Path, repository: str) -> int:
    """Write into `data` the files kept for `repository` that this copy does not hold, never outside
    `data`. Returns how many were written."""
    with psycopg.connect(conninfo, connect_timeout=5) as conn:
        rows = conn.execute(
            "SELECT path, body FROM kept_answers WHERE repository = %s", (repository,)
        ).fetchall()
    root = data.resolve()
    written = 0
    for relative, body in rows:
        target = (root / relative).resolve()
        if root not in target.parents or target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes(body))
        written += 1
    return written
