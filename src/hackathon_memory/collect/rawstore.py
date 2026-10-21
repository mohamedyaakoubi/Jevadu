"""Raw pages, saved once and never edited afterwards (design 5.3, design rule 5).

A saved page is two files: the page itself, and a small file that says where it comes from.
Everything else in the system can be rebuilt from these files, so they are also the backup.
The folder is ignored by git: the pages are other people's text (design rule 18).

The one exception to "as received" is the part that shows team members. It is cut out before
the page reaches this store (see teamcut.py), because the sites were promised that.

The one exception to "never edited afterwards" is personal data that was found in a saved page
later, for example an email address inside the data of a page. `remove_text` takes it out and
writes down what was done and why, next to the page. Nothing else may change a saved page.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from hackathon_memory.collect.polite import FetchResult

STORE_FORMAT = 1


def canonical_url(url: str) -> str:
    """The same page always gets the same name: lower-case host, no fragment, no end slash."""
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def page_key(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()[:24]


def fingerprint(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class SavedPage:
    url: str
    body_path: Path
    meta_path: Path
    meta: dict

    def read(self) -> bytes:
        return self.body_path.read_bytes()


class RawStore:
    """The saved pages of one site, in one folder."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def _paths(self, url: str, suffix: str) -> tuple[Path, Path]:
        key = page_key(url)
        return self.folder / f"{key}{suffix}", self.folder / f"{key}.meta.json"

    def load(self, url: str, suffix: str = ".html") -> SavedPage | None:
        body_path, meta_path = self._paths(url, suffix)
        if not (body_path.exists() and meta_path.exists()):
            return None  # a page with no meta file is a crash leftover, not a saved page
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return SavedPage(url=url, body_path=body_path, meta_path=meta_path, meta=meta)

    def has(self, url: str, suffix: str = ".html") -> bool:
        return self.load(url, suffix) is not None

    def saved(self, suffix: str = ".html") -> list[SavedPage]:
        """Every saved page of this folder, always in the same order.

        A file of another kind (robots.txt) is not a page, and neither is a small file whose
        page is missing.
        """
        pages: list[SavedPage] = []
        for meta_path in sorted(self.folder.glob("*.meta.json")):
            body_path = meta_path.with_name(meta_path.name.removesuffix(".meta.json") + suffix)
            if body_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                pages.append(SavedPage(meta["source_url"], body_path, meta_path, meta))
        return pages

    def save(
        self,
        fetch: FetchResult,
        body: bytes,
        *,
        received: bytes,
        collector: str,
        team_cut: dict | None = None,
        answer: dict | None = None,
        suffix: str = ".html",
        received_sha256: str | None = None,
    ) -> SavedPage:
        """Save `body` (after the team part was cut out). `received` is what the site sent.

        `answer` holds facts of the answer that the saved body no longer shows, such as the name
        of a file that an API sent inside its answer. It holds no text of a page.
        `received_sha256` is the fingerprint of what the site sent when it was read as a stream
        and not kept, such as the archive of a repository; `received` is then empty.
        """
        body_path, meta_path = self._paths(fetch.url, suffix)
        if body_path.exists() and meta_path.exists():
            raise FileExistsError(f"already saved, and a saved page is never edited: {fetch.url}")
        self.folder.mkdir(parents=True, exist_ok=True)

        meta = {
            "store_format": STORE_FORMAT,
            "source_url": fetch.url,
            "final_url": fetch.final_url,
            "status": fetch.status,
            "fetched_at": fetch.fetched_at,
            "content_type": fetch.content_type,
            "bytes": len(body),
            "sha256": fingerprint(body),
            "received_sha256": received_sha256 or fingerprint(received),
            "team_cut": team_cut,
            "collector": collector,
        }
        if answer is not None:
            meta["answer"] = answer
        self._write_once(body_path, body)
        self._write_once(meta_path, (json.dumps(meta, indent=2) + "\n").encode("utf-8"))
        return SavedPage(url=fetch.url, body_path=body_path, meta_path=meta_path, meta=meta)

    def remove_text(
        self,
        url: str,
        pattern: re.Pattern[str],
        put: str,
        why: str,
        *,
        at: str | None = None,
        suffix: str = ".html",
    ) -> int:
        """Take a piece of text out of a saved page, and write down that it was done.

        This is the only way in which a saved page changes after it was saved. It is for
        personal data that must not be kept. Every match of `pattern` is replaced by `put`. The
        small file of the page keeps the reason, the time, the number of matches and the
        fingerprint that the page had before, and it never keeps the text that was removed. The
        fingerprint of what the site sent stays as it is.

        Returns the number of matches. With no match, nothing is written.
        """
        if not why.strip():
            raise ValueError("a saved page is changed only with a written reason")
        saved = self.load(url, suffix)
        if saved is None:
            raise FileNotFoundError(f"no saved page for {url}")
        text, matches = pattern.subn(put, saved.read().decode("utf-8"))
        if matches == 0:
            return 0
        body = text.encode("utf-8")
        record = {
            "at": at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "why": why.strip(),
            "matches": matches,
            "sha256_before": saved.meta["sha256"],
        }
        meta = {
            **saved.meta,
            "bytes": len(body),
            "sha256": fingerprint(body),
            "removed": [*saved.meta.get("removed", []), record],
        }
        self._write_once(saved.body_path, body)
        self._write_once(saved.meta_path, (json.dumps(meta, indent=2) + "\n").encode("utf-8"))
        return matches

    @staticmethod
    def _write_once(path: Path, data: bytes) -> None:
        """Write a whole file or nothing: the new file takes its place only when it is complete."""
        temporary = path.with_name(path.name + ".part")
        temporary.unlink(missing_ok=True)
        with open(temporary, "xb") as handle:
            handle.write(data)
        os.replace(temporary, path)
