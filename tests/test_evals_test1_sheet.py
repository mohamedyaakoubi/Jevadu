"""The review sheet of Test 1: the page and its card side by side, a few planted fields, and the
places of the quotes. Every project here is invented."""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import psycopg
import pytest

from evals.test1 import sheet
from evals.test1.sheet import Block, Case, SheetError, build, fingerprint, plant, write_sheet
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from searchfakes import three_projects
from sheetfakes import DONOR, MODEL, SALE, card, case, field, made, seeded


def test_the_sheet_holds_each_page_its_card_and_where_each_quote_stands() -> None:
    data, _ = made()
    assert len(data["cases"]) == 12 and data["fingerprint"] == fingerprint(data)
    first = data["cases"][0]
    assert [block["kind"] for block in first["blocks"]] == ["name", "short_line", "section"]
    quote = first["card"]["hedera_services"]["quotes"][0]
    (block, start, end), = quote["at"]  # fmt: skip
    assert first["blocks"][block]["text"][start:end] == SALE.rstrip(".")
    assert [field["name"] for field in data["fields"]][:2] == ["what_it_does", "how_it_works"]
    assert len(data["categories"]) == 17 and data["services"][-1]["key"] == "none"
    assert sum(item["parser_check"] for item in data["cases"]) == sheet.PARSER_CHECKS


def test_the_order_and_the_parser_checks_do_not_depend_on_the_plants() -> None:
    one, _ = made(seed=1)
    two, _ = made(seed=2)
    assert [c["page"] for c in one["cases"]] == [c["page"] for c in two["cases"]]
    assert [c["page"] for c in one["cases"]] != sorted(c["page"] for c in one["cases"])
    checks = [[c["parser_check"] for c in data["cases"]] for data in (one, two)]
    assert checks[0] == checks[1]


@pytest.mark.parametrize("seed", range(12))
def test_a_few_fields_are_planted_and_only_the_key_names_them(seed: int) -> None:
    data, key = made(seed=seed)
    plants = key["plants"]
    assert sheet.FEWEST_PLANTS <= len(plants) <= sheet.MOST_PLANTS
    assert key["sheet"] == data["fingerprint"]
    assert all(set(plant) == {"page", "field", "kind"} for plant in plants)
    planted = {(plant["page"], plant["field"]): plant["kind"] for plant in plants}
    assert len({page for page, _ in planted}) == len(plants)  # one field of a project at most
    for item in data["cases"]:
        number = int(re.search(r"project-(\d+)-", item["page"]).group(1))
        own = card(number)
        for name, shown in item["card"].items():
            kind = planted.get((item["page"], name))
            if kind is None:
                assert shown["value"] == own[name]["value"]
                continue
            assert shown["value"] != own[name]["value"]
            assert [quote["text"] for quote in shown["quotes"]] == own[name]["quotes"]
            if kind == sheet.SERVICE:
                assert "Consensus" not in shown["value"] and "HCS" not in shown["value"]
            elif kind == sheet.SWAP:
                assert shown["value"] == DONOR[name]["value"]
            else:
                assert shown["value"] in data["categories"] and shown["value"] != "Other"


def test_too_few_fields_to_plant_stop_the_sheet() -> None:
    bare = Case("https://ethglobal.com/showcase/bare-x1y2z", (Block("name", "", "Bare"),),
                {name: field("not_found", "", [], "not_found") for name in card(1)})  # fmt: skip
    with pytest.raises(SheetError):
        plant([bare, bare], [], seeded(1))


def test_the_sheet_embeds_its_data_safely_and_is_never_written_over(tmp_path: Path) -> None:
    hostile = case(1)
    words = "Coins.</script><script>document.title='taken'</script>"
    hostile = Case(hostile.page, (*hostile.blocks, Block("section", "Notes", words)), hostile.card)
    cases = [hostile] + [case(number) for number in range(2, 5)]
    data, key = build(cases, donors=[DONOR], model=MODEL, version="card-form-9",
                      grades_file="grades.json", rng=seeded(3))  # fmt: skip
    page = write_sheet(tmp_path, data, key).read_text(encoding="utf-8")
    assert sheet.PLACEHOLDER not in page
    assert page.count("</script>") == 2  # the data block and the code: the words cannot end one
    inside = page.split('<script id="sheet-data" type="application/json">')[1].split("</script>")
    assert json.loads(inside[0]) == data
    saved = json.loads((tmp_path / sheet.KEY_FILE).read_text(encoding="utf-8"))
    assert saved == key
    with pytest.raises(SheetError):
        write_sheet(tmp_path, data, key)


