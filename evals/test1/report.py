"""The numbers of Test 1, from the grades (design 13.2 and 13.6). guideline.md defines them.

    python -m evals.test1.report

It reads the sheet, the key of its planted fields and the grades of the two graders, all in
data/evals/test1, and writes evals/results/<UTC time>-test1.json: the four numbers of each grader
with their ranges, the pass marks, the planted fields and whether each grader caught them, the
check of the list of categories, how often the graders agree, and every grade by page address
and field name. No text of a page, of a card or of a note goes into that file (design 13.1).

A grader's numbers come from the projects that grader graded in full: every question of every
field answered. The numbers that meet the pass marks come from a grader who graded every project:
the maintainer when the maintainer did, otherwise the second grader. The projects that both
graded show how often the two agree. A range is computed by project: the projects are drawn
again with replacement, DRAWS times, with a fixed seed, and the range holds the middle 95 of every
100 results (design 13.1).
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from evals.test1.sheet import DATA_FILE, KEY_FILE, MAINTAINER_GRADES, SECOND_GRADES
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent.parent / "results"
DRAWS = 10_000
SEED = 20261017
NOT_WRONG = ("right", "partly")
GRADES = ("right", "partly", "wrong")
# The pass marks of design 13.6, fixed on 9 October 2026, and of design 4.5 for the categories.
MOST_WRONG = 0.05
LOWEST_NOT_WRONG = 0.90
LEAST_HONEST_LABELS = 0.90
LEAST_KEPT = 0.85
LEAST_SAME_CATEGORY = 0.80
MOST_OTHER = 0.15


class ReportError(ValueError):
    """The grades cannot be read with this sheet."""


@dataclass(frozen=True)
class Counts:
    """For each project, how many fields count for a number (`of`) and how many of them meet it."""

    meets: tuple[int, ...]
    of: tuple[int, ...]


def share(counts: Counts, draws: int = DRAWS, seed: int = SEED) -> dict:
    """The share, and its range by project."""
    top, bottom = sum(counts.meets), sum(counts.of)
    if bottom == 0:
        return {"share": None, "range": None, "count": 0, "of": 0}
    chance = random.Random(seed)  # noqa: S311 - a draw that must be repeatable, not a secret
    found: list[float] = []
    for _ in range(draws):
        meets = of = 0
        for _ in range(len(counts.of)):
            index = chance.randrange(len(counts.of))
            meets += counts.meets[index]
            of += counts.of[index]
        if of:
            found.append(meets / of)
    found.sort()
    low = found[math.floor(0.025 * len(found))]
    high = found[math.ceil(0.975 * len(found)) - 1]
    return {"share": round(top / bottom, 4), "range": [round(low, 4), round(high, 4)],
            "count": top, "of": bottom}  # fmt: skip


def _counts(rows: list[list[tuple[int, int]]]) -> Counts:
    return Counts(tuple(sum(m for m, _ in row) for row in rows),
                  tuple(sum(o for _, o in row) for row in rows))  # fmt: skip


def _answered(shown: dict, answer: dict) -> bool:
    if shown["state"] == "kept":
        return answer.get("grade") in GRADES and answer.get("label") in ("right", "wrong")
    return answer.get("has_it") in ("yes", "no")


def graded(sheet: dict, grades: dict) -> list[str]:
    """The pages whose every field this grader answered, in the order of the sheet."""
    pages = []
    for case in sheet["cases"]:
        given = grades["cases"].get(case["page"], {}).get("fields", {})
        if all(_answered(shown, given.get(name, {})) for name, shown in case["card"].items()):
            pages.append(case["page"])
    return pages


def numbers(
    sheet: dict,
    grades: dict,
    planted: set[tuple[str, str]],
    draws: int = DRAWS,
    pages: Sequence[str] | None = None,
) -> dict:
    """The four numbers of one grader (guideline.md, "The numbers"), on the projects that it
    graded in full, or on `pages` when they are given."""
    chosen = set(graded(sheet, grades) if pages is None else pages)
    names = [field["name"] for field in sheet["fields"]]
    tallies: dict[str, list[list[tuple[int, int]]]] = {
        key: []
        for key in ("not_wrong", "wrong", "right", "kept", "labels", "inferred_not_wrong",
                    "quote_check")
    }  # fmt: skip
    for case in sheet["cases"]:
        if case["page"] not in chosen:
            continue
        given = grades["cases"].get(case["page"], {}).get("fields", {})
        rows: dict[str, list[tuple[int, int]]] = {key: [] for key in tallies}
        for name in names:
            shown = case["card"][name]
            if shown["state"] != "not_found":
                rows["quote_check"].append((int(shown["state"] == "kept"), 1))
            if (case["page"], name) in planted:
                continue
            answer = given.get(name, {})
            if shown["state"] == "kept":
                grade, label = answer["grade"], answer["label"]
                rows["not_wrong"].append((int(grade in NOT_WRONG), 1))
                rows["wrong"].append((int(grade == "wrong"), 1))
                rows["right"].append((int(grade == "right"), 1))
                if grade in NOT_WRONG:
                    rows["kept"].append((1, 1))
                rows["labels"].append((int(label == "right"), 1))
                if shown["label"] == "inferred":
                    rows["inferred_not_wrong"].append((int(grade in NOT_WRONG), 1))
                continue
            has_it = answer["has_it"]
            if has_it == "yes":
                rows["kept"].append((0, 1))
            if shown["state"] == "not_found":
                rows["labels"].append((int(has_it == "no"), 1))
        for key, row in rows.items():
            tallies[key].append(row)
    result: dict = {"projects_graded": len(chosen)}
    result |= {key: share(_counts(rows), draws) for key, rows in tallies.items()}
    return result


def catches(grades: dict, plants: list[dict], pages: Sequence[str]) -> list[dict]:
    """Each planted field, with this grader's grade and whether it was caught. A planted field
    in a project that this grader did not grade is neither caught nor missed."""
    found = []
    for plant in plants:
        answer = grades["cases"].get(plant["page"], {}).get("fields", {}).get(plant["field"], {})
        grade = answer.get("grade")
        in_graded = plant["page"] in pages
        found.append({**plant, "graded": in_graded, "grade": grade if in_graded else None,
                      "caught": (grade in ("partly", "wrong")) if in_graded else None})  # fmt: skip
    return found


def numbers_from(sheet: dict, graded_by: dict[str, list[str]]) -> str | None:
    """The grader whose numbers meet the pass marks: one who graded every project."""
    every = len(sheet["cases"])
    for who in ("maintainer", "second"):
        if len(graded_by[who]) == every:
            return who
    return None


def categories(sheet: dict, first: dict, second: dict, planted: set[tuple[str, str]]) -> dict:
    """The check of the list of categories (design 4.5), on the projects where both graders
    picked one, and the model's category against each grader's own pick."""
    pages = [case["page"] for case in sheet["cases"]]
    picks = [{page: g["cases"].get(page, {}).get("category") for page in pages}
             for g in (first, second)]  # fmt: skip
    both = [page for page in pages if picks[0][page] and picks[1][page]]
    same = sum(picks[0][page] == picks[1][page] for page in both)
    model = {
        case["page"]: case["card"]["category"]["value"]
        for case in sheet["cases"]
        if case["card"]["category"]["state"] == "kept" and (case["page"], "category") not in planted
    }

    def against_model(pick: dict) -> dict:
        shared = [page for page in model if pick[page]]
        return {"same": sum(pick[page] == model[page] for page in shared), "of": len(shared)}

    others = [sum(pick[page] == "Other" for page in pages if pick[page]) for pick in picks]
    picked = [sum(bool(pick[page]) for page in pages) for pick in picks]
    agree = round(same / len(both), 4) if both else None
    other_shares = [round(o / p, 4) if p else None for o, p in zip(others, picked, strict=True)]
    accepted = (
        agree is not None
        and agree >= LEAST_SAME_CATEGORY
        and all(s is not None and s <= MOST_OTHER for s in other_shares)
    )
    return {
        "projects_picked_by_both": len(both),
        "same_category": same,
        "agreement": agree,
        "other_share": {"maintainer": other_shares[0], "second": other_shares[1]},
        "list_accepted": accepted,
        "model_against_maintainer": against_model(picks[0]),
        "model_against_second": against_model(picks[1]),
        "picks": {
            "maintainer": dict(Counter(p for p in picks[0].values() if p)),
            "second": dict(Counter(p for p in picks[1].values() if p)),
        },
    }


def agreement(
    sheet: dict, first: dict, second: dict, planted: set[tuple[str, str]], pages: Sequence[str]
) -> dict:
    """How often the two graders give the same answer to the same question, on the projects
    that both graded."""
    tallies: dict[str, list[int]] = {"grade": [0, 0], "label": [0, 0], "has_it": [0, 0]}
    for case in sheet["cases"]:
        if case["page"] not in pages:
            continue
        answers = [g["cases"].get(case["page"], {}).get("fields", {}) for g in (first, second)]
        for name in case["card"]:
            if (case["page"], name) in planted:
                continue
            for question, tally in tallies.items():
                one = answers[0].get(name, {}).get(question)
                two = answers[1].get(name, {}).get(question)
                if one and two:
                    tally[0] += one == two
                    tally[1] += 1
    result: dict = {"projects_graded_by_both": len(pages)}
    result |= {question: {"same": same, "of": of, "share": round(same / of, 4) if of else None}
               for question, (same, of) in tallies.items()}  # fmt: skip
    return result


def passes(main: dict | None, caught: dict[str, list[dict]]) -> dict:
    """The pass marks of design 13.6, on the numbers of the grader who graded every project.
    The planted fields: each grader catches every planted field in the projects it graded, and
    every planted field is graded by at least one of them."""
    if main is None:
        return {"why_not_decided": "no grader graded every project"}
    not_wrong = main["not_wrong"]
    graded_plants = [plant for plants in caught.values() for plant in plants if plant["graded"]]
    every_plant_seen = all(
        any(p["graded"] for p in plants_of) for plants_of in zip(*caught.values(), strict=True)
    )
    return {
        "faithful": not_wrong["range"] is not None
        and main["wrong"]["share"] <= MOST_WRONG
        and not_wrong["range"][0] >= LOWEST_NOT_WRONG,
        "honest_labels": (main["labels"]["share"] or 0) >= LEAST_HONEST_LABELS,
        "kept": (main["kept"]["share"] or 0) >= LEAST_KEPT,
        "planted": every_plant_seen and all(plant["caught"] for plant in graded_plants),
    }


def every_grade(sheet: dict, first: dict, second: dict) -> list[dict]:
    """Each answer of each grader, by page and field: no text."""
    rows = []
    for case in sheet["cases"]:
        page = case["page"]
        for name in case["card"]:
            row = {"page": page, "field": name, "state": case["card"][name]["state"],
                   "label": case["card"][name]["label"]}  # fmt: skip
            for who, grades in (("maintainer", first), ("second", second)):
                answer = grades["cases"].get(page, {}).get("fields", {}).get(name, {})
                row[who] = {k: answer[k] for k in ("grade", "label", "has_it") if k in answer}
            rows.append(row)
    return rows


def _project_answers(sheet: dict, grades: dict) -> list[dict]:
    keys = ("category", "services", "parser", "changed_after_card")
    return [
        {"page": case["page"]}
        | {key: grades["cases"].get(case["page"], {}).get(key) for key in keys}
        for case in sheet["cases"]
    ]


def report(sheet: dict, key: dict, first: dict, second: dict, draws: int = DRAWS) -> dict:
    for name, grades in (("maintainer", first), ("second grader", second)):
        if grades.get("absent"):
            continue  # this grader did not grade this sheet
        if grades.get("sheet") != sheet["fingerprint"]:
            raise ReportError(f"the grades of the {name} belong to another sheet")
    if key.get("sheet") != sheet["fingerprint"]:
        raise ReportError("the key of the planted fields belongs to another sheet")
    planted = {(plant["page"], plant["field"]) for plant in key["plants"]}
    graded_by = {"maintainer": graded(sheet, first), "second": graded(sheet, second)}
    both = [page for page in graded_by["maintainer"] if page in set(graded_by["second"])]
    graders = {"maintainer": numbers(sheet, first, planted, draws, graded_by["maintainer"]),
               "second": numbers(sheet, second, planted, draws, graded_by["second"])}  # fmt: skip
    caught = {"maintainer": catches(first, key["plants"], graded_by["maintainer"]),
              "second": catches(second, key["plants"], graded_by["second"])}  # fmt: skip
    main = numbers_from(sheet, graded_by)
    to_check = [case["page"] for case in sheet["cases"] if case["parser_check"]]
    checks = [first["cases"].get(page, {}).get("parser") for page in to_check]
    return {
        "test": "test1"
        if sheet.get("instructions_version") in (None, "card-form-1")
        else f"test1-{sheet['instructions_version']}",
        "made_on": datetime.now(UTC).strftime("%Y-%m-%d"),
        "sheet": sheet["fingerprint"],
        "model": sheet["model"],
        "instructions_version": sheet["instructions_version"],
        "projects": len(sheet["cases"]),
        "projects_graded": {who: len(pages) for who, pages in graded_by.items()},
        "planted_fields": len(key["plants"]),
        "draws_for_the_ranges": draws,
        "seed_of_the_ranges": SEED,
        "numbers": graders,
        "numbers_that_meet_the_pass_marks": main,
        "pass_marks": {
            "faithful": f"at most {MOST_WRONG:.0%} wrong, and the low end of not wrong at "
            f"{LOWEST_NOT_WRONG:.0%} or more",
            "honest_labels": f"at least {LEAST_HONEST_LABELS:.0%}",
            "kept": f"at least {LEAST_KEPT:.0%}",
            "planted": "each grader catches every planted field in the projects it graded, "
            "and every planted field is graded",
        },
        "passes": passes(graders[main] if main else None, caught),
        "planted": caught,
        "categories": categories(sheet, first, second, planted),
        "agreement": agreement(sheet, first, second, planted, both),
        "agreement_numbers": {
            "maintainer": graders["maintainer"],
            "second_on_the_same_projects": numbers(sheet, second, planted, draws, both),
        },
        "parser_check": dict(Counter(str(answer) for answer in checks)),
        "answers_before_the_card": {
            "maintainer": _project_answers(sheet, first),
            "second": _project_answers(sheet, second),
        },
        "grades": every_grade(sheet, first, second),
    }


def write(result: dict, folder: Path | None = None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = folder or RESULTS
    path = folder / f"{stamp}-{result['test']}.json"
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return path


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReportError(f"{path.name} cannot be read") from error


def _read_or_none(path: Path) -> dict:
    """The grades of a grader, or none when this grader did not grade this sheet."""
    if not path.exists():
        return {"sheet": None, "cases": {}, "absent": True}
    return _read(path)


def main(argv: Sequence[str]) -> int:
    if len(argv) not in (0, 2) or (argv and argv[0] != "--name"):
        print("usage: python -m evals.test1.report [--name <folder of the sheet in data/evals>]")
        return 2
    name = argv[1] if argv else "test1"
    folder = Path(Settings().data_dir) / "evals" / name
    try:
        result = report(
            _read(folder / DATA_FILE),
            _read(folder / KEY_FILE),
            _read_or_none(folder / MAINTAINER_GRADES),
            _read(folder / SECOND_GRADES),
            DRAWS,
        )
    except ReportError as error:
        print(f"Stopped: {error}")
        return 1
    path = write(result)
    print(f"projects graded: {result['projects_graded']}; the pass marks use the numbers of: "
          f"{result['numbers_that_meet_the_pass_marks']}")  # fmt: skip
    main_numbers = result["numbers"].get(result["numbers_that_meet_the_pass_marks"] or "", {})
    for name in ("not_wrong", "wrong", "kept", "labels", "quote_check"):
        if name in main_numbers:
            number = main_numbers[name]
            print(f"{name}: {number['share']} {number['range']} "
                  f"({number['count']} of {number['of']})")  # fmt: skip
    print(f"passes: {result['passes']}")
    print(f"Written: {path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
