"""Raw pages, saved once and never edited afterwards (design 5.3, design rule 5).

A saved page is two files: the page itself, and a small file that says where it comes from.
Everything else in the system can be rebuilt from these files, so they are also the backup.
The folder is ignored by git: the pages are other people's text (design rule 18).

The one exception to "as received" is the part that shows team members. It is cut out before
the page reaches this store (see teamcut.py), because the sites were promised that.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
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

    def save(
        self,
        fetch: FetchResult,
        body: bytes,
        *,
        received: bytes,
        collector: str,
        team_cut: dict | None = None,
        suffix: str = ".html",
    ) -> SavedPage:
        """Save `body` (after the team part was cut out). `received` is what the site sent."""
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
            "received_sha256": fingerprint(received),
            "team_cut": team_cut,
            "collector": collector,
        }
        self._write_once(body_path, body)
        self._write_once(meta_path, (json.dumps(meta, indent=2) + "\n").encode("utf-8"))
        return SavedPage(url=fetch.url, body_path=body_path, meta_path=meta_path, meta=meta)

    @staticmethod
    def _write_once(path: Path, data: bytes) -> None:
        temporary = path.with_name(path.name + ".part")
        temporary.unlink(missing_ok=True)
        with open(temporary, "xb") as handle:
            handle.write(data)
        os.replace(temporary, path)
