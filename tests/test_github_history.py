"""How the code of a repository changed between two hackathons (collect/github_history.py): the
newest commit on or before a day, and the comparison of two commits, of which only the numbers are
kept. Every answer is invented."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from checkfakes import COMMIT, LATER_COMMIT, REPO, commits_answer, compare_answer, github
from fakes import Reply
from hackathon_memory.collect.github import allowed
from hackathon_memory.collect.github_history import (
    BLOCKED,
    FOUND,
    GONE,
    MOST_FILES,
    Change,
    compare_address,
    compare_page,
    fetch_changes,
    fetch_untils,
    kept_change,
    saved_change,
    saved_until,
    until_address,
)
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore

COLLECTOR = "TestTool/0.1.0"
MARCH, JUNE = date(2026, 3, 8), date(2026, 6, 14)  # the last days of two invented events


def fetched(status: int, body: bytes) -> FetchResult:
    url = compare_address(REPO, COMMIT, LATER_COMMIT)
    return FetchResult(url, url, status, body, "application/json", "2026-10-31T08:00:00Z")


def test_the_addresses_ask_for_one_commit_and_one_comparison() -> None:
    assert until_address(REPO, MARCH) == (
        "https://api.github.com/repos/sample-org/pebble-pay/commits"
        "?until=2026-03-08T23:59:59Z&per_page=1"
    )
    assert compare_address(REPO, COMMIT, LATER_COMMIT) == (
        f"https://api.github.com/repos/sample-org/pebble-pay/compare/{COMMIT}...{LATER_COMMIT}?per_page=1"
    )
    assert compare_page(REPO, COMMIT, LATER_COMMIT) == f"{REPO}/compare/{COMMIT}...{LATER_COMMIT}"


def test_only_a_comparison_of_two_commit_ids_may_hold_dots() -> None:
    """The allow list refuses ".." in a path, so that no address climbs out of /repos/; the three
    dots between two commit IDs of a comparison are the one exception."""
    assert allowed(compare_address(REPO, COMMIT, LATER_COMMIT))
    assert allowed(compare_address(REPO, COMMIT[:7], LATER_COMMIT[:7]))
    base = "https://api.github.com/repos/sample-org/pebble-pay"
    for refused in (f"{base}/compare/main...dev", f"{base}/compare/{COMMIT}..{LATER_COMMIT}",
                    f"{base}/compare/{COMMIT}...{LATER_COMMIT}/../../../users",
                    f"{base}/../../users/compare/{COMMIT}...{LATER_COMMIT}",
                    f"https://api.github.com/compare/{COMMIT}...{LATER_COMMIT}"):  # fmt: skip
        assert not allowed(refused), refused


def test_only_the_numbers_of_a_comparison_are_kept() -> None:
    body, facts, taken_out = kept_change(fetched(200, compare_answer()))
    assert json.loads(body) == {"status": "ahead", "ahead_by": 4, "behind_by": 0,
                                "total_commits": 4, "files": 3, "additions": 60,
                                "deletions": 3}  # fmt: skip
    # no person, message, file name, patch or commit ID
    for word in (b"nvented", b"src/", b"@@", LATER_COMMIT.encode()):
        assert word not in body
    assert facts == {} and taken_out["people_dropped"] is True
    assert taken_out["file_names_dropped"] == 3


def test_an_answer_with_no_count_of_commits_keeps_nothing() -> None:
    for answer in (b"not json", b"[]", json.dumps({"status": "ahead"}).encode()):
        body, facts, _ = kept_change(fetched(200, answer))
        assert body == b"{}" and facts["kept"] == "nothing"
    body, facts, taken_out = kept_change(fetched(404, b'{"message": "Not Found"}'))
    assert facts == {"message": "Not Found"} and taken_out is None


def test_three_hundred_files_are_a_floor() -> None:
    """GitHub lists at most 300 files of a comparison, so at 300 the counts are at least these."""
    assert Change("ahead", 40, MOST_FILES, 9_000, 800).files_capped
    assert not Change("ahead", 3, MOST_FILES - 1, 50, 2).files_capped


def test_each_answer_is_asked_once_and_read_back(tmp_path: Path) -> None:
    pages = {
        until_address(REPO, MARCH): Reply(200, commits_answer()),
        until_address(REPO, JUNE): Reply(200, commits_answer(LATER_COMMIT).replace(b"2026-03-08",
                                                                            b"2026-06-12")),
        compare_address(REPO, COMMIT, LATER_COMMIT): Reply(200, compare_answer()),
    }  # fmt: skip
    client, site = github(tmp_path, pages)
    store = RawStore(tmp_path / "answers")
    untils = fetch_untils(client, store, [(REPO, MARCH), (REPO, JUNE), (REPO, MARCH)],
                          collector=COLLECTOR)  # fmt: skip
    assert (untils.asked, untils.by_status[FOUND]) == (2, 2)  # the same day twice: one address
    march, june = saved_until(store, REPO, MARCH), saved_until(store, REPO, JUNE)
    assert (march.sha, june.sha) == (COMMIT, LATER_COMMIT)
    assert june.made_at.date() == date(2026, 6, 12)
    changes = fetch_changes(client, store, [(REPO, COMMIT, LATER_COMMIT)], collector=COLLECTOR)
    assert changes.asked == 1
    assert saved_change(store, REPO, COMMIT, LATER_COMMIT) == Change("ahead", 4, 3, 60, 3)
    before = len(site.seen)
    again = fetch_untils(client, store, [(REPO, MARCH), (REPO, JUNE)], collector=COLLECTOR)
    changes = fetch_changes(client, store, [(REPO, COMMIT, LATER_COMMIT)], collector=COLLECTOR)
    assert len(site.seen) == before  # a saved answer is never asked for again
    assert (again.already_saved, changes.already_saved) == (2, 1)
    assert saved_until(store, REPO, date(2026, 9, 13)) is None  # a day never asked for
    assert all(request.headers["User-Agent"].startswith("TestTool-research")
               for request in site.seen)  # fmt: skip


def test_a_comparison_that_is_not_there_reads_as_none(tmp_path: Path) -> None:
    """A repository that is gone, or that GitHub blocked: the answer is saved, and the timeline
    says that the code is not compared."""
    blocked = b'{"message": "Repository access blocked"}'
    pages = {compare_address(REPO, COMMIT, LATER_COMMIT): Reply(404, b'{"message": "Not Found"}'),
             compare_address(REPO, LATER_COMMIT, COMMIT): Reply(451, blocked)}  # fmt: skip
    client, _ = github(tmp_path, pages)
    store = RawStore(tmp_path / "answers")
    run = fetch_changes(client, store, [(REPO, COMMIT, LATER_COMMIT), (REPO, LATER_COMMIT, COMMIT)],
                        collector=COLLECTOR)  # fmt: skip
    assert (run.by_status[GONE], run.by_status[BLOCKED]) == (1, 1)
    assert saved_change(store, REPO, COMMIT, LATER_COMMIT) is None
    assert saved_change(store, REPO, LATER_COMMIT, COMMIT) is None
