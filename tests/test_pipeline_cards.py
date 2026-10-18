"""The step that makes the cards of the LLM, with the network of Google faked. All data is
invented: three projects, and one answer of the model that quotes the page of one of them."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

from googlefake import answer
from hackathon_memory.db.cards import CardStore
from hackathon_memory.db.runs import recorded_run
from hackathon_memory.pipeline.__main__ import main as pipeline_main
from hackathon_memory.pipeline.embed import GoogleIsAway
from hackathon_memory.read import cards as card_step
from hackathon_memory.settings import Settings
from searchfakes import google, three_projects

pytestmark = pytest.mark.integration

PRO = "gemini-3.1-pro-preview"
PAGE = "https://ethglobal.com/showcase/{}-x1y2z"
ON_PEBBLE = "A street vendor takes a coin."  # a sentence of the invented page of Pebble Pay
ANSWER = answer(
    what_it_does={"label": "stated", "text": "A vendor takes coins.", "quotes": [ON_PEBBLE]},
    how_it_works={"label": "not_found", "steps": [], "quotes": []},
    for_whom={"label": "inferred", "text": "Vendors.", "quotes": [ON_PEBBLE]},
    hedera_services={"label": "not_found", "text": "", "quotes": []},
    category={"label": "inferred", "category": "Payments and remittance", "quotes": [ON_PEBBLE]},
)


@pytest.fixture
def database(empty_database: str) -> str:
    return three_projects(empty_database)


def make(database: str, pages: list[str], **options: object):  # noqa: ANN201
    client, fake, calls = google()
    fake.answer_text = ANSWER
    with recorded_run(database, card_step.STEP) as run:
        card_step.make_cards(CardStore(database), client, run, pages=pages, model=PRO,
                             thinking_level="HIGH", **options)  # fmt: skip
    return run, fake


def cards_by_name(database: str) -> list[tuple]:
    with psycopg.connect(database) as conn:
        return conn.execute(
            "SELECT p.name, c.quotes_found, c.fields_dropped FROM cards c "
            "JOIN projects p ON p.id = c.project_id ORDER BY p.name"
        ).fetchall()


def test_the_cards_of_a_set_are_made_checked_and_kept(database: str) -> None:
    pages = [PAGE.format("pebble-pay"), PAGE.format("cedar-post"), PAGE.format("nowhere")]
    run, _ = make(database, pages)
    counts = run.counts
    assert (counts["made"], counts["pages_of_the_set"], counts["pages_without_a_full_card"]) == (
        2, 3, 1
    )  # fmt: skip
    # The quotes stand on the page of Pebble Pay, and not on the page of Cedar Post.
    assert cards_by_name(database) == [("Cedar Post", 0, 3), ("Pebble Pay", 3, 0)]
    assert (counts["quotes_given"], counts["quotes_found"], counts["fields_dropped"]) == (6, 3, 3)
    assert counts["cost_microdollars"] > 0 and counts["input_tokens"] == 2000


def test_a_card_whose_text_did_not_change_costs_nothing(database: str) -> None:
    pages = [PAGE.format("pebble-pay"), PAGE.format("cedar-post")]
    make(database, pages)
    run, fake = make(database, pages)
    assert (run.counts["made"], run.counts["the_same_as_before"]) == (0, 2)
    assert fake.requests == []


def test_the_limit_leaves_the_rest_for_later(database: str) -> None:
    run, _ = make(database, [PAGE.format("pebble-pay"), PAGE.format("fern-vote")], limit=1)
    assert (run.counts["made"], run.counts["left_for_later"]) == (1, 1)


def test_three_failures_in_a_row_stop_the_step(database: str) -> None:
    client, fake, _ = google()
    fake.fail_with = (400, "Invalid request")
    pages = [PAGE.format(slug) for slug in ("pebble-pay", "cedar-post", "fern-vote")]
    with pytest.raises(GoogleIsAway), recorded_run(database, card_step.STEP) as run:
        card_step.make_cards(CardStore(database), client, run, pages=pages, model=PRO,
                             thinking_level="HIGH")  # fmt: skip
    assert [problem["rule"] for problem in run.problems][:3] == ["ClientError"] * 3
    assert cards_by_name(database) == []


def write_set(tmp_path: Path, pages: list[str]) -> Path:
    path = tmp_path / "set.json"
    path.write_text(json.dumps({"cases": [{"page": page} for page in pages]}), encoding="utf-8")
    return path


def test_the_command_needs_a_set_and_makes_its_cards(
    database: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(_env_file=None, database_url=database)
    assert pipeline_main(["cards"], settings) == 2
    assert pipeline_main(["parse", "--set", "x.json"], settings) == 2
    assert "cards needs --set" in capsys.readouterr().out
    client, fake, _ = google()
    fake.answer_text = ANSWER
    path = write_set(tmp_path, [PAGE.format("pebble-pay")])
    assert pipeline_main(["cards", "--set", str(path)], settings, google=client) == 0
    out = capsys.readouterr().out
    assert "Cards made: 1." in out and "Quotes: 3 of 3 found in the page." in out
    assert "a street vendor" not in out.lower()  # numbers only, never the text of a page
    assert pipeline_main(["cards", "--set", str(tmp_path / "none.json")], settings) == 1
    assert "cannot be read as a set" in capsys.readouterr().out


def test_the_command_writes_the_cards_to_a_file_and_puts_them_back(
    database: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """For a database built again: the cards come back from a file, and no model is called."""
    settings = Settings(_env_file=None, database_url=database)
    client, fake, _ = google()
    fake.answer_text = ANSWER
    path = write_set(tmp_path, [PAGE.format("pebble-pay")])
    assert pipeline_main(["cards", "--set", str(path)], settings, google=client) == 0
    saved = tmp_path / "cards.jsonl"
    assert pipeline_main(["cards", "--export", str(saved)], settings) == 0
    assert "Cards written to" in capsys.readouterr().out
    with psycopg.connect(database) as conn:
        conn.execute("DELETE FROM cards")
    before = len(fake.requests)
    assert pipeline_main(["cards", "--restore", str(saved)], settings, google=client) == 0
    out = capsys.readouterr().out
    assert "Put back: 1, with 3 of 3 quotes found again" in out
    assert len(fake.requests) == before  # no model was called
    assert pipeline_main(["cards", "--set", str(path), "--restore", str(saved)], settings) == 2
