"""The code of a repository is read once from its archive, and only what was found is kept.
Every repository, answer and archive here is invented."""

from __future__ import annotations

import hashlib
import io
import json
import random
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import SecretStr

from fakes import FakeSite, FakeTime, Reply, archive, session_for
from hackathon_memory.collect import github_code
from hackathon_memory.collect.github import GitHubClient, allowed, archive_address
from hackathon_memory.collect.github_code import (
    BLOCKED,
    BROKE_OFF_NOW,
    GITHUB_AWAY,
    GONE,
    PARTIAL,
    READ,
    SUFFIX,
    again_store,
    fetch_code,
    fetch_code_again,
    read_code_now,
    saved_code,
)
from hackathon_memory.collect.polite import CollectorIdentity, RequestCount
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.parse import hedera_code

PEBBLE = "https://github.com/sample-org/pebble-pay"
EEL = "https://github.com/sample-org/eel-ledger"
FERN = "https://github.com/sample-org/fern-feed"
COLLECTOR = "TestTool-research/0.1.0"
TOKEN = "github_pat_INVENTED"
API = {"x-ratelimit-remaining": "4000"}
FILES = {
    "package.json": json.dumps({"dependencies": {"@hashgraph/sdk": "^2"},
                                "author": "Quill Invented <quill@example.test>"}).encode(),
    "src/topic.ts": b'import { TopicCreateTransaction } from "@hashgraph/sdk";\n'
                    b"await new TopicCreateTransaction().execute(client);\n",
    "config/keys.ts": b'import "../src/topic";\nexport const KEY = "302e-INVENTED-KEY";\n',
}  # fmt: skip


def download(repository: str) -> str:
    """Where the invented API sends the archive: GitHub's archive host."""
    owner_and_name = repository.removeprefix("https://github.com/")
    return f"https://codeload.github.com/{owner_and_name}/legacy.tar.gz/refs/heads/main"


def sent_to(repository: str, location: str | None = None) -> Reply:
    """The API's answer: the archive is at another address."""
    return Reply(302, b"", {**API, "Location": location or download(repository)})


class BreaksOff(io.RawIOBase):
    """A download that stops after some bytes, as a network that goes away."""

    def __init__(self, body: bytes, after: int) -> None:
        self._data = io.BytesIO(body[:after])

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        data = self._data.read(size)
        if not data:
            raise ConnectionResetError("the invented network went away")
        return data


def client_for(
    site: FakeSite,
    tmp_path: Path,
    fake_time: FakeTime | None = None,
    is_enabled: Callable[[], bool] = lambda: True,
) -> GitHubClient:
    fake_time = fake_time or FakeTime()
    return GitHubClient(
        token=SecretStr(TOKEN),
        site="api.github.com",
        identity=CollectorIdentity(name="TestTool-research", contact="owner@example.test"),
        allow=allowed,
        is_enabled=is_enabled,
        session=session_for(site),
        count=RequestCount(tmp_path / "count.json", "api.github.com", limit=50),
        pause_seconds=1.0,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
    )


# --------------------------------------------------------------------- a run of the step


