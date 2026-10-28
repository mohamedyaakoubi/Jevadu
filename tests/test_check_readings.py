"""What a reading of a project changed, in plain words (check/readings.py, design 7.3). Every
state here is invented."""

from __future__ import annotations

from datetime import UTC, datetime

from hackathon_memory.check.readings import GONE, ProjectState, changes_of

BEFORE = ProjectState(
    code_status="found",
    last_push_at=datetime(2026, 3, 8, 12, tzinfo=UTC),
    readme_sha256="a" * 64,
    code_commit="7260ea7290637399c6ac181ed893a567144d96eb",
    services_in_code=frozenset({"Consensus Service (topics)"}),
    ids=frozenset({"0.0.3456781"}),
    statuses={"0.0.3456781": "not_found"},
    own_events=40,
)


def test_nothing_changed_says_nothing() -> None:
    assert changes_of(BEFORE, BEFORE) == ()


def test_each_change_is_a_sentence_in_a_fixed_order() -> None:
    after = ProjectState(
        code_status="found",
        last_push_at=datetime(2026, 10, 26, 9, tzinfo=UTC),
        readme_sha256="b" * 64,
        code_commit="3f2a1c9" + "0" * 33,
        services_in_code=frozenset({"Token Service"}),
        ids=frozenset({"0.0.3456781", "0.0.4870201"}),
        statuses={"0.0.3456781": "proof_found", "0.0.4870201": "proof_found"},
        own_events=52,
    )
    assert changes_of(BEFORE, after) == (
        "Last push on GitHub: 26 October 2026 (before: 8 March 2026).",
        "The README changed.",
        "New code read, at commit 3f2a1c9.",
        "Its code now calls Token Service.",
        "Its code no longer calls Consensus Service (topics).",
        "New Hedera ID: 0.0.4870201.",
        "0.0.3456781 on the ledger: found (before: ID not found).",
        "12 new transactions of its own IDs.",
    )


def test_a_repository_that_goes_and_comes_back() -> None:
    gone = ProjectState(code_status=GONE, readme_sha256=None, ids=BEFORE.ids,
                        statuses=BEFORE.statuses, own_events=40)  # fmt: skip
    went = changes_of(BEFORE, gone)
    assert went[0] == "The repository can no longer be read on GitHub."
    assert "The README is no longer found." in went
    back = changes_of(gone, BEFORE)
    assert (
        back[0] == "The repository can be read on GitHub again." and "A README was found." in back
    )


def test_one_new_transaction_and_a_first_reading() -> None:
    assert changes_of(BEFORE, ProjectState(**{**BEFORE.__dict__, "own_events": 41})) == (
        "1 new transaction of its own IDs.",
    )
    first = changes_of(ProjectState(), BEFORE)  # read for the first time
    assert "Last push on GitHub: 8 March 2026." in first and "A README was found." in first
    assert "Its code now calls Consensus Service (topics)." in first
