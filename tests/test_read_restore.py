"""The cards saved to a file and put back into a database built again (read/restore.py). Every
project here is invented."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from googlefake import valid_form
from hackathon_memory.db.cards import CardStore
from hackathon_memory.db.runs import Run
from hackathon_memory.llm.card_form import CardFields
from hackathon_memory.llm.gemini import CardResult, Usage
from hackathon_memory.read import restore
from hackathon_memory.read.quotes import check_card
from searchfakes import three_projects

pytestmark = pytest.mark.integration


def made(store: CardStore) -> None:
    """A card of the model for each full card, as a run of the card step leaves them."""
    for card in store.inputs():
        result = CardResult(CardFields.model_validate(valid_form()), Usage(900, 100, 50, 1050),
                            "m", "HIGH", "v")  # fmt: skip
        store.save(card, result, check_card(result.fields, card.text))


def test_cards_come_back_with_their_quotes_checked_again(
    empty_database: str, tmp_path: Path
) -> None:
    database = three_projects(empty_database)
    store = CardStore(database)
    made(store)
    before = store.counts("m", "v")
    file = tmp_path / "cards.jsonl"
    assert restore.export_cards(database, file) == 3
    with psycopg.connect(database) as conn:
        made_at = conn.execute("SELECT min(made_at) FROM cards").fetchone()[0]
        conn.execute("DELETE FROM cards")
    run = Run(0, "cards")
    restore.restore_cards(store, restore.read_saved(file), run)
    assert run.counts["restored"] == 3 and store.counts("m", "v") == before
    with psycopg.connect(database) as conn:
        assert conn.execute("SELECT min(made_at) FROM cards").fetchone()[0] == made_at
    assert "No model was called." in restore.restore_lines(run)[0]


def test_a_card_whose_text_changed_or_whose_page_is_gone_stays_out(
    empty_database: str, tmp_path: Path
) -> None:
    database = three_projects(empty_database)
    store = CardStore(database)
    made(store)
    file = tmp_path / "cards.jsonl"
    restore.export_cards(database, file)
    rows = list(restore.read_saved(file))
    rows[0]["input_sha256"] = "0" * 64  # the page reads otherwise now
    rows[1]["page_url"] = "https://example.test/gone"
    with psycopg.connect(database) as conn:
        conn.execute("DELETE FROM cards")
    run = Run(0, "cards")
    restore.restore_cards(store, rows, run)
    assert run.counts["restored"] == 1
    assert run.counts["text_not_the_same"] == 1 and run.counts["no_full_card_for_the_page"] == 1
