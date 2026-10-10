"""The proof of the lists: it reads what a walk and a run left on disk. Everything is invented."""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fakes import (
    HEDERA_ID,
    LIST,
    OTHER_ID,
    FakeSite,
    FakeTime,
    Reply,
    list_reply,
    listed,
    sample,
    session_for,
)
from hackathon_memory.collect.ethglobal import ROBOTS_URL, build_collector
from hackathon_memory.collect.ethglobal_find import build_walker
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore, fingerprint
from hackathon_memory.settings import Settings
from proofs import lists
from proofs import result as result_module

PEBBLE = "https://ethglobal.com/showcase/pebble-pay-x1y2z"
QUARTZ = "https://ethglobal.com/showcase/quartz-notes-q3w4e"
FIG = "https://ethglobal.com/showcase/fig-registry-u7y6t"
PAGE_2 = LIST + "&page=2"
DUNE = listed("dune-notes", "p0o9i")  # no prize, the row that the two pages share


def winner(name: str) -> Reply:
    body = sample("project_winner.html").replace(b"Pebble Pay", name.encode())
    return Reply(200, body, {"Content-Type": "text/html; charset=utf-8"})


def the_site() -> dict[str, Reply]:
    first = [
        listed("pebble-pay", "x1y2z", HEDERA_ID),
        listed("cedar-lens", "k9l8m", OTHER_ID),
        DUNE,
    ]
    second = [
        DUNE,
        listed("quartz-notes", "q3w4e", OTHER_ID, HEDERA_ID, event="ETHGlobal Other Event"),
        listed("fig-registry", "u7y6t", HEDERA_ID),
    ]
    return {
        # Like the real site: there is no robots.txt.
        LIST: list_reply(1, first, has_next=True),
        PAGE_2: list_reply(2, second, has_next=False),
        PEBBLE: winner("Pebble Pay"),
        QUARTZ: winner("Quartz Notes"),
        FIG: winner("Fig Registry"),
    }


def ticking(seconds: int) -> Callable[[], datetime]:
    """A clock for the time of each answer: it moves on by `seconds` every time it is read."""
    start = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
    ticks = itertools.count()
    return lambda: start + timedelta(seconds=seconds * next(ticks))


@pytest.fixture
def results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "proofs" / "results"
    monkeypatch.setattr(result_module, "RESULTS_DIR", folder)
    return folder


def settings_for(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        data_dir=str(tmp_path / "data"),
        collector_name="TestTool-research",
        collector_contact_email="maintainer@example.test",
        collect_ethglobal=True,
    )


def collected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seconds_apart: int = 3, walk: bool = True
) -> Settings:
    """A data folder as a walk and a run leave it, made on the invented site."""
    monkeypatch.delenv("COLLECT_ETHGLOBAL", raising=False)
    settings = settings_for(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("COLLECT_ETHGLOBAL=on\n", encoding="utf-8")
    folder = tmp_path / "data" / "by-hand" / "ethglobal.com"
    folder.mkdir(parents=True)
    (folder / "project-pages.txt").write_text(PEBBLE + "\n", encoding="utf-8")
    fake_time = FakeTime()
    options = {
        "env_file": env_file,
        "session": session_for(FakeSite(the_site())),
        "clock": fake_time.clock,
        "sleep": fake_time.sleep,
        "now": ticking(seconds_apart),
    }
    if walk:
        walker = build_walker(settings, **options)
        walker.log = lambda message: None
        assert walker.run().complete
    collector = build_collector(settings, **options)
    collector.log = lambda message: None
    assert collector.run().stopped is None
    return settings


def the_result(results_dir: Path) -> dict:
    files = sorted(results_dir.glob("*-lists.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


def failed(results_dir: Path) -> list[str]:
    return [check["name"] for check in the_result(results_dir)["checks"] if not check["passed"]]


def test_the_proof_passes_on_what_a_walk_and_a_run_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_dir: Path
) -> None:
    settings = collected(tmp_path, monkeypatch)
    assert lists.run(settings) == 0
    result = the_result(results_dir)
    assert result["passed"] is True
    numbers = result["measurements"]
    assert numbers["projects_in_the_list"] == 5  # the shared row is counted once
    assert numbers["projects_with_a_prize_of_some_sponsor"] == 4
    assert numbers["projects_with_a_hedera_prize"] == 3
    assert (numbers["pages_planned"], numbers["pages_saved"]) == (3, 3)
    assert numbers["requests_sent_over_all_commands"] == 7  # robots.txt twice, 2 + 3 pages
    assert numbers["smallest_gap_between_two_saved_pages_s"] == 3
    assert numbers["by_event"]["ETHGlobal Other Event"] == {
        "in_the_list": 1,
        "with_a_prize_of_some_sponsor": 1,
        "with_a_hedera_prize": 1,
        "pages_saved": 1,
    }


def test_the_proof_sends_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_dir: Path
) -> None:
    settings = collected(tmp_path, monkeypatch)
    count = tmp_path / "data" / "requests" / "ethglobal.com.json"
    before = count.read_text(encoding="utf-8")
    monkeypatch.setattr(
        "requests.Session.get", lambda *a, **k: pytest.fail("the proof sent a request")
    )
    assert lists.run(settings) == 0
    assert count.read_text(encoding="utf-8") == before


def test_the_result_file_holds_no_project_and_no_page_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_dir: Path
) -> None:
    lists.run(collected(tmp_path, monkeypatch))
    text = next(results_dir.glob("*-lists.json")).read_text(encoding="utf-8").lower()
    for kept_out in (
        "pebble",
        "quartz",
        "fig-registry",
        "showcase/",
        "street vendor",
        "maintainer@",
    ):
        assert kept_out not in text


