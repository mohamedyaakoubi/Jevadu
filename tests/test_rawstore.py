"""Raw pages are saved once and never edited (design 5.3, design rule 5)."""

from __future__ import annotations

import hashlib
import re
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


def test_the_saved_pages_are_listed_in_a_fixed_order_without_the_robots_file(
    tmp_path: Path,
) -> None:
    store = RawStore(tmp_path)
    assert store.saved() == []
    first = "https://ethglobal.com/showcase/pebble-pay-x1y2z"
    second = "https://ethglobal.com/showcase/quartz-notes-q3w4e"
    robots = "https://ethglobal.com/robots.txt"
    for url in (second, first):
        store.save(fetch(url), url.encode(), received=url.encode(), collector="T/1")
    store.save(fetch(robots), b"User-agent: *", received=b"x", collector="T/1", suffix=".txt")

    pages = store.saved()
    assert sorted(page.url for page in pages) == [first, second]
    assert [page.url for page in pages] == [page.url for page in store.saved()]  # the same order
    assert all(page.read() == page.url.encode() for page in pages)
    assert all(page.meta == store.load(page.url).meta for page in pages)  # type: ignore[union-attr]
    assert [page.url for page in store.saved(".txt")] == [robots]


def test_a_small_file_whose_page_is_missing_is_not_listed(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.save(fetch(), b"page", received=b"page", collector="T/1")
    store.load(URL).body_path.unlink()  # type: ignore[union-attr]  # half of a save is left
    assert store.saved() == []


def test_a_folder_that_does_not_exist_yet_holds_no_page(tmp_path: Path) -> None:
    assert RawStore(tmp_path / "not" / "made" / "yet").saved() == []


# --------------------------------------------------------------------- personal data found later

ADDRESS = re.compile(r"[a-z.]+@example\.test")
PAGE = b"<p>Write to quill.invented@example.test or to reed@example.test.</p><p>The rest.</p>"


def test_personal_data_is_taken_out_of_a_saved_page_and_the_reason_is_written(
    tmp_path: Path,
) -> None:
    store = RawStore(tmp_path)
    before = store.save(fetch(), PAGE, received=PAGE + b"<p>team</p>", collector="Tool/0.1.0")

    removed = store.remove_text(
        URL, ADDRESS, "[address hidden]", "an address of a person", at="2026-10-11T15:00:00Z"
    )

    assert removed == 2
    after = store.load(URL)
    assert after is not None
    body = b"<p>Write to [address hidden] or to [address hidden].</p><p>The rest.</p>"
    assert after.read() == body
    assert after.meta["sha256"] == hashlib.sha256(body).hexdigest()
    assert after.meta["bytes"] == len(body)
    assert after.meta["removed"] == [
        {
            "at": "2026-10-11T15:00:00Z",
            "why": "an address of a person",
            "matches": 2,
            "sha256_before": before.meta["sha256"],
        }
    ]
    # What the site sent keeps its fingerprint, and the rest of the small file stays.
    assert after.meta["received_sha256"] == before.meta["received_sha256"]
    assert {k: v for k, v in after.meta.items() if k not in ("sha256", "bytes", "removed")} == {
        k: v for k, v in before.meta.items() if k not in ("sha256", "bytes")
    }
    # The text that was removed is written nowhere.
    assert b"quill" not in after.meta_path.read_bytes() + after.read()


def test_a_second_removal_adds_a_second_record(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.save(fetch(), PAGE, received=PAGE, collector="Tool/0.1.0")
    store.remove_text(URL, re.compile(r"quill\.invented@example\.test"), "[x]", "first reason")
    middle = store.load(URL).meta["sha256"]  # type: ignore[union-attr]
    store.remove_text(URL, ADDRESS, "[x]", "second reason")
    records = store.load(URL).meta["removed"]  # type: ignore[union-attr]
    assert [(r["why"], r["matches"]) for r in records] == [
        ("first reason", 1),
        ("second reason", 1),
    ]
    assert records[1]["sha256_before"] == middle
    assert records[0]["at"].endswith("Z")  # the time of the removal, when none is given


def test_a_removal_that_finds_nothing_writes_nothing(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    saved = store.save(fetch(), PAGE, received=PAGE, collector="Tool/0.1.0")
    meta_before = saved.meta_path.read_bytes()
    assert store.remove_text(URL, re.compile("not in the page"), "[x]", "a reason") == 0
    assert saved.meta_path.read_bytes() == meta_before
    assert saved.read() == PAGE
    assert "removed" not in store.load(URL).meta  # type: ignore[union-attr]


def test_a_saved_page_is_never_changed_without_a_reason_or_when_it_is_not_there(
    tmp_path: Path,
) -> None:
    store = RawStore(tmp_path)
    store.save(fetch(), PAGE, received=PAGE, collector="Tool/0.1.0")
    with pytest.raises(ValueError, match="written reason"):
        store.remove_text(URL, ADDRESS, "[x]", "   ")
    assert store.load(URL).read() == PAGE  # type: ignore[union-attr]
    with pytest.raises(FileNotFoundError):
        store.remove_text("https://ethglobal.com/showcase/another-a1b2c", ADDRESS, "[x]", "why")
