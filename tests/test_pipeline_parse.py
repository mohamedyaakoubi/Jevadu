"""The step that parses the saved pages, on a real PostgreSQL. Every page here is invented."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import psycopg
import pytest

from fakes import project_page, won
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import Run, last_runs, recorded_run
from hackathon_memory.parse.ethglobal_page import PARSER_VERSION, read_project_page
from hackathon_memory.parse.project import ProjectPage
from hackathon_memory.pipeline.__main__ import main
from hackathon_memory.pipeline.parse_pages import EDITED, STEP, parse_saved_pages
from hackathon_memory.settings import Settings

pytestmark = pytest.mark.integration

NAMES = ("pebble-pay", "quartz-notes", "cedar-lens")


def address(name: str) -> str:
    return f"https://ethglobal.com/showcase/{name}-x1y2z"


def save(raw: RawStore, name: str, *, at: str, **changes: object) -> None:
    """Save one invented project page as a collector would."""
    body = project_page(name=name.replace("-", " ").title(), slug=name, **changes)  # type: ignore[arg-type]
    fetch = FetchResult(
        url=address(name),
        final_url=address(name),
        status=200,
        body=body,
        content_type="text/html; charset=utf-8",
        fetched_at=at,
    )
    raw.save(fetch, body, received=body, collector="HackathonMemory-research/0.1.0")


@pytest.fixture
def database(empty_database: str) -> str:
    migrate(empty_database)
    return empty_database


@pytest.fixture
def raw(tmp_path: Path) -> RawStore:
    """Three saved pages. The folder order of their files is not the order of their saving."""
    store = RawStore(tmp_path / "data" / "raw" / "ethglobal.com")
    save(store, "quartz-notes", at="2026-10-10T19:00:02Z")
    save(store, "pebble-pay", at="2026-10-10T19:00:00Z", prizes=[won()])
    save(store, "cedar-lens", at="2026-10-10T19:00:04Z")
    return store


def run_step(database: str, raw: RawStore, **options: object) -> Run:
    with recorded_run(database, STEP) as run:
        parse_saved_pages(raw, ProjectStore(database), run, **options)  # type: ignore[arg-type]
    return run


def names_in(database: str) -> list[str]:
    with psycopg.connect(database) as conn:
        return [name for (name,) in conn.execute("SELECT site_key FROM projects ORDER BY 1")]


def refuse_to_read(body: bytes, page: str) -> ProjectPage:
    raise AssertionError(f"{page} was opened, and it should have been passed over")


# --------------------------------------------------------------------- the step


def test_every_saved_page_becomes_a_project(database: str, raw: RawStore) -> None:
    run = run_step(database, raw)
    assert dict(run.counts) == {"pages": 3, "new": 3}
    assert run.problems == []
    assert names_in(database) == ["cedar-lens-x1y2z", "pebble-pay-x1y2z", "quartz-notes-x1y2z"]
    with psycopg.connect(database) as conn:
        states = conn.execute("SELECT site_key, prize_state FROM projects ORDER BY 1").fetchall()
    assert states == [
        ("cedar-lens-x1y2z", "no_prize"),
        ("pebble-pay-x1y2z", "hedera_prize"),
        ("quartz-notes-x1y2z", "no_prize"),
    ]


def test_a_second_run_opens_no_page_again(database: str, raw: RawStore) -> None:
    run_step(database, raw)
    again = run_step(database, raw, read=refuse_to_read)
    assert dict(again.counts) == {"pages": 3, "same": 3}


def test_a_page_saved_later_is_the_only_one_read_by_the_next_run(
    database: str, raw: RawStore
) -> None:
    run_step(database, raw)
    save(raw, "dune-notes", at="2026-10-11T01:00:00Z")
    later = run_step(database, raw)
    assert dict(later.counts) == {"pages": 4, "same": 3, "new": 1}


def test_a_page_of_another_shape_is_named_and_the_others_are_kept(
    database: str, raw: RawStore
) -> None:
    save(raw, "eel-ledger", at="2026-10-10T19:00:01Z", data_changes={"tagline": "Another line."})
    run = run_step(database, raw)
    assert dict(run.counts) == {"pages": 4, "new": 3, "not_read": 1}
    assert run.problems == [
        {
            "what": address("eel-ledger"),
            "rule": "the short line of the header is not the one in the data",
        }
    ]
    assert len(names_in(database)) == 3


def test_a_page_that_was_changed_on_disk_is_not_read(database: str, raw: RawStore) -> None:
    saved = raw.load(address("cedar-lens"))
    assert saved is not None
    saved.body_path.write_bytes(saved.read().replace(b"Cedar Lens", b"Cedar Leng"))
    run = run_step(database, raw)
    assert dict(run.counts) == {"pages": 3, "new": 2, "not_read": 1}
    assert run.problems == [{"what": address("cedar-lens"), "rule": EDITED}]
    assert "cedar-lens-x1y2z" not in names_in(database)


def test_a_limit_reads_the_pages_that_were_saved_first(database: str, raw: RawStore) -> None:
    first = run_step(database, raw, limit=2)
    assert dict(first.counts) == {"pages": 3, "new": 2, "left_for_later": 1}
    assert names_in(database) == ["pebble-pay-x1y2z", "quartz-notes-x1y2z"]  # by time of saving

    second = run_step(database, raw, limit=2)
    assert dict(second.counts) == {"pages": 3, "same": 2, "new": 1}
    assert len(names_in(database)) == 3


def test_a_new_parser_reads_every_page_again(database: str, raw: RawStore) -> None:
    run_step(database, raw)

    next_version = f"{PARSER_VERSION}-next"

    def newer(body: bytes, page: str) -> ProjectPage:
        return replace(read_project_page(body, page), parser=next_version)

    again = run_step(database, raw, read=newer, parser=next_version)
    assert dict(again.counts) == {"pages": 3, "changed": 3}


def test_an_empty_folder_gives_an_empty_run(database: str, tmp_path: Path) -> None:
    run = run_step(database, RawStore(tmp_path / "nothing" / "here"))
    assert dict(run.counts) == {}


# --------------------------------------------------------------------- the command


def settings_for(database: str, raw: RawStore) -> Settings:
    return Settings(_env_file=None, database_url=database, data_dir=str(raw.folder.parents[1]))


def test_the_command_parses_and_says_what_it_did(
    database: str, raw: RawStore, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["parse", "--limit", "2"], settings_for(database, raw)) == 0
    said = capsys.readouterr().out
    assert "Saved pages: 3. New: 2." in said
    assert "Left for a later run, because of the limit: 1." in said
    (row,) = last_runs(database, STEP)
    assert row["ok"] is True
    assert row["counts"] == {
        "pages": 3,
        "new": 2,
        "left_for_later": 1,
        "events_without_an_end": 1,
    }
    assert "Events with no end yet: 1." in said
    assert f"This is run {row['id']} in the table of runs." in said


def test_the_command_names_a_page_that_it_could_not_read_and_ends_with_an_error(
    database: str, raw: RawStore, capsys: pytest.CaptureFixture[str]
) -> None:
    save(raw, "eel-ledger", at="2026-10-10T19:00:01Z", data_changes={"name": "Another Name"})
    assert main(["parse"], settings_for(database, raw)) == 1
    said = capsys.readouterr().out
    assert "Not read: 1." in said
    assert f"  {address('eel-ledger')}: the name in the header is not the name in the data" in said
    assert "Eel Ledger" not in said  # no text of a page


def test_the_command_says_what_to_do_when_the_tables_are_missing(
    empty_database: str, raw: RawStore, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["parse"], settings_for(empty_database, raw)) == 1
    assert "python -m hackathon_memory.db migrate" in capsys.readouterr().out


def test_the_command_does_not_show_the_connection_text_when_the_database_is_away(
    raw: RawStore, capsys: pytest.CaptureFixture[str]
) -> None:
    away = "postgresql://someone:a-password-that-protects-nothing@127.0.0.1:1/nothing?connect_timeout=2"
    assert main(["parse"], settings_for(away, raw)) == 1
    said = capsys.readouterr().out
    assert "cannot reach the database" in said
    assert "a-password-that-protects-nothing" not in said


@pytest.mark.parametrize("argv", [[], ["embed"], ["parse", "--limit", "0"], ["parse", "--fast"]])
def test_the_command_refuses_what_it_does_not_know(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 2
    assert "usage: python -m hackathon_memory.pipeline parse" in capsys.readouterr().out


# --------------------------------------------------------------------- the ends of events


def write_ends(raw: RawStore, text: str) -> None:
    """The file of the ends of events, where the command looks for it."""
    folder = raw.folder.parents[1] / "by-hand" / "ethglobal.com"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "event-ends.txt").write_text(text, encoding="utf-8")


def ends_in(database: str) -> list[tuple]:
    with psycopg.connect(database) as conn:
        return conn.execute("SELECT slug, ends_on::text FROM events ORDER BY slug").fetchall()


def test_the_command_writes_the_ends_of_events_typed_by_hand(
    database: str, raw: RawStore, capsys: pytest.CaptureFixture[str]
) -> None:
    write_ends(raw, "# typed by hand\nsample-event 2026-03-08  # the page of the event\n")
    assert main(["parse"], settings_for(database, raw)) == 0
    said = capsys.readouterr().out
    assert (
        "Ends of events typed by hand: 1 written, 0 the same as before. Events with no end yet: 0."
    ) in said
    assert ends_in(database) == [("sample-event", "2026-03-08")]

    assert main(["parse"], settings_for(database, raw)) == 0
    assert "0 written, 1 the same as before" in capsys.readouterr().out


def test_the_command_names_an_end_that_it_could_not_use(
    database: str, raw: RawStore, capsys: pytest.CaptureFixture[str]
) -> None:
    write_ends(raw, "sample-event 2026-03-01\nanother-event 2026-03-08\n")
    assert main(["parse"], settings_for(database, raw)) == 1
    said = capsys.readouterr().out
    assert "Not used, and why:" in said
    assert "  event-ends.txt: another-event: no saved project names this event" in said
    assert "  event-ends.txt: sample-event: the last day is before the start of the event" in said
    assert ends_in(database) == [("sample-event", None)]


def test_a_file_of_ends_that_cannot_be_read_is_not_used_at_all(
    database: str, raw: RawStore, capsys: pytest.CaptureFixture[str]
) -> None:
    write_ends(raw, "sample-event 2026-03-08\nnot a line\n")
    assert main(["parse"], settings_for(database, raw)) == 1
    said = capsys.readouterr().out
    assert (
        "  the ends of events typed by hand: event-ends.txt, line 2: expected the short name"
    ) in said
    assert ends_in(database) == [("sample-event", None)]  # not even the good first line


# --------------------------------------------------------------------- people are hidden


def test_the_step_hides_people_and_the_command_says_how_many_words(
    database: str, raw: RawStore, capsys: pytest.CaptureFixture[str]
) -> None:
    save(
        raw,
        "eel-ledger",
        at="2026-10-10T19:00:01Z",
        made="<p>Built by @quill and @reed.</p>",
        demo="https://t.me/invented_helper_bot",
    )
    assert main(["parse"], settings_for(database, raw)) == 0
    said = capsys.readouterr().out
    assert (
        "Handles, addresses and profile links that were hidden in the texts and the links: 3."
    ) in said
    with psycopg.connect(database) as conn:
        texts = " ".join(body for (body,) in conn.execute("SELECT body FROM sections"))
    assert "quill" not in texts and "reed" not in texts
    assert "Built by @[name hidden] and @[name hidden]." in texts
    with psycopg.connect(database) as conn:
        hidden = conn.execute(
            "SELECT kind, url, hidden_on FROM links WHERE hidden_on IS NOT NULL"
        ).fetchall()
    assert hidden == [("demo", None, "t.me")]