def test_a_page_that_was_edited_fails_the_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_dir: Path
) -> None:
    settings = collected(tmp_path, monkeypatch)
    page = RawStore(tmp_path / "data" / "raw" / "ethglobal.com").load(PEBBLE)
    assert page is not None
    page.body_path.write_bytes(page.read() + b"<!-- one more line -->")
    assert lists.run(settings) == 1
    assert failed(results_dir) == ["no saved page was edited after it was saved (fingerprints)"]


def test_a_winner_that_is_not_saved_fails_the_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_dir: Path
) -> None:
    settings = collected(tmp_path, monkeypatch)
    page = RawStore(tmp_path / "data" / "raw" / "ethglobal.com").load(FIG)
    assert page is not None
    page.body_path.unlink()
    page.meta_path.unlink()
    assert lists.run(settings) == 1
    assert failed(results_dir) == [
        "every page of the plan was read",
        "every winner of a Hedera prize that the walk found is saved",
    ]


def test_a_saved_page_that_nobody_planned_fails_the_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_dir: Path
) -> None:
    settings = collected(tmp_path, monkeypatch)
    body = sample("project_winner.html")
    extra = FetchResult(
        url="https://ethglobal.com/showcase/cedar-lens-k9l8m",
        final_url="https://ethglobal.com/showcase/cedar-lens-k9l8m",
        status=200,
        body=body,
        content_type="text/html",
        fetched_at="2026-10-10T10:00:00Z",
    )
    RawStore(tmp_path / "data" / "raw" / "ethglobal.com").save(
        extra, body, received=body, collector="TestTool-research/0"
    )
    assert lists.run(settings) == 1
    assert "no page outside the plan is saved" in failed(results_dir)


def test_a_saved_page_with_no_hedera_prize_or_with_a_person_fails_the_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_dir: Path
) -> None:
    settings = collected(tmp_path, monkeypatch)
    page = RawStore(tmp_path / "data" / "raw" / "ethglobal.com").load(QUARTZ)
    assert page is not None
    # A page with another sponsor's prize and with a link to a profile, saved by a broken tool.
    body = sample("project_profile_link.html").replace(b"Hedera -", b"Other Sponsor -")
    page.body_path.write_bytes(body)
    page.meta_path.write_text(
        json.dumps(page.meta | {"sha256": fingerprint(body)}), encoding="utf-8"
    )
    assert lists.run(settings) == 1
    assert failed(results_dir) == [
        'every saved page shows a Hedera prize in its "Winner of" block',
        "no saved page holds a personal tag, a profile link, an avatar or a data key for people",
    ]


def test_pages_fetched_too_fast_fail_the_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_dir: Path
) -> None:
    settings = collected(tmp_path, monkeypatch, seconds_apart=1)
    assert lists.run(settings) == 1
    assert failed(results_dir) == ["two saved pages were never fetched less than two seconds apart"]


def test_more_requests_than_the_limit_fail_the_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_dir: Path
) -> None:
    settings = collected(tmp_path, monkeypatch)
    count = tmp_path / "data" / "requests" / "ethglobal.com.json"
    count.write_text('{"site": "ethglobal.com", "sent": 301, "by_day": {}}', encoding="utf-8")
    assert lists.run(settings) == 1
    assert failed(results_dir) == [
        "the requests to the site, over all commands, stay inside the limit"
    ]


def test_without_a_walk_the_proof_fails_and_says_what_to_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_dir: Path
) -> None:
    settings = collected(tmp_path, monkeypatch, walk=False)  # a run on the hand-made list only
    assert lists.run(settings) == 1
    check = the_result(results_dir)["checks"][0]
    assert check["passed"] is False
    assert "--find" in check["detail"]


def test_the_site_has_no_robots_txt_in_this_proof_setup(tmp_path: Path) -> None:
    assert ROBOTS_URL not in the_site()  # the invented site answers 404 for it, as the real one
