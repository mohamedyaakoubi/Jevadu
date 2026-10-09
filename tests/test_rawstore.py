"""Raw pages are saved once and never edited (design 5.3, design rule 5)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore, canonical_url, page_key

URL = "https://ethglobal.com/showcase/zed-widget-a1b2c"


def fetch(url: str = URL) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status=200,
        body=b"",
        content_type="text/html",
        fetched_at="2026-10-09T18:00:00Z",
    )


def test_a_saved_page_can_be_loaded_with_its_meta(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    saved = store.save(
        fetch(), b"<p>cut</p>", received=b"<p>cut</p><p>team</p>", collector="Tool/0.1.0"
    )
    loaded = store.load(URL)
    assert loaded is not None
    assert loaded.read() == b"<p>cut</p>"
    assert loaded.meta == saved.meta
    assert loaded.meta["sha256"] == hashlib.sha256(b"<p>cut</p>").hexdigest()
    assert loaded.meta["received_sha256"] == hashlib.sha256(b"<p>cut</p><p>team</p>").hexdigest()
    assert loaded.meta["bytes"] == len(b"<p>cut</p>")
    assert loaded.meta["fetched_at"] == "2026-10-09T18:00:00Z"
    assert loaded.meta["source_url"] == URL


def test_a_saved_page_is_never_overwritten(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.save(fetch(), b"first", received=b"first", collector="Tool/0.1.0")
    with pytest.raises(FileExistsError):
        store.save(fetch(), b"second", received=b"second", collector="Tool/0.1.0")
    assert store.load(URL).read() == b"first"  # type: ignore[union-attr]


def test_a_page_without_its_meta_file_is_not_counted_as_saved(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.save(fetch(), b"first", received=b"first", collector="Tool/0.1.0")
    store.load(URL).meta_path.unlink()  # type: ignore[union-attr]  # a crash left half a save
    assert store.has(URL) is False
    store.save(fetch(), b"again", received=b"again", collector="Tool/0.1.0")
    assert store.load(URL).read() == b"again"  # type: ignore[union-attr]


def test_the_same_page_gets_the_same_name_however_it_is_written() -> None:
    spellings = [
        URL,
        URL + "/",
        URL + "#details",
        "HTTPS://ETHGLOBAL.COM/showcase/zed-widget-a1b2c",
    ]
    assert len({page_key(s) for s in spellings}) == 1
    assert canonical_url(URL + "/#x") == URL


def test_a_query_makes_a_different_page() -> None:
    assert page_key(URL + "?a=1") != page_key(URL)


def test_the_meta_file_holds_no_address_of_a_person(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    saved = store.save(fetch(), b"x", received=b"x", collector="Tool/0.1.0")
    text = saved.meta_path.read_text(encoding="utf-8")
    assert "@" not in text
    assert set(saved.meta) == {
        "store_format",
        "source_url",
        "final_url",
        "status",
        "fetched_at",
        "content_type",
        "bytes",
        "sha256",
        "received_sha256",
        "team_cut",
        "collector",
    }


def test_the_robots_file_is_kept_next_to_the_pages(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    robots = "https://ethglobal.com/robots.txt"
    store.save(
        fetch(robots), b"User-agent: *", received=b"User-agent: *", collector="T/1", suffix=".txt"
    )
    assert store.has(robots, ".txt")
    assert not store.has(robots, ".html")
