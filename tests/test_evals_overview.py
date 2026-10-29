"""The counts of the overview (evals/overview.py), on three invented projects."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import psycopg
import pytest

from evals import overview
from googlefake import valid_form
from hackathon_memory.db.cards import CardStore
from hackathon_memory.llm.card_form import CardFields
from hackathon_memory.llm.gemini import CardResult, Usage
from hackathon_memory.read.quotes import check_card
from searchfakes import three_projects

pytestmark = pytest.mark.integration


def test_the_counts_of_each_event_hold_numbers_only(empty_database: str) -> None:
    database = three_projects(empty_database)
    now = datetime(2026, 10, 16, 8, 0, tzinfo=UTC)
    found = overview.counts(database, model="m", version="v", now=now)
    assert found["test"] == "overview" and found["made_on"] == "2026-10-16"
    assert found["projects"] == 3 and len(found["events"]) == 1
    event = found["events"][0]
    assert (event["site"], event["slug"]) == ("ethglobal.com", "sample-event")
    assert event["projects"] == 3 and sum(event["prize"].values()) == 3
    assert sum(event["proof"]["all"].values()) == 3 and sum(event["life"]["all"].values()) == 3
    assert found["came_back"] == {"groups": 0, "projects": 0}  # one event: nothing to link
    assert found["proof_from_the_code_only"] == 0
    text = json.dumps(found)
    assert "Pebble" not in text and "invented" not in text  # no text of a page


def test_a_proof_that_only_the_code_gives_is_counted(empty_database: str) -> None:
    """A project whose only proof is an ID of its code counts; one with a proof from its page
    too does not (design 7.3, 29 October 2026)."""
    database = three_projects(empty_database)
    found = (("0.0.7001", "code", "config/ids.ts"), ("0.0.7002", "code", "config/ids.ts"),
             ("0.0.7003", "page", None))  # fmt: skip
    with psycopg.connect(database) as conn:
        first, second, _ = [row[0] for row in conn.execute("SELECT id FROM projects ORDER BY id")]
        for project, (entity, found_in, path) in zip((first, second, second), found, strict=True):
            (hedera_id,) = conn.execute(
                "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
                "words_around, in_hashscan_link, found_at) VALUES (%s, %s, 'testnet', NULL, %s, "
                "'', false, %s) RETURNING id",
                (project, entity, found_in, path)).fetchone()  # fmt: skip
            conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                         "VALUES (%s, 'testnet', 'proof_found')", (hedera_id,))  # fmt: skip
    found_now = overview.counts(database, model="m", version="v",
                                now=datetime(2026, 10, 29, 8, 0, tzinfo=UTC))  # fmt: skip
    assert found_now["proof_from_the_code_only"] == 1


def test_the_cards_of_the_model_and_version_are_counted(empty_database: str) -> None:
    database = three_projects(empty_database)
    store = CardStore(database)
    card = store.inputs()[0]
    made = CardResult(
        fields=CardFields.model_validate(valid_form()),
        usage=Usage(1000, 200, 300, 1500),
        model="m",
        thinking_level="HIGH",
        instructions_version="v",
    )
    checked = check_card(made.fields, card.text)
    store.save(card, made, checked)
    now = datetime(2026, 10, 18, 8, 0, tzinfo=UTC)
    found = overview.counts(database, model="m", version="v", now=now)
    assert found["cards"] == {"cards": 1, "quotes_given": checked.quotes_given,
                              "quotes_found": checked.quotes_found,
                              "fields_dropped": len(checked.dropped())}  # fmt: skip
    other = overview.counts(database, model="m", version="another", now=now)
    assert other["cards"]["cards"] == 0  # a card of another version is not counted


def test_the_job_writes_a_dated_file(empty_database: str, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    from hackathon_memory.settings import Settings

    database = three_projects(empty_database)
    monkeypatch.setattr(overview, "RESULTS", tmp_path)
    monkeypatch.setattr(overview, "Settings",
                        lambda: Settings(_env_file=None, database_url=database))  # fmt: skip
    assert overview.main([]) == 0
    files = list(tmp_path.glob("*-overview.json"))
    assert len(files) == 1 and json.loads(files[0].read_text(encoding="utf-8"))["projects"] == 3
