"""The counts of the overview (evals/overview.py), on three invented projects."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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
    text = json.dumps(found)
    assert "Pebble" not in text and "invented" not in text  # no text of a page


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
