"""Rewrite the history of a CLONE (never of the real repository): constraints 19 and 20.

    python rewrite.py <clone folder>

* drops CLAUDE.md, backlog/ and docs/ from every commit (the notes stay on the laptop);
* cleans the wording of every text file of every commit (sanitize.py);
* removes the co-author lines and the Refs lines from every message, and writes six messages again;
* drops the commits that only touched the notes (git-filter-repo prunes commits that became empty).

git-filter-repo 2.47.0, used as a library.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "filter_repo_pkg"))
sys.path.insert(0, HERE)

import git_filter_repo as fr  # noqa: E402
from sanitize import CURATED, sanitize_message, sanitize_text  # noqa: E402

changed_blobs = 0


def blob_callback(blob, metadata) -> None:  # noqa: ANN001, ARG001
    global changed_blobs
    try:
        text = blob.data.decode("utf-8")
    except UnicodeDecodeError:
        return
    new = sanitize_text(text)
    if new != text:
        blob.data = new.encode("utf-8")
        changed_blobs += 1


def commit_callback(commit, metadata) -> None:  # noqa: ANN001, ARG001
    original = commit.original_id.decode("ascii")
    curated = next((msg for short, msg in CURATED.items() if original.startswith(short)), None)
    if curated is not None:
        commit.message = curated.encode("utf-8")
        return
    commit.message = sanitize_message(commit.message.decode("utf-8", errors="replace")).encode(
        "utf-8"
    )


def main(clone: str) -> int:
    os.chdir(clone)
    args = fr.FilteringOptions.parse_args(
        [
            "--force",
            "--invert-paths",
            "--path",
            "CLAUDE.md",
            "--path",
            "backlog",
            "--path",
            "docs",
        ],
        error_on_empty=False,
    )
    fr.RepoFilter(args, blob_callback=blob_callback, commit_callback=commit_callback).run()
    print(f"blobs whose wording changed: {changed_blobs}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
