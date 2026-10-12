"""The facts of a repository are asked for once and saved without the account. All invented."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import SecretStr

from fakes import FakeSite, FakeTime, Reply, session_for
from hackathon_memory.collect.github import GitHubClient, allowed
from hackathon_memory.collect.github_facts import (
    BLOCKED,
    FOUND,
    GONE,
    SUFFIX,
    facts_address,
    fetch_facts,
    kept_of,
    saved_facts,
)
from hackathon_memory.collect.polite import CollectorIdentity, FetchResult, RequestCount
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.parse.people import HIDDEN_HANDLE

PEBBLE = "https://github.com/sample-org/pebble-pay"
EEL = "https://github.com/sample-org/eel-ledger"
COLLECTOR = "TestTool-research/0.1.0"


def answer(**changes: object) -> dict:
    """An INVENTED answer of "get a repository", with the parts about the account."""
    owner = {
        "login": "sample-org",
        "name": "Quill Invented",
        "email": "quill@example.test",
        "avatar_url": "https://avatars.githubusercontent.com/u/1234567?v=4",
        "type": "User",
    }
    body = {
        "id": 1296269,
        "name": "pebble-pay",
        "full_name": "sample-org/pebble-pay",
        "owner": owner,
        "html_url": "https://github.com/Sample-Org/pebble-pay",
        "description": "Pay a vendor with a coin. Made by @quill_invented.",
        "fork": True,
        "parent": {"full_name": "other-org/pebble", "owner": owner},
        "archived": False,
        "disabled": False,
        "created_at": "2026-03-06T17:00:00Z",
        "updated_at": "2026-03-09T10:00:00Z",
        "pushed_at": "2026-03-08T21:30:00Z",
        "size": 1840,
        "language": "TypeScript",
        "default_branch": "main",
        "visibility": "public",
        "topics": ["hedera", "payments"],
        "license": {"key": "mit", "name": "MIT License", "spdx_id": "MIT"},
        "stargazers_count": 12,
    }
    body.update(changes)
    return body


def fetched(status: int, body: bytes, repository: str = PEBBLE) -> FetchResult:
    url = facts_address(repository)
    return FetchResult(url, url, status, body, "application/json", "2026-10-12T02:00:00Z")


def save(store: RawStore, status: int, body: bytes, repository: str) -> None:
    fetch = fetched(status, body, repository)
    kept, facts, taken_out = kept_of(fetch)
    store.save(
        fetch, kept, received=body, collector=COLLECTOR, team_cut=taken_out, answer=facts,
        suffix=SUFFIX,
    )  # fmt: skip


# --------------------------------------------------------------------- what is kept


def test_only_the_fixed_fields_are_kept_and_the_account_is_dropped() -> None:
    body, _, taken_out = kept_of(fetched(200, json.dumps(answer()).encode()))
    kept = json.loads(body)
    assert sorted(kept) == sorted(
        [
            "html_url", "description", "fork", "archived", "disabled", "created_at",
            "updated_at", "pushed_at", "size", "language", "default_branch", "visibility",
            "topics", "license",
        ]
    )  # fmt: skip
    assert kept["license"] == "MIT"
    assert kept["description"] == f"Pay a vendor with a coin. Made by {HIDDEN_HANDLE}."
    text = body.decode()
    for words in ("Quill", "quill", "avatars.githubusercontent", "other-org", "stargazers"):
        assert words not in text
    assert taken_out == {"fields_dropped": 6, "owner_dropped": True, "words_hidden": 1}


def test_an_answer_with_no_repository_is_kept_as_it_came() -> None:
    gone = json.dumps({"message": "Not Found", "status": "404"}).encode()
    body, facts, taken_out = kept_of(fetched(404, gone))
    assert (body, facts, taken_out) == (gone, {"message": "Not Found"}, None)


def test_an_answer_that_is_not_json_keeps_nothing() -> None:
    body, facts, _ = kept_of(fetched(200, b"<html>not json</html>"))
    assert body == b"{}" and facts["kept"] == "nothing"


# --------------------------------------------------------------------- reading what was saved


def test_each_kind_of_saved_answer_is_read_back(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    save(store, 200, json.dumps(answer()).encode(), PEBBLE)
    save(store, 404, json.dumps({"message": "Not Found"}).encode(), EEL)
    other = "https://github.com/sample-org/fern-feed"
    save(store, 451, json.dumps({"message": "Repository access blocked"}).encode(), other)

    facts = saved_facts(store, PEBBLE)
    assert facts is not None and facts.status == FOUND
    assert facts.created_at == datetime(2026, 3, 6, 17, tzinfo=UTC)
    assert facts.pushed_at == datetime(2026, 3, 8, 21, 30, tzinfo=UTC)
    assert (facts.fork, facts.archived, facts.language) == (True, False, "TypeScript")
    assert facts.current_url == "https://github.com/sample-org/pebble-pay"
    assert saved_facts(store, EEL).status == GONE  # type: ignore[union-attr]
    assert saved_facts(store, other).status == BLOCKED  # type: ignore[union-attr]
    assert saved_facts(store, "https://github.com/sample-org/never-asked") is None


def test_the_facts_and_the_readme_of_a_repository_live_side_by_side(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    save(store, 200, json.dumps(answer()).encode(), PEBBLE)
    assert store.saved(".txt") == []  # the README files are .txt, the facts .json
    assert len(store.saved(SUFFIX)) == 1


# --------------------------------------------------------------------- a run


def test_a_run_asks_once_for_the_facts_of_each_repository(tmp_path: Path) -> None:
    pages = {
        facts_address(PEBBLE): Reply(200, json.dumps(answer()).encode(),
                                     {"x-ratelimit-remaining": "4000"}),
        facts_address(EEL): Reply(404, b'{"message": "Not Found"}',
                                  {"x-ratelimit-remaining": "4000"}),
    }  # fmt: skip
    site = FakeSite(pages)
    fake_time = FakeTime()
    client = GitHubClient(
        token=SecretStr("github_pat_INVENTED"),
        site="api.github.com",
        identity=CollectorIdentity(name="TestTool-research", contact="owner@example.test"),
        allow=allowed,
        is_enabled=lambda: True,
        session=session_for(site),
        count=RequestCount(tmp_path / "count.json", "api.github.com", limit=50),
        pause_seconds=1.0,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
    )
    store = RawStore(tmp_path / "raw")
    first = fetch_facts(client, store, [PEBBLE, EEL], collector=COLLECTOR)
    assert first.by_status == {FOUND: 1, GONE: 1, BLOCKED: 0}
    again = fetch_facts(client, store, [PEBBLE, EEL], collector=COLLECTOR)
    assert (again.asked, again.already_saved) == (0, 2)
    assert len(site.seen) == 2
