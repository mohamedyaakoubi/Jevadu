"""GitHub's answers, asked again as the repositories change (design 7.3, 25 October 2026), on a
stand-in GitHub: the newest answer counts, a request carries the ETag of the last answer, a 304
is kept as a record with no body, nothing saved is replaced, and the code is read again only for
a new commit."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from checkfakes import (
    COMMIT,
    DOWNLOAD,
    NOW,
    REPO,
    commits_answer,
    facts_answer,
    github,
    readme_answer,
)
from fakes import ARCHIVE_COMMIT, Reply, archive
from hackathon_memory.collect.answers import AGAIN, Answers, etag_of
from hackathon_memory.collect.github import archive_address, readme_address
from hackathon_memory.collect.github_code import (
    again_store,
    read_new_commits,
    save_reading,
    saved_code,
)
from hackathon_memory.collect.github_commits import commits_address, fetch_versions, saved_version
from hackathon_memory.collect.github_facts import facts_address, facts_again, fetch_facts
from hackathon_memory.collect.github_facts import saved_facts as facts_of
from hackathon_memory.collect.github_readmes import fetch_readmes, readmes_again, saved_readme
from hackathon_memory.collect.polite import FetchResult, RequestCount, StopCollecting
from hackathon_memory.parse.hedera_code import CodeScan

COLLECTOR = "TestTool/0.1.0"
DAY = timedelta(hours=24)
LATER = NOW + timedelta(days=2)  # when the answers of NOW are two days old


def first_facts(tmp_path: Path, replies: list[Reply]) -> tuple:
    """GitHub answers the facts with `replies`, one for each visit; the first answer is saved."""
    client, site = github(tmp_path, {facts_address(REPO): replies})
    answers = Answers(tmp_path / "raw")
    fetch_facts(client, answers, [REPO], collector=COLLECTOR)
    return client, site, answers


def test_a_first_answer_keeps_its_etag_and_a_second_ask_is_conditional(tmp_path: Path) -> None:
    replies = [
        Reply(200, facts_answer(), {"ETag": 'W/"one"'}),
        Reply(304, b"", {"ETag": 'W/"one"'}),
    ]
    client, site, answers = first_facts(tmp_path, replies)
    assert etag_of(answers.load(facts_address(REPO), ".json")) == 'W/"one"'
    client.now = lambda: LATER  # the moment of the answer asked again
    done = facts_again(client, answers, [REPO], collector=COLLECTOR, older_than=DAY,
                       now=lambda: LATER)  # fmt: skip
    assert site.seen[-1].headers["If-None-Match"] == 'W/"one"'
    assert (done.asked, done.unchanged, done.changed, done.answered) == (1, 1, [], [REPO])
    newest = answers.load(facts_address(REPO), ".json")
    assert newest.meta["status"] == 200  # the content is the first answer's
    assert newest.meta["answered_at"] == "2026-10-11T02:00:00Z"
    assert facts_of(answers, REPO).pushed_at is not None  # its facts still read


def test_a_304_is_kept_with_no_body_and_dates_the_answer(tmp_path: Path) -> None:
    replies = [Reply(200, facts_answer(), {"ETag": '"one"'}), Reply(304, b"")]
    client, _, answers = first_facts(tmp_path, replies)
    client.now = lambda: LATER  # the moment of the answer asked again
    facts_again(client, answers, [REPO], collector=COLLECTOR, older_than=DAY, now=lambda: LATER)
    kept = list((tmp_path / "raw" / AGAIN).rglob("*.meta.json"))
    record = json.loads(kept[0].read_text(encoding="utf-8"))
    assert (len(kept), record["status"], record["bytes"]) == (1, 304, 0)
    assert facts_of(answers, REPO).fetched_at == "2026-10-13T02:00:00Z"  # GitHub confirmed it


def test_a_young_answer_is_not_asked_again(tmp_path: Path) -> None:
    client, site, answers = first_facts(tmp_path, [Reply(200, facts_answer())])
    asked = len(site.seen)
    soon = NOW + timedelta(hours=3)
    done = facts_again(client, answers, [REPO], collector=COLLECTOR, older_than=DAY,
                       now=lambda: soon)  # fmt: skip
    assert (done.fresh, done.asked, len(site.seen)) == (1, 0, asked)


def test_an_address_never_asked_is_left_to_the_steps(tmp_path: Path) -> None:
    client, site = github(tmp_path, {})
    done = facts_again(client, Answers(tmp_path / "raw"), [REPO], collector=COLLECTOR,
                       older_than=DAY, now=lambda: LATER)  # fmt: skip
    assert (done.never_asked, done.asked, site.seen) == (1, 0, [])


def test_a_changed_answer_is_the_newest_and_the_first_stays(tmp_path: Path) -> None:
    replies = [
        Reply(200, facts_answer()),
        Reply(200, facts_answer(pushed_at="2026-10-12T08:00:00Z")),
    ]
    client, _, answers = first_facts(tmp_path, replies)
    first = (tmp_path / "raw").glob("*.json")
    before = {path.name: path.read_bytes() for path in first}
    done = facts_again(client, answers, [REPO], collector=COLLECTOR, older_than=DAY,
                       now=lambda: LATER)  # fmt: skip
    assert done.changed == [REPO]
    assert facts_of(answers, REPO).pushed_at.isoformat() == "2026-10-12T08:00:00+00:00"
    after = {path.name: path.read_bytes() for path in (tmp_path / "raw").glob("*.json")}
    assert after == before  # nothing saved is replaced


def test_the_same_content_without_an_etag_counts_as_unchanged(tmp_path: Path) -> None:
    client, _, answers = first_facts(tmp_path, [Reply(200, facts_answer())])
    done = facts_again(client, answers, [REPO], collector=COLLECTOR, older_than=DAY,
                       now=lambda: LATER)  # fmt: skip
    assert (done.unchanged, done.changed) == (1, [])


def test_a_readme_gone_since_is_the_newest_answer(tmp_path: Path) -> None:
    gone = Reply(404, b'{"message": "Not Found"}')
    client, _ = github(tmp_path, {readme_address(REPO): [Reply(200, readme_answer()), gone]})
    answers = Answers(tmp_path / "raw")
    fetch_readmes(client, answers, [REPO], collector=COLLECTOR)
    assert saved_readme(answers, REPO).status == "found"
    readmes_again(client, answers, [REPO], collector=COLLECTOR, older_than=DAY, now=lambda: LATER)
    assert saved_readme(answers, REPO).status == "none"


def test_a_stop_ends_the_run_and_keeps_what_was_saved(tmp_path: Path) -> None:
    client, _, answers = first_facts(tmp_path, [Reply(200, facts_answer())])
    client.is_enabled = lambda: False  # the switch is turned off
    done = facts_again(client, answers, [REPO, REPO], collector=COLLECTOR, older_than=DAY,
                       now=lambda: LATER)  # fmt: skip
    assert done.stopped is not None and done.left_for_later == 2
    assert facts_of(answers, REPO) is not None


def test_the_limit_of_a_day_stops_the_requests_and_says_so(tmp_path: Path) -> None:
    count = RequestCount(tmp_path / "count.json", "api.github.com", limit=100, daily_limit=2,
                         now=lambda: NOW)  # fmt: skip
    count.add_one()
    count.add_one()
    assert (count.left(), count.day_is_full()) == (0, True)
    client, _ = github(tmp_path, {facts_address(REPO): Reply(200, facts_answer())})
    client.count = count
    with pytest.raises(StopCollecting, match="for one day"):
        client.get(facts_address(REPO))
    tomorrow = RequestCount(tmp_path / "count.json", "api.github.com", limit=100, daily_limit=2,
                            now=lambda: NOW + timedelta(days=1))  # fmt: skip
    assert tomorrow.left() == 2


def code_store(tmp_path: Path, commit: str | None) -> Answers:
    """A saved reading of the code of REPO, made from `commit`."""
    answers = Answers(tmp_path / "raw")
    scan = CodeScan(commit=commit, files=1, archive_bytes=10, archive_sha256="a" * 64)
    fetch = FetchResult(archive_address(REPO), DOWNLOAD, 200, b"", "application/x-gzip",
                        "2026-10-11T02:00:00Z")  # fmt: skip
    save_reading(answers, fetch, scan, COLLECTOR)
    return answers


def test_the_code_is_read_again_only_for_a_new_commit(tmp_path: Path) -> None:
    pages = {commits_address(REPO): Reply(200, commits_answer()),
             archive_address(REPO): Reply(302, b"", {"Location": DOWNLOAD}),
             DOWNLOAD: Reply(200, archive({"src/a.ts": b"// nothing"}))}  # fmt: skip
    client, site = github(tmp_path, pages)
    same = code_store(tmp_path / "same", COMMIT)
    fetch_versions(client, same, [REPO], collector=COLLECTOR)
    asked = len(site.seen)
    done = read_new_commits(client, same, [REPO], collector=COLLECTOR)
    assert (done.fresh, done.asked, len(site.seen)) == (1, 0, asked)
    older = code_store(tmp_path / "older", "f" * 40)
    fetch_versions(client, older, [REPO], collector=COLLECTOR)
    done = read_new_commits(client, older, [REPO], collector=COLLECTOR)
    assert (done.asked, done.changed) == (1, [REPO])
    newest = saved_code(older, REPO)
    assert newest.scan.commit == ARCHIVE_COMMIT  # the commit of the archive read again
    assert len(list((tmp_path / "older" / "raw" / AGAIN).rglob("*.meta.json"))) == 1
    assert saved_version(older, REPO).sha == COMMIT


def test_the_newest_reading_of_the_code_counts_by_its_time(tmp_path: Path) -> None:
    """A reading made again for a newer reader (code-format-3) was found first before 25 October
    2026; a reading of a newer commit is newer still."""
    answers = code_store(tmp_path, "f" * 40)

    def reading(day: str, files: int) -> tuple[FetchResult, CodeScan]:
        fetch = FetchResult(archive_address(REPO), DOWNLOAD, 200, b"", "application/x-gzip",
                            f"2026-10-{day}T02:00:00Z")  # fmt: skip
        return fetch, CodeScan(commit=COMMIT, files=files, archive_bytes=10,
                               archive_sha256="b" * 64)  # fmt: skip

    fetch, scan = reading("12", 5)
    save_reading(again_store(answers, 3), fetch, scan, COLLECTOR)
    assert saved_code(answers, REPO).scan.files == 5
    fetch, scan = reading("14", 7)
    save_reading(answers.store_for(fetch), fetch, scan, COLLECTOR)
    assert saved_code(answers, REPO).scan.files == 7
