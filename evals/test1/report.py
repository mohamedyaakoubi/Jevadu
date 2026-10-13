"""The numbers of Test 1, from the grades (design 13.2 and 13.6). guideline.md defines them.

    python -m evals.test1.report

It reads the sheet, the key of its planted fields and the grades of the two graders, all in
data/evals/test1, and writes evals/results/<UTC time>-test1.json: the four numbers of each grader
with their ranges, the pass marks, the planted fields and whether each grader caught them, the
check of the list of categories, how often the graders agree, and every grade by page address
and field name. No text of a page, of a card or of a note goes into that file (design 13.1).

The numbers that meet the pass marks come from the maintainer's grades. A range is computed by
project: the projects are drawn again with replacement, DRAWS times, with a fixed seed, and the
range holds the middle 95 of every 100 results (design 13.1).
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


def numbers(sheet: dict, grades: dict, planted: set[tuple[str, str]], draws: int = DRAWS) -> dict:
    """The four numbers of one grader (guideline.md, "The numbers")."""
    names = [field["name"] for field in sheet["fields"]]
    tallies: dict[str, list[list[tuple[int, int]]]] = {
        key: []
        for key in ("not_wrong", "wrong", "right", "kept", "labels", "inferred_not_wrong",
                    "quote_check")
    }  # fmt: skip
    not_graded = 0
    for case in sheet["cases"]:
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
                grade, label = answer.get("grade"), answer.get("label")
                if grade not in ("right", "partly", "wrong") or label not in ("right", "wrong"):
                    not_graded += 1
                    continue
                rows["not_wrong"].append((int(grade in NOT_WRONG), 1))
                rows["wrong"].append((int(grade == "wrong"), 1))
                rows["right"].append((int(grade == "right"), 1))
                if grade in NOT_WRONG:
                    rows["kept"].append((1, 1))
                rows["labels"].append((int(label == "right"), 1))
                if shown["label"] == "inferred":
                    rows["inferred_not_wrong"].append((int(grade in NOT_WRONG), 1))
                continue
            has_it = answer.get("has_it")
            if has_it not in ("yes", "no"):
                not_graded += 1
                continue
            if has_it == "yes":
                rows["kept"].append((0, 1))
            if shown["state"] == "not_found":
                rows["labels"].append((int(has_it == "no"), 1))
        for key, row in rows.items():
            tallies[key].append(row)
    result = {key: share(_counts(rows), draws) for key, rows in tallies.items()}
    result["fields_not_graded"] = not_graded
    return result


def catches(grades: dict, plants: list[dict]) -> list[dict]:
    """Each planted field, with this grader's grade and whether it was caught."""
    found = []
    for plant in plants:
        answer = grades["cases"].get(plant["page"], {}).get("fields", {}).get(plant["field"], {})
        grade = answer.get("grade")
        found.append({**plant, "grade": grade, "caught": grade in ("partly", "wrong")})
    return found


def categories(sheet: dict, first: dict, second: dict, planted: set[tuple[str, str]]) -> dict:
    """The check of the list of categories (design 4.5), and the model's category against each
    grader's own pick."""
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


def agreement(sheet: dict, first: dict, second: dict, planted: set[tuple[str, str]]) -> dict:
    """How often the two graders give the same answer to the same question."""
    tallies: dict[str, list[int]] = {"grade": [0, 0], "label": [0, 0], "has_it": [0, 0]}
    for case in sheet["cases"]:
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
    return {question: {"same": same, "of": of, "share": round(same / of, 4) if of else None}
            for question, (same, of) in tallies.items()}  # fmt: skip


def passes(maintainer: dict, caught: dict[str, list[dict]]) -> dict:
    """The pass marks of design 13.6, on the maintainer's numbers."""
    not_wrong = maintainer["not_wrong"]
    marks = {
        "faithful": not_wrong["range"] is not None
        and maintainer["wrong"]["share"] <= MOST_WRONG
        and not_wrong["range"][0] >= LOWEST_NOT_WRONG,
        "honest_labels": (maintainer["labels"]["share"] or 0) >= LEAST_HONEST_LABELS,
        "kept": (maintainer["kept"]["share"] or 0) >= LEAST_KEPT,
        "planted": all(plant["caught"] for plants in caught.values() for plant in plants),
    }
    if maintainer["fields_not_graded"]:
        return {name: None for name in marks} | {"why_not_decided": "some fields are not graded"}
    return marks


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
        if grades.get("sheet") != sheet["fingerprint"]:
            raise ReportError(f"the grades of the {name} belong to another sheet")
    if key.get("sheet") != sheet["fingerprint"]:
        raise ReportError("the key of the planted fields belongs to another sheet")
    planted = {(plant["page"], plant["field"]) for plant in key["plants"]}
    graders = {"maintainer": numbers(sheet, first, planted, draws),
               "second": numbers(sheet, second, planted, draws)}  # fmt: skip
    caught = {"maintainer": catches(first, key["plants"]),
              "second": catches(second, key["plants"])}  # fmt: skip
    to_check = [case["page"] for case in sheet["cases"] if case["parser_check"]]
    checks = [first["cases"].get(page, {}).get("parser") for page in to_check]
    return {
        "test": "test1",
        "made_on": datetime.now(UTC).strftime("%Y-%m-%d"),
        "sheet": sheet["fingerprint"],
        "model": sheet["model"],
        "instructions_version": sheet["instructions_version"],
        "projects": len(sheet["cases"]),
        "planted_fields": len(key["plants"]),
        "draws_for_the_ranges": draws,
        "seed_of_the_ranges": SEED,
        "numbers": graders,
        "pass_marks": {
            "faithful": f"at most {MOST_WRONG:.0%} wrong, and the low end of not wrong at "
            f"{LOWEST_NOT_WRONG:.0%} or more",
            "honest_labels": f"at least {LEAST_HONEST_LABELS:.0%}",
            "kept": f"at least {LEAST_KEPT:.0%}",
            "planted": "both graders catch every planted field",
        },
        "passes": passes(graders["maintainer"], caught),
        "planted": caught,
        "categories": categories(sheet, first, second, planted),
        "agreement": agreement(sheet, first, second, planted),
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
    path = folder / f"{stamp}-test1.json"
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return path


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReportError(f"{path.name} cannot be read") from error


def main(argv: Sequence[str]) -> int:
    if argv:
        print("usage: python -m evals.test1.report")
        return 2
    folder = Path(Settings().data_dir) / "evals" / "test1"
    try:
        result = report(
            _read(folder / DATA_FILE),
            _read(folder / KEY_FILE),
            _read(folder / MAINTAINER_GRADES),
            _read(folder / SECOND_GRADES),
            DRAWS,
        )
    except ReportError as error:
        print(f"Stopped: {error}")
        return 1
    path = write(result)
    mine = result["numbers"]["maintainer"]
    for name in ("not_wrong", "wrong", "kept", "labels", "quote_check"):
        number = mine[name]
        print(f"{name}: {number['share']} {number['range']} ({number['count']} of {number['of']})")
    print(f"passes: {result['passes']}")
    print(f"Written: {path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
