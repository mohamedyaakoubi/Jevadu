"""Which card of a project the website shows (db/card_choice.py, the maintainer's rule of 1
November 2026): the card of the first model of the settings, else the card of its stand-in, with
the name of the model that wrote it. On a real PostgreSQL; every text is invented."""

from __future__ import annotations

import json

import psycopg
import pytest

from hackathon_memory.read.quotes import FIELDS, KEPT
from hackathon_memory.search.compare import items_for
from hackathon_memory.search.filters import facts
from hackathon_memory.settings import Settings
from hackathon_memory.web.data import project_card, summaries
from searchfakes import three_projects

pytestmark = pytest.mark.integration

MAIN, STAND_IN, VERSION = "gemini-main", "gemini-4-argon", "card-form-2"


def card(database: str, project_id: int, model: str) -> None:
    """A card of `model` whose every field says which model wrote it."""
    fields = {name: {"label": "stated", "state": KEPT, "value": f"{name} by {model}",
                     "quotes": []} for name in FIELDS}  # fmt: skip
    with psycopg.connect(database) as conn:
        conn.execute(
            "INSERT INTO cards (project_id, model, instructions_version, thinking_level, "
            "input_sha256, fields, answer, quotes_given, quotes_found, fields_dropped, attempts) "
            "VALUES (%s, %s, %s, 'HIGH', %s, %s, '{}', 0, 0, 0, 1)",
            (project_id, model, VERSION, "a" * 64, json.dumps(fields)),
        )


def test_a_project_shows_the_first_models_card_else_the_stand_ins(empty_database: str) -> None:
    database = three_projects(empty_database)
    with psycopg.connect(database) as conn:
        ids = dict(conn.execute("SELECT name, id FROM projects").fetchall())
    both, stand_in_only, none = ids["Pebble Pay"], ids["Cedar Post"], ids["Fern Vote"]
    card(database, both, MAIN)
    card(database, both, STAND_IN)
    card(database, stand_in_only, STAND_IN)
    models = (MAIN, STAND_IN)
    assert project_card(database, both, models=models, version=VERSION).card.model == MAIN
    shown = project_card(database, stand_in_only, models=models, version=VERSION).card
    assert shown.model == STAND_IN  # the card says which model wrote it
    assert shown.fields[0].value == f"{FIELDS[0]} by {STAND_IN}"
    assert project_card(database, none, models=models, version=VERSION).card is None
    said = summaries(database, [both, stand_in_only, none], models=models, version=VERSION)
    assert said[both].text == f"what_it_does by {MAIN}"
    assert said[stand_in_only].text == f"what_it_does by {STAND_IN}"
    assert said[none].source == "page"
    rows = {row.project_id: row for row in facts(database, models=models, version=VERSION)}
    assert (rows[both].category, rows[stand_in_only].category) == (
        f"category by {MAIN}", f"category by {STAND_IN}")  # fmt: skip
    assert len(items_for(database, [both, stand_in_only], models=models, version=VERSION)) == 2
    alone = summaries(database, [stand_in_only], models=(MAIN,), version=VERSION)
    assert alone[stand_in_only].source == "page"  # with no stand-in, its card is not shown


def test_the_settings_name_the_stand_in_after_the_first_model() -> None:
    assert Settings(_env_file=None).card_models() == ("gemini-3.1-pro-preview",)
    with_stand_in = Settings(_env_file=None, gemini_rewrite_stand_in_model=STAND_IN)
    assert with_stand_in.card_models() == ("gemini-3.1-pro-preview", STAND_IN)
    with pytest.raises(ValueError, match="Gemini"):
        Settings(_env_file=None, gemini_rewrite_stand_in_model="another-model")
