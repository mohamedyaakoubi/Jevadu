"""The ETHGlobal collector, run against an invented site. Nothing here touches the internet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fakes import FakeSite, FakeTime, Reply, sample, session_for
from hackathon_memory.collect.ethglobal import (
    ETHGLOBAL_SHAPE,
    ROBOTS_URL,
    EthGlobalCollector,
    SiteShape,
    build_collector,
    extract_project_links,
    is_allowed_url,
    load_prize_pages,
    plan,
)
from hackathon_memory.collect.polite import CollectorIdentity, CollectorRefused, PoliteClient
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.collect.teamcut import CutPolicy, CutRule
from hackathon_memory.settings import Settings

PRIZE = "https://ethglobal.com/events/sample-event-2099/prizes/hedera"
ZED = "https://ethglobal.com/showcase/zed-widget-a1b2c"
MANGO = "https://ethglobal.com/showcase/mango-ledger-d4e5f"
NAMES = [b"Quillfeather", b"Ledgerwood", b"Orchardson", b"quillfeather", b"Samplewright"]

# The shape of the INVENTED pages. The real shape is not known yet.
TEST_SHAPE = SiteShape(
    project_links_selector="main a[href]",
    project_cut=CutPolicy(rules=(CutRule("#team"),), json_blocklist=frozenset({"members"})),
    prize_cut=CutPolicy(rules=(CutRule("#team", required=False),)),
    verified_on="invented test pages only",
)


def page(body: bytes) -> Reply:
    return Reply(200, body, {"Content-Type": "text/html; charset=utf-8"})


def pages(**changes: Reply) -> dict[str, Reply]:
    result = {
        ROBOTS_URL: Reply(200, sample("robots.txt"), {"Content-Type": "text/plain"}),
        PRIZE: page(sample("prize_page.html")),
        ZED: page(sample("project_zed_widget.html")),
        MANGO: page(sample("project_mango_ledger.html")),
    }
    for key, reply in changes.items():
        result[{"robots": ROBOTS_URL, "prize": PRIZE, "zed": ZED, "mango": MANGO}[key]] = reply
    return result


def make(tmp_path: Path, site_pages: dict[str, Reply], shape: SiteShape = TEST_SHAPE, **options):
    site = FakeSite(site_pages)
    fake_time = FakeTime()
    client = PoliteClient(
        site="ethglobal.com",
        identity=CollectorIdentity(name="TestTool-research", contact="owner@example.test"),
        allow=is_allowed_url,
        is_enabled=lambda: True,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        **options,
    )
    collector = EthGlobalCollector(
        client=client,
        store=RawStore(tmp_path / "raw"),
        prize_pages=[PRIZE],
        shape=shape,
        runs_dir=tmp_path / "runs",
        log=lambda message: None,
    )
    return collector, site, fake_time


# --------------------------------------------------------------------- only the pages we named


@pytest.mark.parametrize(
    "url",
    [
        ROBOTS_URL,
        PRIZE,
        PRIZE + "/",
        ZED,
        ZED + "/",
    ],
)
def test_addresses_we_named_are_allowed(url: str) -> None:
    assert is_allowed_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://ethglobal.com/showcase/zed-widget-a1b2c",  # not https
        "https://example.com/showcase/zed-widget-a1b2c",  # another site
        "https://ethglobal.com.evil.test/showcase/x",  # a look-alike
        "https://user@ethglobal.com/showcase/x",  # a login in the address
        "https://ethglobal.com:8443/showcase/x",  # another port
        "https://ethglobal.com/showcase",  # the list of the whole showcase
        "https://ethglobal.com/showcase/",
        "https://ethglobal.com/showcase/x?page=2",  # a query
        "https://ethglobal.com/showcase/x#team",  # a fragment
        "https://ethglobal.com/events/sample-event-2099/prizes/other",  # not the Hedera prize
        "https://ethglobal.com/events/sample-event-2099",
        "https://ethglobal.com/hackers/someone",  # a person
        "https://ethglobal.com/",
    ],
)
def test_other_addresses_are_never_allowed(url: str) -> None:
    assert not is_allowed_url(url)


def test_the_prize_list_must_exist_and_hold_prize_pages_only(tmp_path: Path) -> None:
    path = tmp_path / "prize-pages.txt"
    with pytest.raises(CollectorRefused, match="missing"):
        load_prize_pages(path)

    path.write_text("# only comments\n\n", encoding="utf-8")
    with pytest.raises(CollectorRefused, match="empty"):
        load_prize_pages(path)

    path.write_text(f"{PRIZE}\nhttps://ethglobal.com/showcase/zed-widget-a1b2c\n", encoding="utf-8")
    with pytest.raises(CollectorRefused, match="line 2"):
        load_prize_pages(path)


def test_the_prize_list_ignores_comments_and_repeats(tmp_path: Path) -> None:
    path = tmp_path / "prize-pages.txt"
    path.write_text(f"# checked by hand\n{PRIZE}  # one\n{PRIZE}/\n", encoding="utf-8")
    assert load_prize_pages(path) == [PRIZE]


def test_only_showcase_projects_are_taken_from_a_prize_page() -> None:
    links = extract_project_links(sample("prize_page.html"), PRIZE, "main a[href]")
    # The page also links to a sponsor, to another prize page, and to Zed Widget twice.
    assert links == [ZED, MANGO]


# --------------------------------------------------------------------- a full run


def test_a_full_run_saves_the_pages_without_the_team(tmp_path: Path) -> None:
    collector, site, fake_time = make(tmp_path, pages())
    summary = collector.run()

    assert site.urls == [ROBOTS_URL, PRIZE, ZED, MANGO]
    assert fake_time.sleeps == [2.0, 2.0, 2.0]
    assert summary.stopped is None
    assert summary.pages_saved == 3  # the prize page and two projects (robots.txt is kept too)
    assert summary.project_links_found == 2

    saved_files = [p for p in (tmp_path / "raw").iterdir() if p.is_file()]
    assert saved_files
    for path in saved_files:
        content = path.read_bytes()
        for name in NAMES:
            assert name not in content, f"{name!r} was saved in {path.name}"

    zed = collector.store.load(ZED)
    assert zed is not None
    assert b"Zed Widget" in zed.read()
    assert b"0.0.1234567" in zed.read()
    assert zed.meta["team_cut"]["elements_removed"] == 2
    assert zed.meta["status"] == 200


def test_the_run_leaves_a_record_without_page_text(tmp_path: Path) -> None:
    collector, _, _ = make(tmp_path, pages())
    collector.run()
    records = list((tmp_path / "runs").glob("*-ethglobal.json"))
    assert len(records) == 1
    text = records[0].read_text(encoding="utf-8")
    record = json.loads(text)
    assert record["requests_made"] == 4
    assert record["stopped"] is None
    assert record["project_links_found"] == 2
    assert "Widget" not in text  # no text of a page, only counts and addresses


def test_a_second_run_makes_no_request_at_all(tmp_path: Path) -> None:
    first, _, _ = make(tmp_path, pages())
    first.run()

    second, site, _ = make(tmp_path, pages())
    summary = second.run()
    assert site.seen == []
    assert summary.requests_made == 0
    assert summary.pages_already_saved == 2
    assert summary.pages_saved == 0


def test_a_second_run_fetches_only_what_is_missing(tmp_path: Path) -> None:
    first, _, _ = make(tmp_path, pages(mango=Reply(404, b"gone")))
    first.run()

    second, site, _ = make(tmp_path, pages())  # the page is back
    summary = second.run()
    assert site.urls == [MANGO]  # robots.txt, the prize page and Zed Widget are already saved
    assert summary.pages_saved == 1
    assert summary.pages_already_saved == 1


def test_the_limit_stops_the_run_and_the_record_says_so(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(), max_requests=3)
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, PRIZE, ZED]
    assert summary.stopped is not None
    assert "limit of 3 requests" in summary.stopped
    assert collector.store.has(ZED)
    assert not collector.store.has(MANGO)
    assert list((tmp_path / "runs").glob("*.json"))  # the record is written even when stopped


# --------------------------------------------------------------------- the site says stop


def test_robots_txt_is_read_first_and_obeyed(tmp_path: Path) -> None:
    robots = Reply(200, b"User-agent: *\nDisallow: /showcase/\n")
    collector, site, _ = make(tmp_path, pages(robots=robots))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, PRIZE]
    assert summary.stopped is not None
    assert "robots.txt" in summary.stopped


def test_a_crawl_delay_in_robots_txt_makes_the_pause_longer(tmp_path: Path) -> None:
    robots = Reply(200, b"User-agent: *\nCrawl-delay: 6\n")
    collector, _, fake_time = make(tmp_path, pages(robots=robots))
    collector.run()
    assert fake_time.sleeps == [6.0, 6.0, 6.0]


def test_a_robots_answer_we_do_not_understand_stops_the_run(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(robots=Reply(503, b"")))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL]  # nothing else is read when the rules cannot be read
    assert summary.stopped is not None
    assert "robots.txt" in summary.stopped


def test_a_refusal_stops_the_run_at_once(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(zed=Reply(403, b"no")))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, PRIZE, ZED]  # nothing after the refusal
    assert summary.stopped is not None
    assert "says no" in summary.stopped


# --------------------------------------------------------------------- the team part


def test_a_page_whose_team_part_cannot_be_cut_is_not_saved_and_stops_the_run(
    tmp_path: Path,
) -> None:
    changed_shape = (
        b"<html><body><main><h1>Zed Widget</h1><p>No team block.</p></main></body></html>"
    )
    collector, site, _ = make(tmp_path, pages(zed=page(changed_shape)))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, PRIZE, ZED]  # stopped at the first page that cannot be cut
    assert not collector.store.has(ZED)
    assert summary.stopped is not None
    assert "team part" in summary.stopped


def _unsafe(project: bytes) -> bytes:
    """The same page, but a team member's name is also written in the project's own text."""
    marker = b"<h2>Project Description</h2>"
    return project.replace(marker, marker + b"<p>Thanks to Zed Quillfeather for the idea.</p>")


def test_a_page_with_a_team_name_in_its_text_is_skipped_and_the_run_goes_on(
    tmp_path: Path,
) -> None:
    unsafe_zed = page(_unsafe(sample("project_zed_widget.html")))
    collector, _, _ = make(tmp_path, pages(zed=unsafe_zed))
    summary = collector.run()
    assert summary.pages_skipped_team_text == [ZED]
    assert not collector.store.has(ZED)  # not saved, not even in part
    assert collector.store.has(MANGO)  # the next page was saved
    assert summary.stopped is None
    for path in (tmp_path / "raw").iterdir():
        assert b"Quillfeather" not in path.read_bytes()


def test_three_unsafe_pages_in_a_row_stop_the_run(tmp_path: Path) -> None:
    slugs = [f"https://ethglobal.com/showcase/unsafe-{i}" for i in range(4)]
    prize_links = "".join(f'<li><a href="{s}">p</a></li>' for s in slugs)
    prize = page(f"<html><body><main><ul>{prize_links}</ul></main></body></html>".encode())
    unsafe = page(_unsafe(sample("project_zed_widget.html")))
    site_pages = pages(prize=prize) | {s: unsafe for s in slugs}
    collector, site, _ = make(tmp_path, site_pages)
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, PRIZE, *slugs[:3]]  # the fourth page is never requested
    assert summary.stopped is not None
    assert "3 pages in a row" in summary.stopped
    assert summary.pages_skipped_team_text == slugs[:3]


def test_a_safe_page_resets_the_count_of_unsafe_pages(tmp_path: Path) -> None:
    slugs = [f"https://ethglobal.com/showcase/mixed-{i}" for i in range(5)]
    prize_links = "".join(f'<li><a href="{s}">p</a></li>' for s in slugs)
    prize = page(f"<html><body><main><ul>{prize_links}</ul></main></body></html>".encode())
    unsafe = page(_unsafe(sample("project_zed_widget.html")))
    safe = page(sample("project_mango_ledger.html"))
    # unsafe, unsafe, safe, unsafe, unsafe: never three in a row
    replies = [unsafe, unsafe, safe, unsafe, unsafe]
    site_pages = pages(prize=prize) | dict(zip(slugs, replies, strict=True))
    collector, _, _ = make(tmp_path, site_pages)
    summary = collector.run()
    assert summary.stopped is None
    assert summary.pages_saved == 2  # the prize page and the one safe project


# ------------------------------------------------------------ pages that are missing or broken


def test_a_missing_page_is_recorded_and_the_run_goes_on(tmp_path: Path) -> None:
    site_pages = pages()
    del site_pages[MANGO]
    collector, _, _ = make(tmp_path, site_pages)
    summary = collector.run()
    assert summary.pages_not_found == [MANGO]
    assert summary.stopped is None
    assert collector.store.has(ZED)


def test_a_server_error_is_recorded_and_the_run_goes_on(tmp_path: Path) -> None:
    collector, _, _ = make(tmp_path, pages(zed=Reply(500, b"oops")))
    summary = collector.run()
    assert summary.errors == [{"url": ZED, "kind": "status 500"}]
    assert collector.store.has(MANGO)


# --------------------------------------------------------------------- starting


def test_the_unchecked_page_shape_refuses_a_live_run(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(), shape=ETHGLOBAL_SHAPE)
    with pytest.raises(CollectorRefused, match="not been checked"):
        collector.run()
    assert site.seen == []


def _settings(tmp_path: Path, **values: object) -> Settings:
    defaults = {
        "data_dir": str(tmp_path),
        "collector_name": "TestTool-research",
        "collector_contact_email": "owner@example.test",
        "collect_ethglobal": True,
    }
    return Settings(_env_file=None, **(defaults | values))  # type: ignore[arg-type]


def _write_prize_list(tmp_path: Path) -> None:
    folder = tmp_path / "by-hand" / "ethglobal.com"
    folder.mkdir(parents=True)
    (folder / "prize-pages.txt").write_text(PRIZE + "\n", encoding="utf-8")


def test_a_run_does_not_start_while_the_switch_is_off(tmp_path: Path) -> None:
    _write_prize_list(tmp_path)
    with pytest.raises(CollectorRefused, match="switch"):
        build_collector(_settings(tmp_path, collect_ethglobal=False))


def test_a_run_does_not_start_without_the_name_and_the_address(tmp_path: Path) -> None:
    _write_prize_list(tmp_path)
    with pytest.raises(CollectorRefused, match="COLLECTOR_NAME"):
        build_collector(_settings(tmp_path, collector_contact_email=""))
    with pytest.raises(CollectorRefused, match="COLLECTOR_NAME"):
        build_collector(_settings(tmp_path, collector_name=""))


def test_a_run_does_not_start_without_the_hand_checked_list(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="missing"):
        build_collector(_settings(tmp_path))


def test_turning_the_switch_off_in_the_settings_file_stops_a_running_collector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COLLECT_ETHGLOBAL", raising=False)
    _write_prize_list(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("COLLECT_ETHGLOBAL=on\n", encoding="utf-8")
    collector = build_collector(_settings(tmp_path), env_file=env_file)

    assert collector.client.is_enabled() is True
    env_file.write_text("COLLECT_ETHGLOBAL=off\n", encoding="utf-8")
    assert collector.client.is_enabled() is False  # read again, before the next request


def test_the_plan_says_what_would_be_read_and_makes_no_request(tmp_path: Path) -> None:
    _write_prize_list(tmp_path)
    text = "\n".join(plan(_settings(tmp_path)))
    assert PRIZE in text
    assert "robots.txt" in text
    assert "NO: a live run refuses" in text  # the real page shape is not checked yet
    assert "owner@example.test" not in text  # the address is never printed


def test_the_plan_says_when_the_list_is_missing(tmp_path: Path) -> None:
    text = "\n".join(plan(_settings(tmp_path)))
    assert "missing" in text