def test_a_run_reads_each_archive_once_and_keeps_only_what_it_found(tmp_path: Path) -> None:
    body = archive(FILES)
    site = FakeSite({
        archive_address(PEBBLE): sent_to(PEBBLE),
        download(PEBBLE): Reply(200, body, {"Content-Type": "application/x-gzip"}),
        archive_address(EEL): Reply(404, b'{"message": "Not Found"}', API),
        archive_address(FERN): Reply(451, b'{"message": "Repository access blocked"}', API),
    })  # fmt: skip
    fake_time = FakeTime()
    client = client_for(site, tmp_path, fake_time)
    store = RawStore(tmp_path / "raw")

    first = fetch_code(client, store, [PEBBLE, EEL, FERN], collector=COLLECTOR)
    assert first.by_status == {READ: 1, PARTIAL: 0, GONE: 1, BLOCKED: 1}
    assert site.urls == [archive_address(PEBBLE), download(PEBBLE), archive_address(EEL),
                         archive_address(FERN)]  # fmt: skip
    asked_api, downloaded = site.seen[0], site.seen[1]
    assert asked_api.headers["Authorization"] == f"Bearer {TOKEN}"
    assert "Authorization" not in downloaded.headers  # the token goes to the API only
    assert downloaded.headers["From"] == "owner@example.test"
    assert "owner@example.test" in downloaded.headers["User-Agent"]
    assert fake_time.sleeps[0] == 1.0  # the pause between the two requests of one repository
    assert client.count is not None and client.count.sent() == 4

    read = saved_code(store, PEBBLE)
    assert read is not None and read.status == READ and read.saved and read.scan is not None
    assert read.scan.packages == {"@hashgraph/sdk": ["package.json"]}
    assert sorted(read.scan.features) == ["Consensus Service (topics)"]
    saved = store.load(archive_address(PEBBLE), SUFFIX)
    assert saved is not None
    assert saved.meta["received_sha256"] == hashlib.sha256(body).hexdigest()
    # The time of the two requests and of the reading, pauses included: on the fake clock,
    # the pause of one second between the two requests.
    assert saved.meta["answer"] == {"archive_bytes": len(body), "seconds": 1.0}
    kept = saved.read().decode()
    for words in ("Quill", "quill@", "INVENTED-KEY", "execute(client)"):
        assert words not in kept  # no text of a file is kept
    assert saved_code(store, EEL).status == GONE  # type: ignore[union-attr]
    assert saved_code(store, FERN).status == BLOCKED  # type: ignore[union-attr]
    assert saved_code(store, "https://github.com/sample-org/never-read") is None

    again = fetch_code(client, store, [PEBBLE, EEL, FERN], collector=COLLECTOR)
    assert (again.asked, again.already_saved) == (0, 3)
    assert len(site.seen) == 4


@pytest.mark.parametrize(
    "location",
    ["https://archive.example.test/pebble-pay.tar.gz",
     "http://codeload.github.com/sample-org/pebble-pay/legacy.tar.gz/refs/heads/main"],
)  # fmt: skip
def test_an_archive_sent_anywhere_else_is_not_downloaded_and_the_run_goes_on(
    tmp_path: Path, location: str
) -> None:
    site = FakeSite({
        archive_address(PEBBLE): sent_to(PEBBLE, location),
        archive_address(EEL): Reply(404, b'{"message": "Not Found"}', API),
    })  # fmt: skip
    store = RawStore(tmp_path / "raw")
    run = fetch_code(client_for(site, tmp_path), store, [PEBBLE, EEL], collector=COLLECTOR)
    assert (run.stopped, run.failed, run.by_status[GONE]) == (None, 1, 1)
    assert site.urls == [archive_address(PEBBLE), archive_address(EEL)]
    assert saved_code(store, PEBBLE) is None  # a later run asks again


def test_a_moved_repository_is_followed_inside_the_api_to_its_archive(tmp_path: Path) -> None:
    moved = "https://api.github.com/repositories/4242/tarball"
    site = FakeSite({
        archive_address(PEBBLE): Reply(301, b"", {**API, "Location": moved}),
        moved: sent_to(PEBBLE),
        download(PEBBLE): Reply(200, archive(FILES)),
    })  # fmt: skip
    store = RawStore(tmp_path / "raw")
    run = fetch_code(client_for(site, tmp_path), store, [PEBBLE], collector=COLLECTOR)
    assert run.by_status[READ] == 1
    assert site.urls == [archive_address(PEBBLE), moved, download(PEBBLE)]
    assert all("Authorization" in one.headers for one in site.seen[:2])  # inside the API
    assert "Authorization" not in site.seen[2].headers
    assert saved_code(store, PEBBLE).status == READ  # type: ignore[union-attr]


