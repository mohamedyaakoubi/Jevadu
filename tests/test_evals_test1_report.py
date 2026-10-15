"""The numbers of Test 1 from the grades. Every project and every grade here is invented."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.test1 import report
from evals.test1.report import Counts, ReportError, numbers, passes, share
from evals.test1.sheet import write_sheet
from sheetfakes import made

DRAWS = 300  # enough to test the range; the report uses 10,000


def graded(
    data: dict,
    *,
    wrong: tuple[tuple[str, str], ...] = (),
    category: str = "Payments and remittance",
    note: str = "",
) -> dict:
    """Grades of every field: right, except the fields named in `wrong`; the page gives nothing
    for a field that the model did not find, and gives what the quote check removed."""
    cases = {}
    for item in data["cases"]:
        fields = {}
        for name, shown in item["card"].items():
            if shown["state"] == "kept":
                bad = (item["page"], name) in wrong
                fields[name] = {"grade": "wrong" if bad else "right",
                                "label": "wrong" if bad else "right"}  # fmt: skip
            else:
                fields[name] = {"has_it": "no" if shown["state"] == "not_found" else "yes"}
        cases[item["page"]] = {
            "category": category, "services": ["consensus"], "card_shown": True,
            "parser": "same" if item["parser_check"] else None, "changed_after_card": False,
            "fields": fields, "note": note,
        }  # fmt: skip
    return {"sheet": data["fingerprint"], "grader": "maintainer", "saved_at": None,
            "cases": cases}  # fmt: skip


def test_a_share_comes_with_its_range_by_project() -> None:
    counts = Counts(meets=(5, 5, 4, 0, 5, 5), of=(5, 5, 5, 5, 5, 5))
    found = share(counts, draws=DRAWS)
    assert (found["share"], found["count"], found["of"]) == (0.8, 24, 30)
    low, high = found["range"]
    assert low < 0.8 < high
    assert share(counts, draws=DRAWS) == found  # the same seed, the same range
    assert share(Counts(meets=(0,), of=(0,)), draws=DRAWS)["share"] is None


def test_the_four_numbers_of_one_grader() -> None:
    data, _ = made(count=6, seed=1)
    first = data["cases"][0]["page"]
    found = numbers(data, graded(data, wrong=((first, "what_it_does"),)), set(), DRAWS)
    # Six projects: five filled fields each, one empty "not found", one removed by the check.
    assert (found["not_wrong"]["count"], found["not_wrong"]["of"]) == (29, 30)
    assert (found["wrong"]["count"], found["right"]["count"]) == (1, 29)
    assert (found["kept"]["count"], found["kept"]["of"]) == (29, 29 + 6)
    assert (found["labels"]["count"], found["labels"]["of"]) == (29 + 6, 30 + 6)
    assert (found["inferred_not_wrong"]["count"], found["inferred_not_wrong"]["of"]) == (12, 12)
    assert (found["quote_check"]["count"], found["quote_check"]["of"]) == (30, 36)
    assert found["projects_graded"] == 6


def test_a_project_not_graded_in_full_is_left_out_of_that_graders_numbers() -> None:
    data, _ = made(count=6, seed=1)
    grades = graded(data)
    del grades["cases"][data["cases"][2]["page"]]["fields"]["for_whom"]
    found = numbers(data, grades, set(), DRAWS)
    assert found["projects_graded"] == 5 and found["not_wrong"]["of"] == 25


def test_the_pass_marks_use_a_grader_who_graded_every_project() -> None:
    data, key = made(count=6, seed=4)
    plants = key["plants"]
    first = graded(data)
    planted_pages = {plant["page"] for plant in plants}
    unplanted = [item["page"] for item in data["cases"] if item["page"] not in planted_pages]
    for page in list(first["cases"]):
        if page not in unplanted[:1]:
            del first["cases"][page]  # the maintainer graded one project, with no planted field
    second = graded(data, wrong=tuple((p["page"], p["field"]) for p in plants))
    result = report.report(data, key, first, second, DRAWS)
    assert result["projects_graded"] == {"maintainer": 1, "second": 6}
    assert result["numbers_that_meet_the_pass_marks"] == "second"
    assert result["agreement"]["projects_graded_by_both"] == 1
    unseen = result["planted"]["maintainer"]
    assert all(p["graded"] is False and p["caught"] is None for p in unseen)
    assert all(p["caught"] for p in result["planted"]["second"])
    assert result["passes"]["planted"] is True and result["passes"]["faithful"] is True
    assert result["agreement_numbers"]["second_on_the_same_projects"]["projects_graded"] == 1
    del second["cases"][data["cases"][0]["page"]]
    result = report.report(data, key, first, second, DRAWS)
    assert result["numbers_that_meet_the_pass_marks"] is None
    assert result["passes"] == {"why_not_decided": "no grader graded every project"}


def test_the_planted_fields_are_left_out_and_caught_when_not_graded_right() -> None:
    data, key = made(count=6, seed=4)
    plants = key["plants"]
    first = graded(data, wrong=tuple((p["page"], p["field"]) for p in plants))
    second = graded(data, wrong=tuple((p["page"], p["field"]) for p in plants[1:]))
    result = report.report(data, key, first, second, DRAWS)
    assert [p["caught"] for p in result["planted"]["maintainer"]] == [True] * len(plants)
    assert [p["caught"] for p in result["planted"]["second"]] == [False] + [True] * (
        len(plants) - 1
    )
    assert result["passes"]["planted"] is False
    mine = result["numbers"]["maintainer"]
    assert mine["not_wrong"]["of"] == 30 - len(plants) and mine["wrong"]["count"] == 0
    assert result["agreement"]["grade"]["share"] == 1.0  # the planted fields are left out


def test_the_pass_marks_of_design_13_6() -> None:
    def mine(wrong: float, low: float, labels: float, kept: float) -> dict:
        return {"not_wrong": {"range": [low, 0.99]}, "wrong": {"share": wrong},
                "labels": {"share": labels}, "kept": {"share": kept}}  # fmt: skip

    caught = {"maintainer": [{"graded": True, "caught": True}],
              "second": [{"graded": True, "caught": True}]}  # fmt: skip
    assert passes(mine(0.05, 0.90, 0.90, 0.85), caught) == {
        "faithful": True, "honest_labels": True, "kept": True, "planted": True}  # fmt: skip
    assert passes(mine(0.06, 0.95, 0.95, 0.95), caught)["faithful"] is False
    assert passes(mine(0.01, 0.89, 0.95, 0.95), caught)["faithful"] is False
    assert passes(mine(0.01, 0.95, 0.89, 0.84), caught) | {} == {
        "faithful": True, "honest_labels": False, "kept": False, "planted": True}  # fmt: skip


def test_the_list_of_categories_needs_the_same_pick_and_few_others() -> None:
    data, key = made(count=10, seed=2)
    first, second = graded(data), graded(data)
    pages = [item["page"] for item in data["cases"]]
    second["cases"][pages[0]]["category"] = "Health"
    second["cases"][pages[1]]["category"] = "Education"
    result = report.report(data, key, first, second, DRAWS)["categories"]
    assert (result["same_category"], result["projects_picked_by_both"]) == (8, 10)
    assert result["agreement"] == 0.8 and result["list_accepted"] is True
    second["cases"][pages[2]]["category"] = "Other"
    second["cases"][pages[3]]["category"] = "Other"
    result = report.report(data, key, first, second, DRAWS)["categories"]
    assert result["other_share"]["second"] == 0.2 and result["list_accepted"] is False


def test_grades_of_another_sheet_are_refused() -> None:
    data, key = made(count=4, seed=1)
    other = graded(data) | {"sheet": "f" * 64}
    with pytest.raises(ReportError, match="second grader"):
        report.report(data, key, graded(data), other, DRAWS)
    with pytest.raises(ReportError, match="key"):
        report.report(data, key | {"sheet": "0" * 64}, graded(data), graded(data), DRAWS)


def test_the_result_file_holds_numbers_and_names_but_no_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hackathon_memory.settings import Settings

    data, key = made(count=6, seed=3)
    folder = tmp_path / "data" / "evals" / "test1"
    write_sheet(folder, data, key)
    words = "My note says the vendor page is odd."
    for name in (report.MAINTAINER_GRADES, report.SECOND_GRADES):
        (folder / name).write_text(json.dumps(graded(data, note=words)), encoding="utf-8")
    settings = Settings(_env_file=None, data_dir=str(tmp_path / "data"))
    monkeypatch.setattr(report, "Settings", lambda: settings)
    monkeypatch.setattr(report, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(report, "DRAWS", DRAWS)
    assert report.main([]) == 0
    assert "Written: " in capsys.readouterr().out
    (written,) = (tmp_path / "results").iterdir()
    text = written.read_text(encoding="utf-8")
    for words_of_a_text in ("note", "odd", "street vendor", "Street vendors", "take a coin"):
        assert words_of_a_text not in text
    saved = json.loads(text)
    assert saved["projects"] == 6 and len(saved["grades"]) == 6 * 7
    assert saved["passes"]["faithful"] is True
    (folder / report.SECOND_GRADES).unlink()
    assert report.main([]) == 1
    assert "Stopped: grades-second.json cannot be read" in capsys.readouterr().out


def test_a_sheet_graded_by_the_second_grader_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hackathon_memory.settings import Settings

    data, key = made(count=4, seed=6)
    folder = tmp_path / "data" / "evals" / "test1-card-form-9"
    write_sheet(folder, data, key)
    (folder / report.SECOND_GRADES).write_text(json.dumps(graded(data)), encoding="utf-8")
    settings = Settings(_env_file=None, data_dir=str(tmp_path / "data"))
    monkeypatch.setattr(report, "Settings", lambda: settings)
    monkeypatch.setattr(report, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(report, "DRAWS", DRAWS)
    assert report.main(["--name", "test1-card-form-9"]) == 0
    (written,) = (tmp_path / "results").iterdir()
    assert written.name.endswith("-test1-card-form-9.json")
    saved = json.loads(written.read_text(encoding="utf-8"))
    assert saved["projects_graded"] == {"maintainer": 0, "second": 4}
    assert saved["numbers_that_meet_the_pass_marks"] == "second"
    assert report.main(["--wrong"]) == 2
