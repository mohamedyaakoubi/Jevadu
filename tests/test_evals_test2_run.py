"""Test 2, the search: the ideas of the pairs, the places of the known projects and the number.
Every project and idea here is invented; the search is a stand-in."""

from __future__ import annotations

from evals.test2 import cases as cases_module
from evals.test2.cases import LOOK_ALIKE, PAIRS, SAME_IDEA, Pair
from evals.test2.ideas import Idea
from evals.test2.run import Case, Project, cases_of, idea_of, places, run, share

PEBBLE = Project(
    1,
    "https://ethglobal.com/showcase/pebble-x1y2z",
    "Pebble Pay",
    "Pebble Pay: pay a street vendor with a coin.",
    "Pebble Pay is a wallet.",
)
CEDAR = Project(
    2,
    "https://ethglobal.com/showcase/cedar-x1y2z",
    "Cedar Post",
    "Parcels, fast.",
    "Cedar Post logs every parcel. It is fast.",
)
FERN = Project(
    3,
    "https://hedera.com/blog/winners#fern",
    "Fern Vote",
    "",
    "Fern Vote: a ballot for a small club, counted in the open. More text here.",
)
PROJECTS = {p.page: p for p in (PEBBLE, CEDAR, FERN)}
PAGE_OF = {p.id: p.page for p in PROJECTS.values()}  # fmt: skip


def test_the_idea_of_a_project_leaves_out_its_name() -> None:
    assert idea_of(PEBBLE) == "pay a street vendor with a coin."
    assert idea_of(CEDAR) == "logs every parcel."  # a short line under three words
    assert idea_of(FERN) == "a ballot for a small club, counted in the open."


def test_the_pairs_are_searched_both_ways_and_the_ideas_take_their_partners(monkeypatch) -> None:
    pairs = (
        Pair(PEBBLE.page, CEDAR.page, SAME_IDEA, "same name", "invented"),
        Pair(PEBBLE.page, FERN.page, LOOK_ALIKE, "same name", "invented"),
    )
    monkeypatch.setattr("evals.test2.run.PAIRS", pairs)
    ideas = [Idea(4, PEBBLE.page, "a coin box for sellers", False),
             Idea(5, FERN.page, "a ballot for a small club", True)]  # fmt: skip
    found = cases_of(PROJECTS, ideas)
    assert [(c.kind, c.asked_by, c.known, c.counted) for c in found] == [
        (SAME_IDEA, PEBBLE.page, (CEDAR.page,), True),
        (SAME_IDEA, CEDAR.page, (PEBBLE.page,), True),
        (LOOK_ALIKE, PEBBLE.page, (FERN.page,), False),
        (LOOK_ALIKE, FERN.page, (PEBBLE.page,), False),
        ("idea", "", (PEBBLE.page, CEDAR.page), True),
        ("idea", "", (FERN.page,), False),
    ]
    assert found[0].group == found[1].group == "pair 1"


def test_the_asking_project_is_left_out_of_its_own_results() -> None:
    case = Case(SAME_IDEA, "same name", PEBBLE.page, (CEDAR.page,), "an idea")
    asked = []

    def search(idea: str, limit: int) -> list[int]:
        asked.append(limit)
        return [1] + [100 + n for n in range(9)] + [2]  # Pebble first, Cedar eleventh

    page_of = PAGE_OF | {100 + n: f"https://ethglobal.com/showcase/other-{n}" for n in range(9)}
    assert places(case, search, PROJECTS, page_of) == [10]
    assert asked == [11]


def test_the_number_counts_the_known_projects_and_draws_whole_cases() -> None:
    assert share({"pair 1": (2, 2), "pair 2": (0, 2), "idea 4": (1, 1)}, draws=200) | {} == {
        "share": 0.6, "range": share({"pair 1": (2, 2), "pair 2": (0, 2), "idea 4": (1, 1)},
                                     draws=200)["range"], "found": 3, "known": 5}  # fmt: skip
    assert share({}, draws=10)["share"] is None


def test_a_run_gives_the_number_the_pass_mark_and_the_look_alikes_apart() -> None:
    found_cases = [
        Case(SAME_IDEA, "same name", PEBBLE.page, (CEDAR.page,), "x", True, "pair 1"),
        Case(SAME_IDEA, "same name", CEDAR.page, (PEBBLE.page,), "y", True, "pair 1"),
        Case(LOOK_ALIKE, "same name", PEBBLE.page, (FERN.page,), "x", False, "pair 2"),
        Case("idea", "the maintainer's words", "", (FERN.page,), "z", False, "idea 5"),
    ]

    def search(idea: str, limit: int) -> list[int]:
        return {"x": [1, 2], "y": [2, 3], "z": [3]}[idea]  # "y" misses Pebble

    result = run(found_cases, search, PROJECTS, PAGE_OF, draws=100)
    assert result["numbers"]["all"]["found"] == 1 and result["numbers"]["all"]["known"] == 2
    assert result["passes"] is False
    assert result["look_alike_shown"] == {"shown": 0, "of": 1}
    assert result["ideas_counted_apart"] == {"found": 1, "known": 1}
    assert all("x" not in str(row) or row["idea_sha256"] for row in result["cases"])
    assert all("idea" not in key for row in result["cases"] for key in row if key != "idea_sha256")


def test_other_setups_are_counted_on_the_same_cases() -> None:
    found_cases = [
        Case(SAME_IDEA, "same name", PEBBLE.page, (CEDAR.page,), "x", True, "pair 1"),
        Case(LOOK_ALIKE, "same name", PEBBLE.page, (FERN.page,), "x", False, "pair 2"),
    ]

    def search(idea: str, limit: int) -> list[int]:
        return [1, 3]  # the product misses Cedar

    def setups(idea: str) -> dict[str, list[int]]:
        return {"meaning only": [1, 2], "words only": [3]}

    result = run(found_cases, search, PROJECTS, PAGE_OF, draws=50, setups=setups)
    assert result["numbers"]["all"]["found"] == 0
    assert result["other_setups"] == {
        "meaning only": {"found": 1, "known": 1, "share": 1.0},
        "words only": {"found": 0, "known": 1, "share": 0.0},
    }


def test_the_frozen_pairs_are_well_formed() -> None:
    assert len(PAIRS) == len({frozenset((p.first, p.second)) for p in PAIRS})
    assert all(p.first != p.second for p in PAIRS)
    assert {p.kind for p in PAIRS} == {SAME_IDEA, LOOK_ALIKE}
    assert all(p.reason and p.source for p in PAIRS)
    for pair in PAIRS:
        for page in (pair.first, pair.second):
            assert page.startswith((cases_module.SHOWCASE, cases_module.POSTS, cases_module.AFRICA))