def test_a_download_that_breaks_off_is_not_kept_and_a_later_run_reads_it(tmp_path: Path) -> None:
    body = archive(FILES)
    site = FakeSite({
        archive_address(PEBBLE): sent_to(PEBBLE),
        download(PEBBLE): [Reply(200, stream=BreaksOff(body, len(body) // 2)), Reply(200, body)],
    })  # fmt: skip
    client = client_for(site, tmp_path)
    store = RawStore(tmp_path / "raw")
    first = fetch_code(client, store, [PEBBLE], collector=COLLECTOR)
    assert (first.asked, first.failed, first.by_status[READ]) == (1, 1, 0)
    assert saved_code(store, PEBBLE) is None
    second = fetch_code(client, store, [PEBBLE], collector=COLLECTOR)
    assert second.by_status[READ] == 1
    assert saved_code(store, PEBBLE).status == READ  # type: ignore[union-attr]


def test_downloads_that_keep_breaking_off_stop_the_run(tmp_path: Path) -> None:
    body = archive(FILES)
    repositories = [f"https://github.com/sample-org/repo-{n}" for n in range(7)]
    pages: dict[str, Reply | list[Reply | Exception]] = {}
    for repository in repositories:
        pages[archive_address(repository)] = sent_to(repository)
        pages[download(repository)] = Reply(200, stream=BreaksOff(body, 40))
    site = FakeSite(pages)
    run = fetch_code(client_for(site, tmp_path), RawStore(tmp_path / "raw"), repositories,
                     collector=COLLECTOR)  # fmt: skip
    assert run.stopped is not None and "5 errors in a row" in run.stopped
    assert (run.asked, run.failed, run.left_for_later) == (4, 4, 3)


@pytest.mark.parametrize(("status", "words"), [(429, "too many requests"), (403, "says no")])
def test_a_download_that_says_no_or_too_many_stops_the_run(
    tmp_path: Path, status: int, words: str
) -> None:
    site = FakeSite({archive_address(PEBBLE): sent_to(PEBBLE), download(PEBBLE): Reply(status)})
    run = fetch_code(client_for(site, tmp_path), RawStore(tmp_path / "raw"), [PEBBLE, EEL],
                     collector=COLLECTOR)  # fmt: skip
    assert run.stopped is not None and words in run.stopped
    assert site.urls == [archive_address(PEBBLE), download(PEBBLE)]  # EEL is not asked


# --------------------------------------------------------------------- the check of a submission


def test_a_check_keeps_a_whole_reading_and_shows_one_that_a_limit_cut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    noise = random.Random(7)  # noqa: S311 - random bytes do not compress: a large archive
    large = archive({f"src/f{n}.ts": noise.randbytes(50_000) for n in range(20)})
    site = FakeSite({
        archive_address(PEBBLE): sent_to(PEBBLE), download(PEBBLE): Reply(200, archive(FILES)),
        archive_address(EEL): sent_to(EEL), download(EEL): Reply(200, large),
    })  # fmt: skip
    client = client_for(site, tmp_path)
    store = RawStore(tmp_path / "raw")
    monkeypatch.setattr(github_code, "LIVE_MAX_BYTES", 100_000)

    read, problem = read_code_now(client, store, PEBBLE, collector=COLLECTOR)
    assert problem is None and read is not None and read.status == READ and read.saved
    assert read_code_now(client, store, PEBBLE, collector=COLLECTOR) == (read, None)
    assert len(site.seen) == 2  # a saved reading is never asked for again

    cut, problem = read_code_now(client, store, EEL, collector=COLLECTOR)
    assert problem is None and cut is not None and cut.status == PARTIAL and not cut.saved
    assert cut.scan is not None and cut.scan.partial == github_code.LIMIT_BYTES
    assert saved_code(store, EEL) is None  # the step reads it whole later
    assert fetch_code(client, store, [EEL], collector=COLLECTOR).by_status[READ] == 1

    never = "https://github.com/sample-org/never-read"
    assert read_code_now(None, store, never, collector=COLLECTOR) == (None, None)


def test_a_check_says_in_plain_words_why_the_code_was_not_read(tmp_path: Path) -> None:
    body = archive(FILES)
    site = FakeSite({
        archive_address(PEBBLE): Reply(502, b"", API),
        archive_address(EEL): sent_to(EEL),
        download(EEL): Reply(200, stream=BreaksOff(body, 40)),
    })  # fmt: skip
    store = RawStore(tmp_path / "raw")
    client = client_for(site, tmp_path)
    assert read_code_now(client, store, PEBBLE, collector=COLLECTOR) == (None, GITHUB_AWAY)
    assert read_code_now(client, store, EEL, collector=COLLECTOR) == (None, BROKE_OFF_NOW)
    off = client_for(site, tmp_path / "off", is_enabled=lambda: False)
    read, problem = read_code_now(off, store, FERN, collector=COLLECTOR)
    assert read is None and problem is not None and "The switch for" in problem
    assert saved_code(store, PEBBLE) is None and saved_code(store, EEL) is None


# --------------------------------------------------------------------- a newer reader


def test_a_reading_of_an_older_reader_is_made_again_once_into_its_own_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = archive({**FILES, "config/ids.ts": b'export const TOPIC_ID = "0.0.4870201";\n'})
    site = FakeSite({
        archive_address(PEBBLE): sent_to(PEBBLE), download(PEBBLE): Reply(200, body),
        archive_address(EEL): Reply(404, b'{"message": "Not Found"}', API),
    })  # fmt: skip
    client = client_for(site, tmp_path)
    store = RawStore(tmp_path / "raw")
    monkeypatch.setattr(hedera_code, "FORMAT", 2)  # the reader of 21 October 2026
    fetch_code(client, store, [PEBBLE, EEL], collector=COLLECTOR)
    monkeypatch.undo()
    first = saved_code(store, PEBBLE)
    assert first is not None and first.scan is not None and first.scan.format == 2
    first_meta = store.load(archive_address(PEBBLE), SUFFIX).meta  # type: ignore[union-attr]

    again = fetch_code_again(client, store, [PEBBLE, EEL], collector=COLLECTOR)
    assert again.asked == 1  # the repository that is gone has no code to read again
    newest = saved_code(store, PEBBLE)
    assert newest is not None and newest.scan is not None
    assert newest.scan.format == hedera_code.FORMAT
    assert ("0.0.4870201", None) in newest.scan.ids
    assert store.load(archive_address(PEBBLE), SUFFIX).meta == first_meta  # never edited
    assert again_store(store).load(archive_address(PEBBLE), SUFFIX) is not None
    assert fetch_code_again(client, store, [PEBBLE, EEL], collector=COLLECTOR).asked == 0


def test_a_check_reads_again_the_code_that_an_older_reader_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = FakeSite({archive_address(PEBBLE): sent_to(PEBBLE),
                     download(PEBBLE): Reply(200, archive(FILES))})  # fmt: skip
    store = RawStore(tmp_path / "raw")
    monkeypatch.setattr(hedera_code, "FORMAT", 2)
    fetch_code(client_for(site, tmp_path), store, [PEBBLE], collector=COLLECTOR)
    monkeypatch.undo()
    away = FakeSite({archive_address(PEBBLE): Reply(502, b"", API)})
    read, problem = read_code_now(client_for(away, tmp_path / "away"), store, PEBBLE,
                                  collector=COLLECTOR)  # fmt: skip
    assert problem is None and read is not None and read.scan.format == 2  # type: ignore[union-attr]
    read, problem = read_code_now(client_for(site, tmp_path / "now"), store, PEBBLE,
                                  collector=COLLECTOR)  # fmt: skip
    assert problem is None and read is not None
    assert read.scan.format == hedera_code.FORMAT  # type: ignore[union-attr]
    assert saved_code(store, PEBBLE) == read
