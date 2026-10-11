"""The README of a repository is asked for once and saved without people. All of it is invented."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from fakes import FakeSite, FakeTime, Reply, session_for
from hackathon_memory.collect.github import GitHubClient, allowed, readme_address
from hackathon_memory.collect.github_readmes import (
    BLOCKED,
    FOUND,
    NONE,
    NOT_TEXT,
    SUFFIX,
    fetch_readmes,
    kept_of,
    read_readme,
    saved_readme,
)
from hackathon_memory.collect.polite import CollectorIdentity, FetchResult, RequestCount
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.parse.people import HIDDEN_HANDLE

PEBBLE = "https://github.com/sample-org/pebble-pay"
EEL = "https://github.com/sample-org/eel-ledger"
FERN = "https://github.com/sample-org/fern-feed"
README_TEXT = (
    "# Pebble Pay\n\nPay a vendor. Our topic on testnet: 0.0.3456789.\n\n"
    "## Team\n\n- Quill Invented, [profile](https://x.com/quill_invented)\n\n"
    "## Setup\n\nAsk @reed_invented.\n"
)
COLLECTOR = "TestTool-research/0.1.0"


def readme_answer(text: str = README_TEXT, **changes: object) -> bytes:
    raw = text.encode("utf-8")
    content = base64.encodebytes(raw).decode("ascii")  # GitHub breaks the lines, as here
    answer = {
        "type": "file",
        "encoding": "base64",
        "size": len(raw),
        "name": "README.md",
        "path": "README.md",
        "content": content,
        "sha": "3d21ec53a331a6f037a91c368710b99387d012c1",
        "url": "https://api.github.com/repos/sample-org/pebble-pay/contents/README.md",
        "html_url": "https://github.com/sample-org/pebble-pay/blob/main/README.md",
        "git_url": "https://api.github.com/repos/sample-org/pebble-pay/git/blobs/3d21ec5",
        "download_url": "https://raw.githubusercontent.com/sample-org/pebble-pay/main/README.md",
        "_links": {},
    }
    answer.update(changes)
    return json.dumps(answer).encode()


def fetched(status: int, body: bytes, url: str = readme_address(PEBBLE)) -> FetchResult:
    return FetchResult(url, url, status, body, "application/json", "2026-10-11T18:00:00Z")


NOT_FOUND = json.dumps({"message": "Not Found", "status": "404"}).encode()


# --------------------------------------------------------------------- what is kept of an answer


def test_a_readme_is_kept_as_text_without_its_team_part_and_its_handles() -> None:
    body, facts, taken_out = kept_of(fetched(200, readme_answer()))
    text = body.decode("utf-8")
    assert "Quill" not in text and "quill" not in text and "reed" not in text
    assert "## Team" not in text
    assert f"Ask {HIDDEN_HANDLE}." in text
    assert "Our topic on testnet: 0.0.3456789." in text
    assert facts == {
        "name": "README.md",
        "path": "README.md",
        "size": len(README_TEXT.encode()),
        "sha": "3d21ec53a331a6f037a91c368710b99387d012c1",
        "html_url": "https://github.com/sample-org/pebble-pay/blob/main/README.md",
        "encoding": "base64",
    }
    assert taken_out == {
        "words_hidden": 1,
        "team_parts_cut": 1,
        "team_lines_cut": 4,
        "ids_in_the_cut": 0,
    }


def test_an_answer_with_no_readme_is_kept_as_it_came() -> None:
    body, facts, taken_out = kept_of(fetched(404, NOT_FOUND))
    assert body == NOT_FOUND
    assert facts == {"message": "Not Found"}
    assert taken_out is None


@pytest.mark.parametrize(
    ("answer", "why"),
    [
        (readme_answer(content=base64.b64encode(b"\xff\xfe\x00bad").decode()), "UTF-8"),
        (readme_answer(encoding="none", content=""), "base64"),
        (b"<html>not json</html>", "JSON"),
        (b"[1, 2]", "object"),
    ],
)
def test_an_answer_that_is_not_text_is_kept_as_an_empty_page(answer: bytes, why: str) -> None:
    body, facts, taken_out = kept_of(fetched(200, answer))
    assert body == b""
    assert facts["kept"] == NOT_TEXT and why in facts["why"]
    assert taken_out is None


# --------------------------------------------------------------------- reading what was saved


def save(store: RawStore, status: int, body: bytes, url: str) -> None:
    fetch = fetched(status, body, url)
    kept, facts, taken_out = kept_of(fetch)
    store.save(
        fetch, kept, received=body, collector=COLLECTOR, team_cut=taken_out, answer=facts,
        suffix=SUFFIX,
    )  # fmt: skip


def test_each_kind_of_saved_answer_is_read_back(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    save(store, 200, readme_answer(), readme_address(PEBBLE))
    save(store, 404, NOT_FOUND, readme_address(EEL))
    blocked = json.dumps({"message": "Repository access blocked"}).encode()
    save(store, 451, blocked, readme_address(FERN))
    other = "https://github.com/sample-org/odd-one"
    save(store, 200, readme_answer(encoding="none", content=""), readme_address(other))

    found = saved_readme(store, PEBBLE)
    assert found is not None and found.status == FOUND
    assert found.name == "README.md"
    assert "0.0.3456789" in found.text and "Quill" not in found.text
    assert found.taken_out["team_parts_cut"] == 1
    assert [saved_readme(store, repo).status for repo in (EEL, FERN, other)] == [  # type: ignore[union-attr]
        NONE,
        BLOCKED,
        NOT_TEXT,
    ]
    assert saved_readme(store, "https://github.com/sample-org/never-asked") is None


def test_the_fingerprint_of_what_github_sent_is_kept(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    body = readme_answer()
    save(store, 200, body, readme_address(PEBBLE))
    saved = store.load(readme_address(PEBBLE), SUFFIX)
    assert saved is not None
    assert saved.meta["received_sha256"] == hashlib.sha256(body).hexdigest()
    assert saved.meta["sha256"] == hashlib.sha256(saved.read()).hexdigest()
    assert read_readme(saved).sha256 == saved.meta["sha256"]


def test_no_name_of_a_person_is_in_any_saved_file(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    save(store, 200, readme_answer(), readme_address(PEBBLE))
    for path in tmp_path.iterdir():
        content = path.read_text(encoding="utf-8")
        assert "quill" not in content.lower() and "reed" not in content.lower(), path.name


# --------------------------------------------------------------------- a run


def client_for(
    pages: dict, tmp_path: Path, *, enabled=lambda: True
) -> tuple[GitHubClient, FakeSite]:
    site = FakeSite(pages)
    fake_time = FakeTime()
    client = GitHubClient(
        token=SecretStr("github_pat_INVENTED"),
        site="api.github.com",
        identity=CollectorIdentity(name="TestTool-research", contact="owner@example.test"),
        allow=allowed,
        is_enabled=enabled,
        session=session_for(site),
        count=RequestCount(tmp_path / "count.json", "api.github.com", limit=50),
        pause_seconds=1.0,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        now=lambda: datetime(2026, 10, 11, 18, tzinfo=UTC),
    )
    return client, site


def json_reply(status: int, body: bytes) -> Reply:
    return Reply(
        status, body, {"Content-Type": "application/json", "x-ratelimit-remaining": "4000"}
    )


def test_a_run_asks_once_for_each_readme_that_is_not_saved(tmp_path: Path) -> None:
    pages = {
        readme_address(PEBBLE): json_reply(200, readme_answer()),
        readme_address(EEL): json_reply(404, NOT_FOUND),
        readme_address(FERN): json_reply(200, readme_answer("# Fern\n\nNo id here.\n")),
    }
    client, site = client_for(pages, tmp_path)
    store = RawStore(tmp_path / "raw")
    first = fetch_readmes(client, store, [PEBBLE, EEL, FERN], collector=COLLECTOR, limit=2)
    assert (first.asked, first.already_saved, first.left_for_later) == (2, 0, 1)
    assert first.by_status == {FOUND: 1, NONE: 1, BLOCKED: 0, NOT_TEXT: 0}

    second = fetch_readmes(client, store, [PEBBLE, EEL, FERN], collector=COLLECTOR)
    assert (second.asked, second.already_saved, second.left_for_later) == (1, 2, 0)
    assert len(site.seen) == 3  # never twice


def test_a_failed_readme_is_not_saved_and_is_asked_again_later(tmp_path: Path) -> None:
    pages = {
        readme_address(PEBBLE): [json_reply(502, b"{}"), json_reply(200, readme_answer())],
        readme_address(EEL): json_reply(404, NOT_FOUND),
    }
    client, _ = client_for(pages, tmp_path)
    store = RawStore(tmp_path / "raw")
    first = fetch_readmes(client, store, [PEBBLE, EEL], collector=COLLECTOR)
    assert (first.asked, first.failed) == (2, 1)
    assert saved_readme(store, PEBBLE) is None
    second = fetch_readmes(client, store, [PEBBLE, EEL], collector=COLLECTOR)
    assert (second.asked, second.failed, second.by_status[FOUND]) == (1, 0, 1)  # type: ignore[index]


def test_a_stop_ends_the_run_and_what_was_saved_stays(tmp_path: Path) -> None:
    pages = {
        readme_address(PEBBLE): json_reply(200, readme_answer()),
        readme_address(EEL): json_reply(401, json.dumps({"message": "Bad credentials"}).encode()),
    }
    client, site = client_for(pages, tmp_path)
    store = RawStore(tmp_path / "raw")
    run = fetch_readmes(client, store, [PEBBLE, EEL, FERN], collector=COLLECTOR)
    assert run.stopped is not None and "401" in run.stopped
    assert (run.asked, run.left_for_later) == (1, 2)
    assert saved_readme(store, PEBBLE) is not None
    assert len(site.seen) == 2