def test_show_prints_the_page_and_then_the_card(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data, key = made(count=4)
    write_sheet(tmp_path, data, key)
    assert sheet.show(tmp_path, 1, card=False) == 0
    page = capsys.readouterr().out
    assert page.startswith("== 1 of 4: https://ethglobal.com/showcase/project-")
    assert "-- Project Description\nProject " in page and "quote:" not in page
    assert sheet.show(tmp_path, 1, card=True) == 0
    shown = capsys.readouterr().out
    assert "-- Problem  [not found, not found]\n(empty)" in shown
    assert "-- Solution  [stated, dropped]\n(empty)" in shown
    assert "-- How it works  [inferred, kept]\n  1. " in shown and "   quote: " in shown
    assert sheet.show(tmp_path, 5, card=False) == 2


def test_show_prints_a_sign_that_the_terminal_cannot_show_as_a_question_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = case(1)
    item = Case(item.page, (*item.blocks, Block("section", "Notes", "A ↔ B")), item.card)
    data, key = build([item, case(2), case(3)], donors=[DONOR], model=MODEL,
                      version="card-form-9", grades_file="grades.json", rng=seeded(1))  # fmt: skip
    write_sheet(tmp_path, data, key)
    shown = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(shown, encoding="cp1252"))
    number = [c["page"] for c in data["cases"]].index(item.page) + 1
    assert sheet.show(tmp_path, number, card=False) == 0
    sys.stdout.flush()
    assert b"A ? B" in shown.getvalue()


# ----------------------------------------------------------------- from the database


@pytest.mark.integration
def test_main_reads_the_cards_of_the_set_and_prints_no_plant(
    tmp_path: Path,
    empty_database: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hackathon_memory.settings import Settings

    database = three_projects(empty_database)
    settings = Settings(_env_file=None, database_url=database, data_dir=str(tmp_path / "data"))
    with psycopg.connect(database) as conn:
        ids = dict(conn.execute("SELECT page_url, id FROM projects").fetchall())
        for number, project_id in enumerate(ids.values(), start=1):
            conn.execute(
                "INSERT INTO cards (project_id, model, instructions_version, thinking_level, "
                "input_sha256, fields, answer, quotes_given, quotes_found, fields_dropped, "
                "attempts) VALUES (%s, %s, %s, 'HIGH', %s, %s, '{}', 0, 0, 0, 1)",
                (project_id, settings.gemini_rewrite_model, INSTRUCTIONS_VERSION, "a" * 64,
                 json.dumps(card(number))),
            )  # fmt: skip
    pages = sorted(ids)
    set_file = tmp_path / "test1.json"
    set_file.write_text(json.dumps({"cases": [{"page": page} for page in pages[:2]]}))
    monkeypatch.setattr(sheet, "Settings", lambda: settings)
    monkeypatch.setattr(sheet, "TEST1", set_file)
    monkeypatch.setattr(sheet, "FEWEST_PLANTS", 1)
    assert sheet.main([]) == 0
    printed = capsys.readouterr().out
    folder = tmp_path / "data" / "evals" / "test1"
    data = json.loads((folder / sheet.DATA_FILE).read_text(encoding="utf-8"))
    assert sorted(item["page"] for item in data["cases"]) == pages[:2]
    assert data["grades_file"].endswith(sheet.MAINTAINER_GRADES)
    key = json.loads((folder / sheet.KEY_FILE).read_text(encoding="utf-8"))
    for plant_ in key["plants"]:
        assert plant_["page"] not in printed and plant_["kind"] not in printed
    assert sheet.main([]) == 1  # never written over
    assert "Stopped: a sheet is already in" in capsys.readouterr().out


@pytest.mark.integration
def test_a_page_of_the_set_without_its_card_stops_the_sheet(empty_database: str) -> None:
    database = three_projects(empty_database)
    with pytest.raises(SheetError, match="1 page"):
        sheet.cases_of(database, ["https://ethglobal.com/showcase/pebble-pay-x1y2z"], MODEL, "v")
