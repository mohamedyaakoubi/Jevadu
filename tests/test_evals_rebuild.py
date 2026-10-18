"""The comparison of a database built again with the one in use (evals/rebuild.py). Every project
here is invented."""

from __future__ import annotations

import pytest

from evals.rebuild import compare, counts
from searchfakes import three_projects


def test_the_same_counts_are_said_the_same_and_the_others_differ() -> None:
    in_use = {"projects": {"full_card": 3}, "cards": {"v": 2}}
    rebuilt = {"projects": {"full_card": 3}, "cards": {"v": 1}, "events": {"all": 1}}
    table = compare(in_use, rebuilt)
    assert table["projects"]["full_card"] == {"in_use": 3, "rebuilt": 3, "same": True}
    assert table["cards"]["v"]["same"] is False
    assert table["events"]["all"] == {"in_use": 0, "rebuilt": 1, "same": False}


@pytest.mark.integration
def test_the_counts_of_one_database_hold_numbers_only(empty_database: str) -> None:
    database = three_projects(empty_database)
    found = counts(database)
    assert found["projects"] == {"full_card": 3} and found["events"] == {"all": 1}
    assert found["linked_across_events"] == {"groups": 0, "projects": 0}
    assert all(isinstance(number, int) for parts in found.values() for number in parts.values())
