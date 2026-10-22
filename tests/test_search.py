"""The search: two lists merged, an idea embedded once a day, a plain listing. All data invented.

The real google-genai library runs, with the network faked (searchfakes.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from fakes import project_page
from hackathon_memory.db.embeddings import EmbeddingStore, idea_fingerprint
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.llm.embeddings import SEARCH_MODEL
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.search import engine, listing
from hackathon_memory.search.__main__ import main as search_main
from hackathon_memory.settings import Settings
from searchfakes import embed_all, google, ids_of, three_projects, vector_for

pytestmark = pytest.mark.integration


@pytest.fixture
def database(empty_database: str) -> str:
    return three_projects(empty_database)


# --------------------------------------------------------------------- merging two lists


def test_two_lists_are_merged_by_their_reciprocal_ranks() -> None:
    hits = engine.merge([7, 8, 9], [9, 7], k=60)
    assert [hit.project_id for hit in hits] == [7, 9, 8]
    assert hits[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert (hits[1].meaning_rank, hits[1].words_rank) == (3, 1)
    assert (hits[2].meaning_rank, hits[2].words_rank) == (2, None)


def test_a_project_in_one_list_only_is_still_found() -> None:
    assert [hit.project_id for hit in engine.merge([], [4])] == [4]
    assert engine.merge([], []) == []


# --------------------------------------------------------------------- the search


def test_the_words_of_the_idea_find_the_projects_that_use_them(database: str) -> None:
    ids = ids_of(database)
    assert engine.by_words(database, "a parcel tracker") == [ids["Cedar Post"]]
    assert engine.by_words(database, "the and of") == []  # no word that counts


def test_a_rare_word_counts_more_than_a_word_that_every_project_has(database: str) -> None:
    # Every invented short line says "invented". A fourth project says it thirty times more.
    echo = project_page(
        name="Echo Echo",
        slug="echo-echo",
        short_line="Invented, invented.",
        description="<p>" + "Invented words. " * 30 + "</p>",
    )
    page = "https://ethglobal.com/showcase/echo-echo-x1y2z"
    ProjectStore(database).save(read_project_page(echo, page), "b" * 64)
    ids = ids_of(database)
    ranked = engine.by_words(database, "invented parcel")
    assert ranked[0] == ids["Cedar Post"]  # one rare word wins over thirty common ones
    assert set(ranked) == set(ids.values())


def test_the_closest_project_in_meaning_comes_first(database: str) -> None:
    client, _, _ = google()
    embed_all(database, client)
    ids = ids_of(database)
    hits = engine.search(database, client, "help a vendor get paid", model=SEARCH_MODEL)
    assert hits[0].project_id == ids["Pebble Pay"]
    assert (hits[0].meaning_rank, hits[0].words_rank) == (1, 1)
    assert {hit.project_id for hit in hits} == set(ids.values())  # meaning ranks every one


def test_an_empty_idea_finds_nothing_and_costs_nothing(database: str) -> None:
    client, fake, _ = google()
    assert engine.search(database, client, "   ", model=SEARCH_MODEL) == []
    assert fake.requests == []


def test_an_idea_is_embedded_once_a_day_and_kept_by_its_fingerprint_only(database: str) -> None:
    client, fake, _ = google()
    embed_all(database, client)
    before = len(fake.requests)
    engine.search(database, client, "Help a VENDOR  get paid", model=SEARCH_MODEL)
    engine.search(database, client, "help a vendor get paid", model=SEARCH_MODEL)
    assert len(fake.requests) == before + 1  # the same idea, in other letters, is not paid twice
    with psycopg.connect(database) as conn:
        rows = conn.execute("SELECT idea_sha256 FROM idea_embeddings").fetchall()
        everything = str(conn.execute("SELECT * FROM idea_embeddings").fetchall())
    assert rows == [(idea_fingerprint("help a vendor get paid"),)]
    assert "vendor" not in everything  # the idea itself is kept nowhere


def test_an_idea_of_yesterday_is_forgotten(database: str) -> None:
    store = EmbeddingStore(database)
    old = datetime(2026, 10, 10, 9, tzinfo=UTC)
    store.save_idea(idea_fingerprint("an old idea"), SEARCH_MODEL, vector_for("vendor"), old)
    later = old + timedelta(hours=23)
    assert store.idea(idea_fingerprint("an old idea"), SEARCH_MODEL, later) is not None
    assert store.forget_old_ideas(old + timedelta(hours=24)) == 1
    assert store.idea(idea_fingerprint("an old idea"), SEARCH_MODEL, later) is None


# --------------------------------------------------------------------- the listing


def test_the_listing_shows_the_facts_of_each_project_and_where_it_was_found(
    database: str,
) -> None:
    client, _, _ = google()
    embed_all(database, client)
    hits = engine.search(database, client, "a ballot for my club", model=SEARCH_MODEL, limit=2)
    found = listing.cards(database, hits)
    text = "\n".join(listing.lines(found))
    assert text.startswith("1. Fern Vote  (ETHGlobal Sample Event)")
    assert "prize: no prize. Hedera proof: not checked yet." in text
    assert "page: https://ethglobal.com/showcase/fern-vote-x1y2z" in text
    assert "found by: meaning #1, words #1" in text
    quiet = "\n".join(listing.lines(found, names=False))
    assert "Fern" not in quiet and "ethglobal.com" not in quiet
    assert quiet.startswith(f"1. project {hits[0].project_id}")


def test_the_listing_shows_what_the_mirror_node_said(database: str) -> None:
    ids = ids_of(database)
    pebble = ids["Pebble Pay"]
    with psycopg.connect(database) as conn:
        hedera_id = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, '0.0.3456781', 'testnet', 'topic', "
            "'readme', 'our topic', false) RETURNING id",
            (pebble,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO ledger_facts (entity_id, network, asked_at, found, kind, created_at, "
            "last_activity_at) VALUES ('0.0.3456781', 'testnet', '2026-10-11T20:00:00Z', true, "
            "'topic', '2026-03-05T10:00:00Z', '2026-03-07T12:00:00Z')"
        )
        conn.execute(
            "INSERT INTO id_checks (hedera_id, network, status) VALUES (%s, 'testnet', "
            "'proof_found')",
            (hedera_id,),
        )
        conn.execute("UPDATE projects SET proof_status = 'proof_found' WHERE id = %s", (pebble,))
    [card] = listing.cards(database, [engine.Hit(pebble, 1.0, 1, None)])
    text = "\n".join(listing.lines([card]))
    assert "Hedera proof: proof found." in text
    assert (
        "0.0.3456781 on testnet, from the README: topic, created 2026-03-05, last activity "
        "2026-03-07. proof found (asked 2026-10-11)"
    ) in text
    quiet = "\n".join(listing.lines([card], names=False))
    assert "0.0.3456781" not in quiet
    assert "ids asked of the mirror node: 1, with 1 answer(s) kept" in quiet


# --------------------------------------------------------------------- the command


def test_the_search_command_prints_the_listing(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    client, _, _ = google()
    embed_all(database, client)
    settings = Settings(_env_file=None, database_url=database)
    assert search_main(["parcels that move", "--limit", "1"], settings, client) == 0
    said = capsys.readouterr().out
    assert said.startswith("1. Cedar Post")
    assert search_main(["parcels that move", "--numbers-only"], settings, client) == 0
    assert "Cedar" not in capsys.readouterr().out


def test_with_no_embedding_only_the_words_are_searched_and_nothing_is_paid(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    client, fake, _ = google()
    settings = Settings(_env_file=None, database_url=database)
    assert search_main(["a ballot for my club"], settings, client) == 0
    said = capsys.readouterr().out
    assert said.startswith("No project has an embedding yet, so only the words were searched.")
    assert "1. Fern Vote" in said and "found by: words #1" in said
    assert fake.requests == []  # the idea was not embedded
    assert search_main(["zebra crossing"], settings, client) == 0
    assert "No project was found." in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["   "], ["an idea", "--limit", "0"]])
def test_the_search_command_refuses_what_makes_no_sense(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert search_main(argv, Settings(_env_file=None)) == 2
    assert "usage:" in capsys.readouterr().out


# --------------------------------------------------------------------- the life of a project

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def give_an_id(database: str, project: int, entity: str, last_activity: str) -> None:
    """The project names the id, and the mirror node found it with this last activity."""
    with psycopg.connect(database) as conn:
        hedera_id = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, %s, 'testnet', 'topic', 'page', "
            "'a topic', false) RETURNING id",
            (project, entity),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO ledger_facts (entity_id, network, asked_at, found, kind, created_at, "
            "last_activity_at) VALUES (%s, 'testnet', '2026-10-11T20:00:00Z', true, 'topic', "
            "'2026-03-05T10:00:00Z', %s) ON CONFLICT DO NOTHING",
            (entity, last_activity),
        )
        conn.execute(
            "INSERT INTO id_checks (hedera_id, network, status) VALUES (%s, 'testnet', "
            "'proof_found')",
            (hedera_id,),
        )


def end_the_event(database: str, last_day: str) -> None:
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE events SET ends_on = %s", (last_day,))


def life_line(database: str, project: int) -> str:
    [card] = listing.cards(database, [engine.Hit(project, 1.0, 1, None)], now=NOW)
    return next(line for line in listing.lines([card]) if line.startswith("   life:"))


def test_a_project_with_nothing_to_look_at_is_unknown(database: str) -> None:
    pebble = ids_of(database)["Pebble Pay"]
    assert life_line(database, pebble) == (
        "   life: unknown (no date of the code and no activity of its own ids)."
    )


def test_the_dates_of_the_code_make_a_project_active(database: str) -> None:
    pebble = ids_of(database)["Pebble Pay"]
    with psycopg.connect(database) as conn:
        repository = conn.execute(
            "INSERT INTO repositories (url, code_status, code_fetched_at, made_at, last_push_at) "
            "VALUES ('https://github.com/sample-org/pebble-pay', 'found', now(), "
            "'2026-03-06T17:00:00Z', '2026-09-30T08:00:00Z') RETURNING id"
        ).fetchone()[0]
        conn.execute("UPDATE projects SET repository_id = %s WHERE id = %s", (repository, pebble))
    end_the_event(database, "2026-03-08")
    assert life_line(database, pebble) == (
        "   life: active (a sign of life in the last 90 days, last sign 2026-09-30). "
        "Code: made 2026-03-06, last push 2026-09-30."
    )


def test_the_ledger_activity_of_an_id_of_its_own_counts(database: str) -> None:
    pebble = ids_of(database)["Pebble Pay"]
    give_an_id(database, pebble, "0.0.3456781", "2026-09-01T10:00:00Z")
    end_the_event(database, "2026-03-08")
    assert life_line(database, pebble).startswith("   life: active (")


def test_an_id_that_projects_with_other_code_name_is_not_a_sign(database: str) -> None:
    ids = ids_of(database)
    # A shared service: two projects with different code name the same busy token.
    give_an_id(database, ids["Pebble Pay"], "0.0.4567891", "2026-10-10T10:00:00Z")
    give_an_id(database, ids["Cedar Post"], "0.0.4567891", "2026-10-10T10:00:00Z")
    end_the_event(database, "2026-03-08")  # so that a sign would make it active
    assert life_line(database, ids["Pebble Pay"]) == (
        "   life: unknown (no date of the code and no activity of its own ids)."
    )


def test_the_work_of_a_recent_event_is_too_early_to_tell(database: str) -> None:
    pebble = ids_of(database)["Pebble Pay"]
    give_an_id(database, pebble, "0.0.3456781", "2026-09-30T10:00:00Z")
    end_the_event(database, "2026-09-16")
    assert life_line(database, pebble) == (
        "   life: too early to tell (the event ended less than 90 days ago, nothing later than "
        "30 days yet, last sign 2026-09-30)."
    )


def test_with_no_end_of_the_event_no_sign_can_be_judged(database: str) -> None:
    pebble = ids_of(database)["Pebble Pay"]
    give_an_id(database, pebble, "0.0.3456781", "2026-10-01T10:00:00Z")
    assert life_line(database, pebble) == (
        "   life: unknown (the end of the event is not known, last sign 2026-10-01)."
    )
    end_the_event(database, "2026-03-08")
    assert life_line(database, pebble).startswith("   life: active (")


# --------------------------------------------------------------------- the filters (design 8.2)


def test_the_filters_limit_both_lists_to_their_projects(database: str) -> None:
    client, _, _ = google()
    embed_all(database, client)
    ids = ids_of(database)
    cedar = ids["Cedar Post"]
    hits = engine.search(database, client, "a vendor and a parcel", model=SEARCH_MODEL,
                         only=[cedar])  # fmt: skip
    assert [hit.project_id for hit in hits] == [cedar]
    assert engine.by_words(database, "a parcel tracker", only=[ids["Pebble Pay"]]) == []


def test_no_project_left_by_the_filters_finds_nothing_and_costs_nothing(database: str) -> None:
    client, fake, _ = google()
    embed_all(database, client)
    before = len(fake.requests)
    assert engine.search(database, client, "a vendor", model=SEARCH_MODEL, only=[]) == []
    assert len(fake.requests) == before  # the idea was not embedded


def test_a_filter_keeps_the_order_of_the_projects_it_keeps(database: str) -> None:
    # How rare a word is, is counted over every project, also when a filter keeps only a few.
    echo = project_page(name="Echo Echo", slug="echo-echo", short_line="Invented, invented.",
                        description="<p>" + "Invented parcel words. " * 30 + "</p>")  # fmt: skip
    page = "https://ethglobal.com/showcase/echo-echo-x1y2z"
    ProjectStore(database).save(read_project_page(echo, page), "b" * 64)
    ids = ids_of(database)
    kept = {ids["Echo Echo"], ids["Fern Vote"]}
    everything = engine.by_words(database, "invented parcel")
    assert engine.by_words(database, "invented parcel", only=sorted(kept)) == [
        project for project in everything if project in kept
    ]


def test_a_mode_makes_only_its_own_list(database: str) -> None:
    client, fake, _ = google()
    embed_all(database, client)
    ids = ids_of(database)
    before = len(fake.requests)
    words = engine.search(database, client, "a parcel tracker", model=SEARCH_MODEL,
                          mode=engine.WORDS)  # fmt: skip
    assert [hit.project_id for hit in words] == [ids["Cedar Post"]]
    assert len(fake.requests) == before  # by words only, the idea is not embedded
    meaning = engine.search(database, client, "help a vendor get paid", model=SEARCH_MODEL,
                            mode=engine.MEANING)  # fmt: skip
    assert meaning[0].project_id == ids["Pebble Pay"]
    assert all(hit.words_rank is None for hit in meaning)
    with pytest.raises(ValueError, match="unknown mode"):
        engine.search(database, client, "a vendor", model=SEARCH_MODEL, mode="magic")
