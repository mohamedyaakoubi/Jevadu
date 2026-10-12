"""Winner entries copied by hand become thin cards (design 4.6). Every record here is invented."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import Run, recorded_run
from hackathon_memory.parse.people import HIDDEN_HANDLE
from hackathon_memory.parse.project import HEDERA_PRIZE, WINNER_ENTRY
from hackathon_memory.parse.winner_entries import (
    AS_PUBLISHED,
    PARSER_VERSION,
    WinnerEntriesError,
    entry_files,
    read_entries,
    slug,
)
from hackathon_memory.pipeline.parse_pages import STEP, parse_winner_entries
from hackathon_memory.search import listing
from hackathon_memory.search.engine import Hit

RECORDS = [
    {
        "kind": "winner_entry",
        "name": "Pebble Pay",
        "event": "Sample Hedera Hackathon 2025",
        "organiser": "Sample Organiser",
        "track": "Payments Track",
        "place": "First Place",
        "description_as_published": "Pebble Pay lets a vendor take a coin. By @quill_invented.",
        "source_url": "https://organiser.example.test/winners",
    },
    {
        "kind": "winner_entry",
        "name": "Cedar Post",
        "event": "Sample Hedera Hackathon 2025",
        "result_as_published": "Local winner",
        "description_as_published": "Logs every parcel on the topic 0.0.3456789 on testnet.",
        "source_url": "https://organiser.example.test/winners",
    },
]


def write(folder: Path, records: list, name: str = "sample-winners.entries.json") -> Path:
    path = folder / "organiser.example.test" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


# --------------------------------------------------------------------- reading a file


def test_each_record_becomes_a_winner_entry(tmp_path: Path) -> None:
    pebble, cedar = read_entries(write(tmp_path, RECORDS))
    page = pebble.page
    assert page.entry_kind == WINNER_ENTRY
    assert page.site == "organiser.example.test"
    assert page.page == "https://organiser.example.test/winners#pebble-pay"
    assert (page.name, page.short_line) == ("Pebble Pay", "")
    assert (page.event.slug, page.event.name) == (
        "sample-hedera-hackathon-2025",
        "Sample Hedera Hackathon 2025",
    )
    [prize] = page.prizes
    assert prize.line == "Sample Organiser - Payments Track - First Place"
    assert page.prize_state == HEDERA_PRIZE
    [text] = page.sections
    assert (text.kind, text.text) == (
        AS_PUBLISHED,
        f"Pebble Pay lets a vendor take a coin. By {HIDDEN_HANDLE}.",
    )
    assert page.people_words_hidden == 1
    assert page.parser == PARSER_VERSION
    # An organiser that is not named is Hedera, and a published result stands for the place.
    assert cedar.page.prizes[0].line == "Hedera - Local winner"
    assert [(i.entity_id, i.network) for i in cedar.page.hedera_ids] == [("0.0.3456789", "testnet")]


def test_a_changed_record_gets_another_fingerprint(tmp_path: Path) -> None:
    [first, _] = read_entries(write(tmp_path, RECORDS))
    changed = [dict(RECORDS[0], place="Second Place"), RECORDS[1]]
    [again, _] = read_entries(write(tmp_path, changed))
    assert first.sha256 != again.sha256


@pytest.mark.parametrize(
    ("records", "why"),
    [
        ([{**RECORDS[0], "kind": "full_card"}], "record 1: not a winner entry"),
        ([RECORDS[0], {**RECORDS[1], "name": "  "}], "record 2: missing or wrong: name"),
        ([{**RECORDS[0], "source_url": "http://organiser.example.test/w"}], "source_url"),
        ([RECORDS[0], RECORDS[0]], "record 2: a second winner of that name"),
        ({"not": "a list"}, "not a list of records"),
    ],
)
def test_a_file_with_a_wrong_record_is_refused_whole(
    tmp_path: Path, records: object, why: str
) -> None:
    with pytest.raises(WinnerEntriesError, match=why) as wrong:
        read_entries(write(tmp_path, records))  # type: ignore[arg-type]
    assert "Pebble" not in str(wrong.value)  # the record is named by its number, not its text


def test_the_files_of_winner_entries_are_found_in_the_folders_of_the_sites(tmp_path: Path) -> None:
    write(tmp_path, RECORDS)
    (tmp_path / "ethglobal.com").mkdir()
    (tmp_path / "ethglobal.com" / "event-ends.txt").write_text("", encoding="utf-8")
    assert [path.name for path in entry_files(tmp_path)] == ["sample-winners.entries.json"]
    assert slug("Hedera x AI 2025!") == "hedera-x-ai-2025"


# --------------------------------------------------------------------- the parse step


@pytest.fixture
def database(empty_database: str) -> str:
    migrate(empty_database)
    return empty_database


def run_step(database: str, folder: Path) -> Run:
    with recorded_run(database, STEP) as run:
        parse_winner_entries(folder, ProjectStore(database), run)
    return run


@pytest.mark.integration
def test_the_parse_step_keeps_the_winner_entries_and_reads_a_changed_one_again(
    database: str, tmp_path: Path
) -> None:
    write(tmp_path, RECORDS)
    first = run_step(database, tmp_path)
    assert dict(first.counts) == {"winner_entries": 2, "winner_entries_new": 2}
    with psycopg.connect(database) as conn:
        rows = conn.execute(
            "SELECT p.name, p.entry_kind, e.site, p.proof_status FROM projects p "
            "JOIN events e ON e.id = p.event_id ORDER BY p.name"
        ).fetchall()
    assert rows == [
        ("Cedar Post", WINNER_ENTRY, "organiser.example.test", None),
        ("Pebble Pay", WINNER_ENTRY, "organiser.example.test", None),
    ]
    write(tmp_path, [dict(RECORDS[0], place="Second Place"), RECORDS[1]])
    again = run_step(database, tmp_path)
    assert dict(again.counts) == {
        "winner_entries": 2,
        "winner_entries_changed": 1,
        "winner_entries_same": 1,
    }


@pytest.mark.integration
def test_a_file_that_cannot_be_read_is_named_and_the_others_are_kept(
    database: str, tmp_path: Path
) -> None:
    write(tmp_path, RECORDS)
    write(tmp_path, [{"kind": "winner_entry"}], name="broken.entries.json")
    run = run_step(database, tmp_path)
    assert run.counts["winner_files_not_read"] == 1
    assert run.counts["winner_entries_new"] == 2
    assert run.problems == [
        {
            "what": "broken.entries.json",
            "rule": "broken.entries.json, record 1: missing or wrong: name, event, source_url, "
            "description_as_published",
        }
    ]


@pytest.mark.integration
def test_the_listing_says_that_a_winner_entry_is_one(database: str, tmp_path: Path) -> None:
    write(tmp_path, RECORDS)
    run_step(database, tmp_path)
    with psycopg.connect(database) as conn:
        pebble = conn.execute("SELECT id FROM projects WHERE name = 'Pebble Pay'").fetchone()[0]
    text = "\n".join(listing.lines(listing.cards(database, [Hit(pebble, 1.0, 1, None)])))
    assert "a winner entry: only the winners of this event are public" in text
    assert "1. Pebble Pay  (Sample Hedera Hackathon 2025)" in text
