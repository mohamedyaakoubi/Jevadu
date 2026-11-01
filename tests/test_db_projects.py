"""The store of parsed projects, on a real PostgreSQL. Every page here is invented."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, date, datetime

import psycopg
import pytest
from psycopg import sql

from fakes import EVENT, OTHER_ID, PROJECT_PAGE, project_page, won
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import CHANGED, NEW, SAME, ProjectStore
from hackathon_memory.parse.ethglobal_page import PARSER_VERSION, read_project_page
from hackathon_memory.parse.hedera_ids import FoundId
from hackathon_memory.parse.project import ProjectPage

pytestmark = pytest.mark.integration

SHA_A = "a" * 64
SHA_B = "b" * 64
SECOND_PAGE = "https://ethglobal.com/showcase/quartz-notes-q3w4e"
TABLES = ("events", "projects", "prizes", "links", "sections", "hedera_ids")


@pytest.fixture
def database(empty_database: str) -> str:
    migrate(empty_database)
    return empty_database


def parsed(**changes: object) -> ProjectPage:
    return read_project_page(project_page(**changes), PROJECT_PAGE)  # type: ignore[arg-type]


def second() -> ProjectPage:
    html = project_page(name="Quartz Notes", slug="quartz-notes", short_id="q3w4e")
    return read_project_page(html, SECOND_PAGE)


def rows(database: str, query: str, *values: object) -> list[tuple]:
    with psycopg.connect(database) as conn:
        return conn.execute(query, values).fetchall()


def everything(database: str) -> dict[str, list[tuple]]:
    """Every row of every table of the projects."""
    with psycopg.connect(database) as conn:
        return {
            table: conn.execute(
                sql.SQL("SELECT * FROM {} ORDER BY 1, 2").format(sql.Identifier(table))
            ).fetchall()
            for table in TABLES
        }


FULL = {
    "prizes": [won(), won("Other Sponsor", OTHER_ID, track="Best use", kind="track")],
    "description": (
        "<p>The coin is the token 0.0.2345671 on the test network.</p><ul><li>one</li></ul>"
    ),
    "made": '<p>See <a href="https://hashscan.io/testnet/topic/0.0.3456781">the log</a>.</p>',
}


# --------------------------------------------------------------------- saving


def test_a_project_is_saved_with_all_that_the_parser_read(database: str) -> None:
    store = ProjectStore(database)
    assert store.save(parsed(**FULL), SHA_A) == NEW

    assert rows(database, "SELECT site, slug, name, starts_at::text, ends_on FROM events") == [
        ("ethglobal.com", "sample-event", EVENT, "2026-03-06 16:00:00+00", None)
    ]
    assert rows(
        database,
        "SELECT site, page_url, site_key, entry_kind, name, short_line, prize_state, has_video, "
        "page_sha256, parser FROM projects",
    ) == [
        (
            "ethglobal.com",
            PROJECT_PAGE,
            "pebble-pay-x1y2z",
            "full_card",
            "Pebble Pay",
            "Pay a street vendor with a coin on Hedera.",
            "hedera_prize",
            True,
            SHA_A,
            PARSER_VERSION,
        )
    ]
    assert rows(
        database,
        "SELECT position, sponsor, sponsor_id, track, award, kind, pool, line FROM prizes "
        "ORDER BY position",
    ) == [
        (1, "Hedera", "hed01", "AI, Agents & Hedera Services", "1st place", "tier", False,
         "Hedera - AI, Agents & Hedera Services 1st place"),
        (2, "Other Sponsor", OTHER_ID, "Best use", "Best use", "track", False,
         "Other Sponsor - Best use"),
    ]  # fmt: skip
    assert rows(database, "SELECT position, kind, url, label FROM links ORDER BY position") == [
        (1, "demo", "https://demo.example.test/pebble-pay", "Live Demo"),
        (2, "code", "https://github.com/sample-org/pebble-pay", "Source Code"),
    ]
    assert rows(
        database, "SELECT position, kind, title, body, blocks FROM sections ORDER BY position"
    ) == [
        (
            1,
            "description",
            "Project Description",
            "The coin is the token 0.0.2345671 on the test network.\none",
            [
                {
                    "kind": "paragraph",
                    "text": "The coin is the token 0.0.2345671 on the test network.",
                    "level": 0,
                },
                {"kind": "item", "text": "one", "level": 1},
            ],
        ),
        (
            2,
            "how_its_made",
            "How it's Made",
            "See the log.",
            [{"kind": "paragraph", "text": "See the log.", "level": 0}],
        ),
    ]
    assert rows(
        database,
        "SELECT entity_id, network, said_kind, found_in, in_hashscan_link FROM hedera_ids "
        "ORDER BY id",
    ) == [
        ("0.0.2345671", "testnet", "token", "page", False),
        ("0.0.3456781", "testnet", "topic", "page", True),
    ]


def test_a_link_with_a_hidden_address_is_saved_with_its_site_only(database: str) -> None:
    ProjectStore(database).save(parsed(demo="https://t.me/invented_helper_bot"), SHA_A)
    assert rows(
        database, "SELECT position, kind, url, label, hidden_on FROM links ORDER BY position"
    ) == [
        (1, "demo", None, "Live Demo", "t.me"),
        (2, "code", "https://github.com/sample-org/pebble-pay", "Source Code", None),
    ]
    with psycopg.connect(database) as conn:
        everything = conn.execute("SELECT row_to_json(links)::text FROM links").fetchall()
    assert "invented_helper_bot" not in str(everything)


def test_saving_the_same_page_again_changes_nothing(database: str) -> None:
    store = ProjectStore(database)
    store.save(parsed(**FULL), SHA_A)
    before = everything(database)
    assert store.save(parsed(**FULL), SHA_A) == SAME
    after = everything(database)
    assert after == before  # also the time of the parsing


def test_a_changed_page_replaces_the_parts_and_keeps_the_project(database: str) -> None:
    store = ProjectStore(database)
    store.save(parsed(**FULL), SHA_A)
    (project_id,) = rows(database, "SELECT id FROM projects")[0]

    changed = parsed(short_line="A new short line.", code=None, made="<p>Rewritten.</p>")
    assert store.save(changed, SHA_B) == CHANGED

    assert rows(database, "SELECT id, short_line, prize_state, page_sha256 FROM projects") == [
        (project_id, "A new short line.", "no_prize", SHA_B)
    ]
    assert rows(database, "SELECT count(*) FROM prizes") == [(0,)]
    assert rows(database, "SELECT kind FROM links") == [("demo",)]
    assert rows(database, "SELECT body FROM sections ORDER BY position") == [
        ("Pebble Pay lets a street vendor take a payment with a coin.",),
        ("Rewritten.",),
    ]
    assert rows(database, "SELECT count(*) FROM hedera_ids") == [(0,)]


def test_a_new_parser_reads_a_page_again(database: str) -> None:
    store = ProjectStore(database)
    store.save(parsed(), SHA_A)
    next_version = f"{PARSER_VERSION}-next"
    assert store.save(replace(parsed(), parser=next_version), SHA_A) == CHANGED
    assert rows(database, "SELECT parser FROM projects") == [(next_version,)]
    assert store.already_parsed() == {PROJECT_PAGE: (SHA_A, next_version)}


def test_two_projects_of_one_event_share_it_and_an_end_typed_by_hand_stays(database: str) -> None:
    store = ProjectStore(database)
    store.save(parsed(), SHA_A)
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE events SET ends_on = '2026-03-08'")
    assert store.save(second(), SHA_B) == NEW
    assert store.save(parsed(short_line="Changed."), SHA_B) == CHANGED

    assert rows(database, "SELECT slug, starts_at::date::text, ends_on::text FROM events") == [
        ("sample-event", "2026-03-06", "2026-03-08")
    ]
    assert rows(database, "SELECT count(DISTINCT event_id), count(*) FROM projects") == [(1, 2)]


def test_an_id_found_in_a_readme_stays_when_the_page_is_parsed_again(database: str) -> None:
    store = ProjectStore(database)
    store.save(parsed(**FULL), SHA_A)
    with psycopg.connect(database) as conn:
        conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) "
            "SELECT id, '0.0.4567891', NULL, NULL, 'readme', 'the id 0.0.4567891', false "
            "FROM projects"
        )
    store.save(parsed(), SHA_B)  # the page no longer names an id
    assert rows(database, "SELECT entity_id, found_in FROM hedera_ids") == [
        ("0.0.4567891", "readme")
    ]


def test_a_project_is_saved_whole_or_not_at_all(database: str) -> None:
    store = ProjectStore(database)
    bad_id = FoundId("not an id", None, None, "invented words")
    with pytest.raises(psycopg.errors.CheckViolation):
        store.save(replace(parsed(**FULL), hedera_ids=(bad_id,)), SHA_A)
    assert all(found == [] for found in everything(database).values())

    store.save(parsed(**FULL), SHA_A)
    before = everything(database)
    with pytest.raises(psycopg.errors.CheckViolation):
        store.save(replace(parsed(name="Another Name"), hedera_ids=(bad_id,)), SHA_B)
    after = everything(database)
    assert after == before  # the page that was there is still there, whole


def test_the_counts_say_what_the_tables_hold(database: str) -> None:
    store = ProjectStore(database)
    assert store.already_parsed() == {}
    store.save(parsed(**FULL), SHA_A)
    store.save(second(), SHA_B)
    assert store.counts() == {
        "events": 1,
        "projects": 2,
        "prizes": 2,
        "links": 4,
        "sections": 4,
        "hedera_ids": 2,
        "hedera_prize": 1,
        "no_prize": 1,
    }
    assert store.already_parsed() == {
        PROJECT_PAGE: (SHA_A, PARSER_VERSION),
        SECOND_PAGE: (SHA_B, PARSER_VERSION),
    }


# --------------------------------------------------------------------- the rules of the tables


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE projects SET prize_state = 'best'",
        "UPDATE projects SET entry_kind = 'card'",
        "UPDATE projects SET page_url = 'http://ethglobal.com/showcase/x'",
        "UPDATE projects SET page_sha256 = 'abc'",
        "UPDATE projects SET name = ''",
        "UPDATE hedera_ids SET network = 'ethereum'",
        "UPDATE hedera_ids SET said_kind = 'coin'",
        "UPDATE hedera_ids SET entity_id = '0.0.98x'",
        "UPDATE hedera_ids SET found_in = 'chat'",
        "UPDATE links SET kind = 'person'",
        "UPDATE links SET url = 'javascript:alert(1)'",
        "UPDATE links SET url = NULL",  # neither an address nor the site of a hidden one
        "UPDATE links SET hidden_on = 't.me'",  # both
        "UPDATE links SET url = NULL, hidden_on = ''",
        "UPDATE sections SET blocks = '{}'",
        "UPDATE events SET ends_on = '2026-03-01'",  # before its start
    ],
)
def test_the_tables_refuse_a_value_that_makes_no_sense(database: str, change: str) -> None:
    ProjectStore(database).save(parsed(**FULL), SHA_A)
    with pytest.raises(psycopg.errors.CheckViolation), psycopg.connect(database) as conn:
        conn.execute(change)


def test_the_same_id_is_kept_once_for_a_project_also_with_no_network(database: str) -> None:
    ProjectStore(database).save(parsed(), SHA_A)
    insert = (
        "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
        "words_around, in_hashscan_link) "
        "SELECT id, '0.0.4567891', NULL, NULL, 'readme', 'words', false FROM projects"
    )
    with psycopg.connect(database) as conn:
        conn.execute(insert)
    with pytest.raises(psycopg.errors.UniqueViolation), psycopg.connect(database) as conn:
        conn.execute(insert)


def test_no_table_of_the_projects_has_a_column_for_a_person(database: str) -> None:
    # Design rule 11: no team member names, emails or photos.
    columns = rows(
        database,
        "SELECT table_name || '.' || column_name FROM information_schema.columns "
        "WHERE table_name = ANY(%s)",
        list(TABLES),
    )
    person = re.compile(
        r"member|author|email|team|person|user|owner|avatar|photo|handle|profile|hacker"
    )
    assert len(columns) > 30
    assert [name for (name,) in columns if person.search(name)] == []


# --------------------------------------------------------------------- the ends of events


def other_event() -> ProjectPage:
    html = project_page(
        name="Quartz Notes",
        slug="quartz-notes",
        short_id="q3w4e",
        event_slug="other-event",
        event_name="ETHGlobal Other Event",
        starts_at="2025-11-21T15:00:00.000Z",
    )
    return read_project_page(html, SECOND_PAGE)


def ends_in(database: str) -> list[tuple]:
    return rows(database, "SELECT slug, ends_on::text FROM events ORDER BY slug")


def test_the_ends_of_events_are_written_once_and_then_left_as_they_are(database: str) -> None:
    store = ProjectStore(database)
    store.save(parsed(), SHA_A)
    store.save(other_event(), SHA_B)

    done = store.set_event_ends("ethglobal.com", {"sample-event": date(2026, 3, 8)})
    assert (done.written, done.same, done.unknown, done.before_start) == (1, 0, [], [])
    assert done.without_end == 1  # the other event has no end yet
    assert ends_in(database) == [("other-event", None), ("sample-event", "2026-03-08")]

    again = store.set_event_ends(
        "ethglobal.com", {"sample-event": date(2026, 3, 8), "other-event": date(2025, 11, 23)}
    )
    assert (again.written, again.same, again.without_end) == (1, 1, 0)
    assert ends_in(database) == [("other-event", "2025-11-23"), ("sample-event", "2026-03-08")]


def test_an_end_can_be_corrected(database: str) -> None:
    store = ProjectStore(database)
    store.save(parsed(), SHA_A)
    store.set_event_ends("ethglobal.com", {"sample-event": date(2026, 3, 8)})
    assert store.set_event_ends("ethglobal.com", {"sample-event": date(2026, 3, 7)}).written == 1
    assert ends_in(database) == [("sample-event", "2026-03-07")]


def test_an_event_that_no_project_names_is_not_made_up(database: str) -> None:
    store = ProjectStore(database)
    store.save(parsed(), SHA_A)
    done = store.set_event_ends("ethglobal.com", {"another-event": date(2026, 3, 8)})
    assert done.unknown == ["another-event"]
    assert rows(database, "SELECT count(*) FROM events") == [(1,)]
    other_site = store.set_event_ends("example.test", {"sample-event": date(2026, 3, 8)})
    assert other_site.unknown == ["sample-event"]  # the same name on another site


def test_the_typed_year_of_an_event_is_written_and_used_when_no_date_is_known(
    database: str,
) -> None:
    from hackathon_memory.search import filters

    store = ProjectStore(database)
    store.save(parsed(), SHA_A)  # the event starts on 6 March 2026
    with psycopg.connect(database) as conn:  # an event of a list of winners: no date at all
        conn.execute("UPDATE events SET starts_at = NULL, ends_on = NULL")
    years = {("ethglobal.com", "sample-event"): 2025, ("ethglobal.com", "none"): 2024}
    written, unknown = store.set_event_years(years)
    assert (written, unknown) == (1, ["ethglobal.com none"])  # no event is made up
    assert store.set_event_years(years)[0] == 0  # the same year again writes nothing
    found = filters.facts(database, models=("m",), version="v")
    assert {row.year for row in found} == {"2025"}
    with psycopg.connect(database) as conn:  # a known date wins over the typed year
        conn.execute("UPDATE events SET ends_on = '2026-03-08'")
    assert {row.year for row in filters.facts(database, models=("m",), version="v")} == {"2026"}


def test_the_typed_days_of_an_event_become_its_start_and_its_end(database: str) -> None:
    store = ProjectStore(database)
    store.save(parsed(), SHA_A)
    with psycopg.connect(database) as conn:  # an event of a list of winners: no date at all
        conn.execute("UPDATE events SET starts_at = NULL, ends_on = NULL")
    days = {("ethglobal.com", "sample-event"): (date(2024, 7, 22), date(2024, 8, 20)),
            ("ethglobal.com", "none"): (date(2024, 1, 1), date(2024, 1, 2))}  # fmt: skip
    assert store.set_event_days(days) == (1, ["ethglobal.com none"])
    assert store.set_event_days(days)[0] == 0  # the same days again write nothing
    with psycopg.connect(database) as conn:
        start, end = conn.execute("SELECT starts_at, ends_on FROM events").fetchone()
    assert start == datetime(2024, 7, 22, tzinfo=UTC) and end == date(2024, 8, 20)


def test_an_end_before_the_start_is_refused(database: str) -> None:
    store = ProjectStore(database)
    store.save(parsed(), SHA_A)  # the event starts on 6 March 2026
    done = store.set_event_ends("ethglobal.com", {"sample-event": date(2026, 3, 5)})
    assert (done.written, done.before_start) == (0, ["sample-event"])
    assert ends_in(database) == [("sample-event", None)]
    same_day = store.set_event_ends("ethglobal.com", {"sample-event": date(2026, 3, 6)})
    assert same_day.written == 1  # an event of one day ends on the day it starts
