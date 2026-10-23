"""The version of a repository (collect/github_commits.py): the commit ID and its date are kept,
and the people of the commit are not. Every answer is invented."""

from __future__ import annotations

import json

from checkfakes import COMMIT, REPO, commits_answer
from hackathon_memory.collect.github_commits import (
    BLOCKED,
    EMPTY,
    FOUND,
    GONE,
    commits_address,
    kept_of,
)
from hackathon_memory.collect.polite import FetchResult


def fetched(status: int, body: bytes) -> FetchResult:
    url = commits_address(REPO)
    return FetchResult(url, url, status, body, "application/json", "2026-10-18T08:00:00Z")


def test_the_address_asks_for_the_newest_commit_only() -> None:
    assert commits_address(REPO) == (
        "https://api.github.com/repos/sample-org/pebble-pay/commits?per_page=1"
    )


def test_only_the_commit_id_and_its_date_are_kept() -> None:
    body, facts, taken_out = kept_of(fetched(200, commits_answer()))
    assert json.loads(body) == {"sha": COMMIT, "date": "2026-03-08T09:30:00Z"}
    assert b"Invented" not in body and b"invented" not in body  # no name, address or message
    assert facts == {} and taken_out["people_dropped"] is True


def test_an_answer_with_no_commit_id_keeps_nothing() -> None:
    for answer in (b"[]", b"not json", json.dumps([{"sha": "main"}]).encode()):
        body, facts, _ = kept_of(fetched(200, answer))
        assert body == b"{}" and facts["kept"] == "nothing"


def test_the_statuses_are_read_from_the_answers(tmp_path) -> None:  # noqa: ANN001
    from hackathon_memory.collect.github_commits import read_version, saved_version
    from hackathon_memory.collect.rawstore import RawStore

    assert saved_version(RawStore(tmp_path / "none"), REPO) is None
    cases = [
        (200, commits_answer(), FOUND),
        (409, b'{"message": "Git Repository is empty."}', EMPTY),
        (404, b'{"message": "Not Found"}', GONE),
        (451, b'{"message": "blocked"}', BLOCKED),
    ]
    for status, answer, kind in cases:
        store = RawStore(tmp_path / str(status))  # a saved answer is never saved again
        fetch = fetched(status, answer)
        body, facts, taken_out = kept_of(fetch)
        saved = store.save(
            fetch,
            body,
            received=answer,
            collector="TestTool/0.1.0",
            team_cut=taken_out,
            answer=facts,
            suffix=".json",
        )
        version = read_version(saved)
        assert version.status == kind
        assert (version.sha == COMMIT) is (kind == FOUND)
