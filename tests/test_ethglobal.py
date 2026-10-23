"""The ETHGlobal collector, run against an invented site. Nothing here touches the internet."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from fakes import HEDERA_ID, OTHER_ID, FakeSite, FakeTime, Reply, sample, session_for
from hackathon_memory.collect.ethglobal import (
    ETHGLOBAL_SHAPE,
    MAX_LISTED_PAGES,
    ROBOTS_URL,
    EthGlobalCollector,
    SiteShape,
    build_collector,
    clear_refusal,
    is_allowed_url,
    load_project_pages,
    pages_in_run_records,
    plan,
    read_and_not_kept,
)
from hackathon_memory.collect.ethglobal_found import FoundList, FoundProject, save_found
from hackathon_memory.collect.polite import CollectorIdentity, CollectorRefused, PoliteClient
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.parse.ethglobal_page import took_a_hedera_prize
from hackathon_memory.settings import Settings

WINNER = "https://ethglobal.com/showcase/pebble-pay-x1y2z"
SECOND = "https://ethglobal.com/showcase/quartz-notes-q3w4e"
OTHER = "https://ethglobal.com/showcase/cedar-lens-k9l8m"
NO_PRIZE = "https://ethglobal.com/showcase/dune-notes-p0o9i"
PROFILE = "https://ethglobal.com/showcase/eel-ledger-j5k6l"
PERSON = "https://ethglobal.com/showcase/fig-registry-u7y6t"
A_PRIZE_PAGE = "https://ethglobal.com/events/sample-event/prizes/hedera"

# The real shape was checked against real pages on 10 October 2026. These tests use it as it is.
SHAPE = ETHGLOBAL_SHAPE


def page(body: bytes) -> Reply:
    return Reply(200, body, {"Content-Type": "text/html; charset=utf-8"})


def winner(name: str = "Pebble Pay") -> Reply:
    return page(sample("project_winner.html").replace(b"Pebble Pay", name.encode()))


def unsafe_winner() -> Reply:
    """A winner page whose author tag holds a name that is not the site's, and the name is also
    hidden in the page data. Text of a removed tag that stands elsewhere is a leak."""
    body = sample("project_winner.html")
    body = body.replace(
        b'<meta name="author" content="ETHGlobal">',
        b'<meta name="author" content="Quill Invented">',
    )
    body = body.replace(b'\\"site\\":\\"@ethglobal\\"', b'\\"by\\":\\"Quill Invented\\"')
    return page(body)


def pages(**changes: Reply) -> dict[str, Reply]:
    result = {
        ROBOTS_URL: Reply(200, sample("robots.txt"), {"Content-Type": "text/plain"}),
        WINNER: winner(),
        SECOND: winner("Quartz Notes"),
        OTHER: page(sample("project_other_sponsor.html")),
        NO_PRIZE: page(sample("project_no_prize.html")),
        PROFILE: page(sample("project_profile_link.html")),
        PERSON: page(sample("project_person_in_data.html")),
    }
    names = {
        "robots": ROBOTS_URL,
        "winner": WINNER,
        "second": SECOND,
        "other": OTHER,
        "no_prize": NO_PRIZE,
    }
    for key, reply in changes.items():
        result[names[key]] = reply
    return result


def make(
    tmp_path: Path,
    site_pages: dict[str, Reply],
    listed: tuple[str, ...] = (WINNER, SECOND),
    shape: SiteShape = SHAPE,
    max_new_pages: int | None = None,
    **options,
):
    site = FakeSite(site_pages)
    fake_time = FakeTime()
    named = frozenset(listed)
    client = PoliteClient(
        site="ethglobal.com",
        identity=CollectorIdentity(name="TestTool-research", contact="maintainer@example.test"),
        allow=lambda url: is_allowed_url(url, named),
        is_enabled=lambda: True,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        **options,
    )
    collector = EthGlobalCollector(
        client=client,
        store=RawStore(tmp_path / "raw"),
        project_pages=list(listed),
        shape=shape,
        runs_dir=tmp_path / "runs",
        max_new_pages=max_new_pages,
        log=lambda message: None,
    )
    return collector, site, fake_time


# --------------------------------------------------------------------- only the pages we named


@pytest.mark.parametrize("url", [ROBOTS_URL, WINNER, WINNER + "/"])
def test_addresses_we_named_are_allowed(url: str) -> None:
    assert is_allowed_url(url, {WINNER})


@pytest.mark.parametrize(
    "url",
    [
        SECOND,  # a project page that is not on the list
        "http://ethglobal.com/showcase/pebble-pay-x1y2z",  # not https
        "https://example.com/showcase/pebble-pay-x1y2z",  # another site
        "https://ethglobal.com.evil.test/showcase/pebble-pay-x1y2z",  # a look-alike
        "https://user@ethglobal.com/showcase/pebble-pay-x1y2z",  # a login in the address
        "https://ethglobal.com:8443/showcase/pebble-pay-x1y2z",  # another port
        "https://ethglobal.com/showcase",  # the list of the whole showcase
        "https://ethglobal.com/showcase/",
        "https://ethglobal.com/showcase/pebble-pay-x1y2z?page=2",  # a query
        "https://ethglobal.com/showcase/pebble-pay-x1y2z#team",  # a fragment
        A_PRIZE_PAGE,  # a prize page lists no winners, so it is never read
        "https://ethglobal.com/events/sample-event",
        "https://ethglobal.com/hackers/someone",  # a person
        "https://ethglobal.com/",
    ],
)
def test_other_addresses_are_never_allowed(url: str) -> None:
    assert not is_allowed_url(url, {WINNER})


def test_the_list_must_exist_and_hold_project_pages_only(tmp_path: Path) -> None:
    path = tmp_path / "project-pages.txt"
    with pytest.raises(CollectorRefused, match="missing"):
        load_project_pages(path)

    path.write_text("# only comments\n\n", encoding="utf-8")
    with pytest.raises(CollectorRefused, match="empty"):
        load_project_pages(path)

    path.write_text(f"{WINNER}\n{A_PRIZE_PAGE}\n", encoding="utf-8")
    with pytest.raises(CollectorRefused, match="line 2"):
        load_project_pages(path)


def test_the_list_ignores_comments_and_repeats(tmp_path: Path) -> None:
    path = tmp_path / "project-pages.txt"
    path.write_text(f"# made by hand\n{WINNER}  # one\n{WINNER}/\n{SECOND}\n", encoding="utf-8")
    assert load_project_pages(path) == [WINNER, SECOND]


def test_the_list_may_not_be_longer_than_the_promise_allows(tmp_path: Path) -> None:
    path = tmp_path / "project-pages.txt"
    lines = [f"https://ethglobal.com/showcase/p-{i}" for i in range(MAX_LISTED_PAGES + 1)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(CollectorRefused, match=str(MAX_LISTED_PAGES)):
        load_project_pages(path)
    path.write_text("\n".join(lines[:MAX_LISTED_PAGES]) + "\n", encoding="utf-8")
    assert len(load_project_pages(path)) == MAX_LISTED_PAGES


# --------------------------------------------------------------------- a full run


def test_a_full_run_saves_the_winners_without_personal_tags(tmp_path: Path) -> None:
    collector, site, fake_time = make(tmp_path, pages())
    summary = collector.run()

    assert site.urls == [ROBOTS_URL, WINNER, SECOND]
    assert fake_time.sleeps == [2.0, 2.0]
    assert summary.stopped is None
    assert summary.pages_saved == 2
    assert summary.pages_without_hedera_prize == []

    saved = collector.store.load(WINNER)
    assert saved is not None
    content = saved.read()
    assert b"Pebble Pay" in content
    assert b"0.0.2345671" in content
    assert b'name="author"' not in content  # the personal tags go on every page
    assert b'name="twitter:creator"' not in content
    assert saved.meta["status"] == 200
    assert saved.meta["team_cut"]["elements_removed"] == 2


def test_the_run_leaves_a_record_without_page_text(tmp_path: Path) -> None:
    collector, _, _ = make(tmp_path, pages())
    collector.run()
    records = list((tmp_path / "runs").glob("*-ethglobal.json"))
    assert len(records) == 1
    text = records[0].read_text(encoding="utf-8")
    record = json.loads(text)
    assert record["requests_made"] == 3
    assert record["stopped"] is None
    assert record["project_pages_planned"] == 2
    assert "Pebble" not in text  # no text of a page, only counts and addresses


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
    first, _, _ = make(tmp_path, pages(second=Reply(404, b"gone")))
    first.run()

    second, site, _ = make(tmp_path, pages())  # the page is back
    summary = second.run()
    assert site.urls == [SECOND]  # robots.txt and the first project are already saved
    assert summary.pages_saved == 1
    assert summary.pages_already_saved == 1


def test_a_run_can_be_made_in_parts_and_no_page_is_asked_for_twice(tmp_path: Path) -> None:
    third = "https://ethglobal.com/showcase/opal-desk-t5r4e"
    site_pages = pages() | {third: winner("Opal Desk")}
    listed = (WINNER, SECOND, third)

    first, site, _ = make(tmp_path, site_pages, listed=listed, max_new_pages=1)
    summary = first.run()
    assert site.urls == [ROBOTS_URL, WINNER]
    assert (summary.pages_saved, summary.pages_left_for_later, summary.stopped) == (1, 2, None)

    second, site, _ = make(tmp_path, site_pages, listed=listed, max_new_pages=1)
    summary = second.run()
    assert site.urls == [SECOND]  # robots.txt and the first page are saved
    assert (summary.pages_already_saved, summary.pages_saved, summary.pages_left_for_later) == (
        1,
        1,
        1,
    )

    rest, site, _ = make(tmp_path, site_pages, listed=listed)
    summary = rest.run()
    assert site.urls == [third]
    assert (summary.pages_already_saved, summary.pages_saved, summary.pages_left_for_later) == (
        2,
        1,
        0,
    )


def test_a_page_that_is_not_kept_also_counts_as_a_page_of_the_part(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(), listed=(OTHER, WINNER, SECOND), max_new_pages=2)
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, OTHER, WINNER]  # two pages were asked for, one was kept
    assert (summary.pages_saved, summary.pages_left_for_later) == (1, 1)


def test_a_page_that_was_read_and_not_kept_is_never_asked_for_again(tmp_path: Path) -> None:
    listed = (WINNER, OTHER, SECOND)
    first, site, _ = make(tmp_path, pages(), listed=listed, max_new_pages=2)
    summary = first.run()
    assert site.urls == [ROBOTS_URL, WINNER, OTHER]
    assert summary.pages_without_hedera_prize == [OTHER]

    later, site, _ = make(tmp_path, pages(), listed=listed)
    summary = later.run()
    assert site.urls == [SECOND]  # the page with no Hedera prize is not read a second time
    assert summary.pages_not_kept_before == 1
    assert summary.pages_without_hedera_prize == []
    assert (summary.pages_already_saved, summary.pages_saved) == (1, 1)

    third, site, _ = make(tmp_path, pages(), listed=listed)
    assert third.run().requests_made == 0  # and a third run still remembers it
    assert site.seen == []


def test_a_page_that_was_not_safe_to_save_is_not_asked_for_again(tmp_path: Path) -> None:
    site_pages = pages(winner=unsafe_winner())
    make(tmp_path, site_pages)[0].run()
    later, site, _ = make(tmp_path, site_pages)
    summary = later.run()
    assert site.seen == []
    assert (summary.pages_not_kept_before, summary.pages_already_saved) == (1, 1)


def test_every_run_leaves_its_own_record(tmp_path: Path) -> None:
    for _ in range(3):  # three runs in the same second
        make(tmp_path, pages())[0].run()
    records = sorted(p.name for p in (tmp_path / "runs").glob("*-ethglobal.json"))
    assert len(records) == 3
    assert not list((tmp_path / "runs").glob("*.part"))


def test_a_record_of_an_earlier_run_that_cannot_be_read_refuses_the_run(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "20261010T090000Z-ethglobal.json").write_text("{ half a record", encoding="utf-8")
    collector, site, _ = make(tmp_path, pages())
    with pytest.raises(CollectorRefused, match="record of an earlier run cannot be read"):
        collector.run()
    assert site.seen == []


def test_a_record_of_another_site_or_with_something_else_than_addresses_is_refused(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    record = runs / "20261010T090000Z-ethglobal.json"
    for content in (
        {"site": "example.com", "pages_without_hedera_prize": [], "pages_skipped_team_text": []},
        {"pages_without_hedera_prize": [], "pages_skipped_team_text": []},
        {"site": "ethglobal.com", "pages_without_hedera_prize": [7]},
        {"site": "ethglobal.com", "pages_skipped_team_text": "all"},
    ):
        record.write_text(json.dumps(content), encoding="utf-8")
        with pytest.raises(CollectorRefused, match="cannot be read"):
            read_and_not_kept(runs)
    # A key that an older record does not have yet counts as an empty list.
    record.write_text(json.dumps({"site": "ethglobal.com"}), encoding="utf-8")
    assert read_and_not_kept(runs) == set()
    assert pages_in_run_records(runs, "pages_not_found") == set()


def test_the_record_of_a_walk_is_not_the_record_of_a_run(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "20261010T090000Z-ethglobal-list.json").write_text('{"pages_read": 3}', "utf-8")
    assert read_and_not_kept(runs) == set()
    assert read_and_not_kept(tmp_path / "no-such-folder") == set()


def test_the_plan_does_not_count_a_page_that_was_read_and_not_kept(tmp_path: Path) -> None:
    folder = tmp_path / "by-hand" / "ethglobal.com"
    folder.mkdir(parents=True)
    (folder / "project-pages.txt").write_text(f"{WINNER}\n{OTHER}\n", encoding="utf-8")
    runs = tmp_path / "runs"
    runs.mkdir()
    record = {
        "site": "ethglobal.com",
        "pages_without_hedera_prize": [OTHER],
        "pages_skipped_team_text": [],
    }
    (runs / "20261010T090000Z-ethglobal.json").write_text(json.dumps(record), encoding="utf-8")

    text = "\n".join(plan(_settings(tmp_path)))
    assert f"{OTHER}  (read before and not kept: not asked for again)" in text
    assert f"{WINNER}  (to fetch)" in text
    assert "That is 2 request(s)." in text  # robots.txt and the one page that is left


def test_a_part_of_a_run_is_one_page_or_more(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="1 or more"):
        make(tmp_path, pages(), max_new_pages=0)


def test_the_limit_stops_the_run_and_the_record_says_so(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(), max_requests=2)
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, WINNER]
    assert summary.stopped is not None
    assert "limit of 2 requests" in summary.stopped
    assert collector.store.has(WINNER)
    assert not collector.store.has(SECOND)
    assert list((tmp_path / "runs").glob("*.json"))  # the record is written even when stopped


# --------------------------------------------------------------------- the site says stop


def test_robots_txt_is_read_first_and_obeyed(tmp_path: Path) -> None:
    robots = Reply(200, b"User-agent: *\nDisallow: /showcase/\n")
    collector, site, _ = make(tmp_path, pages(robots=robots))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL]  # no project page is read
    assert summary.stopped is not None
    assert "robots.txt" in summary.stopped


def test_a_crawl_delay_in_robots_txt_makes_the_pause_longer(tmp_path: Path) -> None:
    robots = Reply(200, b"User-agent: *\nCrawl-delay: 6\n")
    collector, _, fake_time = make(tmp_path, pages(robots=robots))
    collector.run()
    assert fake_time.sleeps == [6.0, 6.0]


def test_a_robots_answer_we_do_not_understand_stops_the_run(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(robots=Reply(503, b"")))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL]  # nothing else is read when the rules cannot be read
    assert summary.stopped is not None
    assert "robots.txt" in summary.stopped


def test_a_refusal_stops_the_run_at_once(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(winner=Reply(403, b"no")))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, WINNER]  # nothing after the refusal
    assert summary.stopped is not None
    assert "says no" in summary.stopped


# --------------------------------------------------------------------- only Hedera winners are kept


def test_a_page_without_a_hedera_prize_is_read_but_not_kept(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(), listed=(WINNER, OTHER, NO_PRIZE))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, WINNER, OTHER, NO_PRIZE]
    assert summary.pages_without_hedera_prize == [OTHER, NO_PRIZE]
    assert summary.pages_saved == 1
    assert summary.stopped is None
    assert not collector.store.has(OTHER)
    assert not collector.store.has(NO_PRIZE)
    for path in (tmp_path / "raw").iterdir():
        assert b"Cedar Lens" not in path.read_bytes()  # not kept, not even in part


def test_three_pages_in_a_row_without_a_hedera_prize_stop_the_run(tmp_path: Path) -> None:
    # A list that names the wrong projects: the run must not read on through it.
    wrong = [f"https://ethglobal.com/showcase/wrong-{i}" for i in range(4)]
    site_pages = pages() | {url: page(sample("project_other_sponsor.html")) for url in wrong}
    collector, site, _ = make(tmp_path, site_pages, listed=(*wrong, WINNER))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, *wrong[:3]]  # the fourth page and the winner are not read
    assert summary.stopped is not None
    assert "3 pages in a row show no Hedera prize" in summary.stopped
    assert summary.pages_without_hedera_prize == wrong[:3]
    assert summary.pages_saved == 0


def test_a_kept_page_resets_the_count_of_pages_without_a_prize(tmp_path: Path) -> None:
    wrong = [f"https://ethglobal.com/showcase/wrong-{i}" for i in range(4)]
    site_pages = pages() | {url: page(sample("project_no_prize.html")) for url in wrong}
    listed = (wrong[0], wrong[1], WINNER, wrong[2], wrong[3])  # never three in a row
    collector, _, _ = make(tmp_path, site_pages, listed=listed)
    summary = collector.run()
    assert summary.stopped is None
    assert summary.pages_saved == 1
    assert len(summary.pages_without_hedera_prize) == 4


def test_the_message_about_a_page_that_is_not_kept_names_the_sponsors_it_shows(
    tmp_path: Path,
) -> None:
    said: list[str] = []
    collector, _, _ = make(tmp_path, pages(), listed=(WINNER, OTHER, NO_PRIZE))
    collector.log = said.append
    collector.run()
    assert f"not kept {OTHER}: the page shows no Hedera prize (it shows: Other Sponsor)" in said
    assert f"not kept {NO_PRIZE}: the page shows no Hedera prize (it shows: no prize)" in said


# --------------------------------------------------------------------- the team part


def test_a_page_that_shows_a_profile_link_stops_the_run(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(), listed=(PROFILE, SECOND))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, PROFILE]  # the second page is never requested
    assert not collector.store.has(PROFILE)
    assert summary.stopped is not None
    assert "team part" in summary.stopped
    for path in (tmp_path / "raw").iterdir():
        assert b"Samplewright" not in path.read_bytes()


def test_a_page_whose_data_holds_members_stops_the_run(tmp_path: Path) -> None:
    collector, site, _ = make(tmp_path, pages(), listed=(PERSON, SECOND))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, PERSON]
    assert not collector.store.has(PERSON)
    assert summary.stopped is not None
    assert "'members'" in summary.stopped
    assert "Samplewright" not in summary.stopped  # the key is named, never what it holds
    records = (tmp_path / "runs").glob("*.json")
    assert all("Samplewright" not in p.read_text(encoding="utf-8") for p in records)


def test_the_name_of_the_site_in_the_tags_is_not_taken_for_a_person(tmp_path: Path) -> None:
    # The same real shape, but without the names of the site: the handle that also stands in the
    # page data looks like a leaked name, and the page is refused. This is what the real pages
    # would have done to the first version of the shape.
    without_site_names = SiteShape(
        project_cut=replace(SHAPE.project_cut, site_names=frozenset()), verified_on="test"
    )
    collector, _, _ = make(tmp_path, pages(), shape=without_site_names)
    summary = collector.run()
    assert summary.pages_skipped_team_text == [WINNER, SECOND]
    assert summary.pages_saved == 0

    kept, _, _ = make(tmp_path / "real", pages())
    assert kept.run().pages_saved == 2


def test_a_page_with_a_name_hidden_in_its_data_is_skipped_and_the_run_goes_on(
    tmp_path: Path,
) -> None:
    site_pages = pages(winner=unsafe_winner())
    collector, _, _ = make(tmp_path, site_pages)
    summary = collector.run()
    assert summary.pages_skipped_team_text == [WINNER]
    assert not collector.store.has(WINNER)  # not saved, not even in part
    assert collector.store.has(SECOND)  # the next page was saved
    assert summary.stopped is None
    for path in (tmp_path / "raw").iterdir():
        assert b"Quill Invented" not in path.read_bytes()


def test_three_unsafe_pages_in_a_row_stop_the_run(tmp_path: Path) -> None:
    slugs = [f"https://ethglobal.com/showcase/unsafe-{i}" for i in range(4)]
    site_pages = pages() | {s: unsafe_winner() for s in slugs}
    collector, site, _ = make(tmp_path, site_pages, listed=tuple(slugs))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, *slugs[:3]]  # the fourth page is never requested
    assert summary.stopped is not None
    assert "3 pages in a row" in summary.stopped
    assert summary.pages_skipped_team_text == slugs[:3]


def test_a_safe_page_resets_the_count_of_unsafe_pages(tmp_path: Path) -> None:
    slugs = [f"https://ethglobal.com/showcase/mixed-{i}" for i in range(5)]
    # unsafe, unsafe, safe, unsafe, unsafe: never three in a row
    replies = [unsafe_winner(), unsafe_winner(), winner(), unsafe_winner(), unsafe_winner()]
    site_pages = pages() | dict(zip(slugs, replies, strict=True))
    collector, _, _ = make(tmp_path, site_pages, listed=tuple(slugs))
    summary = collector.run()
    assert summary.stopped is None
    assert summary.pages_saved == 1


# ------------------------------------------------------------ pages that are missing or broken


def test_a_missing_page_is_recorded_and_the_run_goes_on(tmp_path: Path) -> None:
    site_pages = pages()
    del site_pages[SECOND]
    collector, _, _ = make(tmp_path, site_pages)
    summary = collector.run()
    assert summary.pages_not_found == [SECOND]
    assert summary.stopped is None
    assert collector.store.has(WINNER)


def test_a_server_error_is_recorded_and_the_run_goes_on(tmp_path: Path) -> None:
    collector, _, _ = make(tmp_path, pages(winner=Reply(500, b"oops")))
    summary = collector.run()
    assert summary.errors == [{"url": WINNER, "kind": "status 500"}]
    assert collector.store.has(SECOND)


# --------------------------------------------------------------------- starting


def test_the_shape_of_the_real_pages_was_checked() -> None:
    assert ETHGLOBAL_SHAPE.verified_on is not None
    assert ETHGLOBAL_SHAPE.checked_pages


def test_an_unchecked_page_shape_refuses_a_live_run(tmp_path: Path) -> None:
    unchecked = SiteShape(project_cut=SHAPE.project_cut, verified_on=None)
    collector, site, _ = make(tmp_path, pages(), shape=unchecked)
    with pytest.raises(CollectorRefused, match="not been checked"):
        collector.run()
    assert site.seen == []


def _settings(tmp_path: Path, **values: object) -> Settings:
    defaults = {
        "data_dir": str(tmp_path),
        "collector_name": "TestTool-research",
        "collector_contact_email": "maintainer@example.test",
        "collect_ethglobal": True,
    }
    return Settings(_env_file=None, **(defaults | values))  # type: ignore[arg-type]


def _write_page_list(tmp_path: Path) -> None:
    folder = tmp_path / "by-hand" / "ethglobal.com"
    folder.mkdir(parents=True)
    (folder / "project-pages.txt").write_text(WINNER + "\n", encoding="utf-8")


def test_a_run_does_not_start_while_the_switch_is_off(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    with pytest.raises(CollectorRefused, match="switch"):
        build_collector(_settings(tmp_path, collect_ethglobal=False))


def test_a_run_does_not_start_without_the_name_and_the_address(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    with pytest.raises(CollectorRefused, match="COLLECTOR_NAME"):
        build_collector(_settings(tmp_path, collector_contact_email=""))
    with pytest.raises(CollectorRefused, match="COLLECTOR_NAME"):
        build_collector(_settings(tmp_path, collector_name=""))


def test_a_run_does_not_start_without_the_hand_made_list(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="missing"):
        build_collector(_settings(tmp_path))


def test_the_built_collector_may_read_the_listed_pages_only(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    collector = build_collector(_settings(tmp_path))
    assert collector.client.allow(WINNER)
    assert collector.client.allow(ROBOTS_URL)
    assert not collector.client.allow(SECOND)  # a project page that is not on the list
    assert not collector.client.allow(A_PRIZE_PAGE)


# --------------------------------------------------------------------- the projects of the walk


def _write_walk(tmp_path: Path, *projects: tuple[str, tuple[str, ...]], complete: bool = True):
    found = FoundList(
        started_at="2026-10-10T09:00:00Z",
        updated_at="2026-10-10T09:01:00Z",
        pages_read=2,
        complete=complete,
        projects=[
            FoundProject(page, "ETHGlobal Sample Event", sponsors, 1) for page, sponsors in projects
        ],
    )
    save_found(tmp_path / "found" / "ethglobal.com" / "hedera-list.json", found)


# What the Hedera list of the invented site holds: two winners of a Hedera prize, one project
# with a prize of another sponsor, and one with no prize.
WALK = (
    (WINNER, (HEDERA_ID,)),
    (SECOND, (OTHER_ID, HEDERA_ID)),
    (OTHER, (OTHER_ID,)),
    (NO_PRIZE, ()),
)


def test_a_run_reads_the_pages_seen_by_hand_and_then_every_project_of_the_walk(
    tmp_path: Path,
) -> None:
    _write_page_list(tmp_path)  # one page seen by hand: WINNER
    _write_walk(tmp_path, WALK[1], WALK[0], *WALK[2:])
    collector = build_collector(_settings(tmp_path))
    assert collector.project_pages == [WINNER, SECOND, OTHER, NO_PRIZE]
    assert collector.in_the_list == {WINNER, SECOND, OTHER, NO_PRIZE}
    assert collector.hedera_in_the_list == {WINNER, SECOND}
    for page in (WINNER, SECOND, OTHER, NO_PRIZE):
        assert collector.client.allow(page)
    assert not collector.client.allow(PERSON)  # a project that the list does not name
    assert not collector.client.allow("https://ethglobal.com/showcase?partners=hedera")


def listed_run(tmp_path: Path, site_pages: dict[str, Reply], listed: tuple[str, ...], **options):
    """A run on a list that the walk found: WINNER and SECOND took a Hedera prize in the list."""
    collector, site, fake_time = make(tmp_path, site_pages, listed=listed, **options)
    collector.in_the_list = frozenset(listed)
    collector.hedera_in_the_list = frozenset({WINNER, SECOND}) & frozenset(listed)
    return collector, site, fake_time


def test_every_page_of_the_list_is_kept_with_or_without_a_prize(tmp_path: Path) -> None:
    listed = (WINNER, OTHER, NO_PRIZE, SECOND)
    collector, site, _ = listed_run(tmp_path, pages(), listed)
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, *listed]
    assert summary.pages_saved == 4
    assert summary.pages_without_hedera_prize == []  # nothing was read and dropped
    assert summary.pages_that_differ_from_the_list == []
    assert summary.stopped is None
    for page in listed:
        assert collector.store.has(page)
    kept = collector.store.load(NO_PRIZE)
    assert kept is not None
    assert not took_a_hedera_prize(kept.read())  # the page itself says that it took no prize


def test_many_pages_with_no_prize_in_a_row_do_not_stop_a_run_on_the_list(tmp_path: Path) -> None:
    plain = [f"https://ethglobal.com/showcase/plain-{i}" for i in range(6)]
    site_pages = pages() | {url: page(sample("project_no_prize.html")) for url in plain}
    collector, _, _ = listed_run(tmp_path, site_pages, (*plain, WINNER))
    summary = collector.run()
    assert summary.stopped is None
    assert summary.pages_saved == 7


def test_a_page_that_differs_from_the_list_is_kept_and_noted(tmp_path: Path) -> None:
    # The list names a Hedera prize for SECOND, and its page shows another sponsor's prize.
    site_pages = pages(second=page(sample("project_other_sponsor.html")))
    said: list[str] = []
    collector, _, _ = listed_run(tmp_path, site_pages, (WINNER, SECOND, OTHER))
    collector.log = said.append
    summary = collector.run()
    assert summary.pages_that_differ_from_the_list == [SECOND]
    assert summary.pages_saved == 3  # it is a project of the list, so it is kept
    assert summary.stopped is None
    assert (
        f"differs {SECOND}: the list names a Hedera prize, and the page shows: Other Sponsor"
        in said
    )


def test_a_page_with_a_hedera_prize_that_the_list_does_not_name_is_noted_too(
    tmp_path: Path,
) -> None:
    said: list[str] = []
    collector, _, _ = listed_run(tmp_path, pages(other=winner("Cedar Lens")), (WINNER, OTHER))
    collector.log = said.append
    summary = collector.run()
    assert summary.pages_that_differ_from_the_list == [OTHER]
    assert any(line.startswith(f"differs {OTHER}: the list does not name") for line in said)


def test_three_pages_in_a_row_that_differ_from_the_list_stop_the_run(tmp_path: Path) -> None:
    # The tool took the wrong sponsor id for Hedera: the winners of the list show no Hedera prize.
    wrong = [f"https://ethglobal.com/showcase/wrong-{i}" for i in range(4)]
    site_pages = pages() | {url: page(sample("project_other_sponsor.html")) for url in wrong}
    collector, site, _ = make(tmp_path, site_pages, listed=(*wrong, WINNER))
    collector.in_the_list = frozenset((*wrong, WINNER))
    collector.hedera_in_the_list = frozenset(wrong)
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, *wrong[:3]]  # the fourth page and the winner are not read
    assert summary.stopped is not None
    assert "3 pages in a row do not agree with the list" in summary.stopped
    assert summary.pages_that_differ_from_the_list == wrong[:3]
    assert summary.pages_saved == 3


def test_a_page_that_agrees_resets_the_count_of_pages_that_differ(tmp_path: Path) -> None:
    wrong = [f"https://ethglobal.com/showcase/wrong-{i}" for i in range(4)]
    site_pages = pages() | {url: page(sample("project_no_prize.html")) for url in wrong}
    listed = (wrong[0], wrong[1], WINNER, wrong[2], wrong[3])  # never three in a row
    collector, _, _ = make(tmp_path, site_pages, listed=listed)
    collector.in_the_list = frozenset(listed)
    collector.hedera_in_the_list = frozenset((*wrong, WINNER))
    summary = collector.run()
    assert summary.stopped is None
    assert len(summary.pages_that_differ_from_the_list) == 4


def test_a_page_seen_by_hand_outside_the_list_is_kept_only_with_a_hedera_prize(
    tmp_path: Path,
) -> None:
    # OTHER and SECOND were put on the hand-made list. The walk does not name them.
    collector, _, _ = make(tmp_path, pages(), listed=(OTHER, SECOND, WINNER))
    collector.in_the_list = frozenset({WINNER})
    collector.hedera_in_the_list = frozenset({WINNER})
    summary = collector.run()
    assert summary.pages_without_hedera_prize == [OTHER]
    assert not collector.store.has(OTHER)
    assert collector.store.has(SECOND)  # it shows a Hedera prize
    assert collector.store.has(WINNER)


def test_a_run_refuses_a_walk_when_no_page_seen_by_hand_says_which_sponsor_is_hedera(
    tmp_path: Path,
) -> None:
    _write_walk(tmp_path, *WALK)
    with pytest.raises(CollectorRefused, match="Winner of") as refusal:
        build_collector(_settings(tmp_path))  # there is no hand-made list at all
    assert "The walk found 4 projects" in str(refusal.value)

    folder = tmp_path / "by-hand" / "ethglobal.com"
    folder.mkdir(parents=True)
    # SECOND took prizes of two sponsors: not enough to decide.
    (folder / "project-pages.txt").write_text(SECOND + "\n", encoding="utf-8")
    with pytest.raises(CollectorRefused, match="share 2 sponsor ids"):
        build_collector(_settings(tmp_path))


def test_a_run_refuses_when_the_pages_seen_by_hand_are_not_in_the_walk(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    _write_walk(tmp_path, (SECOND, (HEDERA_ID,)), (OTHER, (OTHER_ID,)))
    with pytest.raises(CollectorRefused, match="None of the pages seen by hand"):
        build_collector(_settings(tmp_path))


def test_a_run_refuses_a_file_of_the_walk_that_cannot_be_read(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    folder = tmp_path / "found" / "ethglobal.com"
    folder.mkdir(parents=True)
    (folder / "hedera-list.json").write_text("{ half a file", encoding="utf-8")
    with pytest.raises(CollectorRefused, match="cannot be read"):
        build_collector(_settings(tmp_path))


def test_a_run_may_not_read_more_pages_than_the_limit_of_the_site_allows(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    many = [(f"https://ethglobal.com/showcase/w-{i}", ()) for i in range(MAX_LISTED_PAGES)]
    _write_walk(tmp_path, (WINNER, (HEDERA_ID,)), *many)
    with pytest.raises(CollectorRefused, match=f"a run may read {MAX_LISTED_PAGES}"):
        build_collector(_settings(tmp_path))


def test_the_plan_says_where_the_pages_come_from(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    text = "\n".join(plan(_settings(tmp_path)))
    assert "1 page(s) by hand, and 0 more from the walk." in text
    assert "No walk through the Hedera list was made" in text

    _write_walk(tmp_path, *WALK, complete=False)
    text = "\n".join(plan(_settings(tmp_path)))
    assert "1 page(s) by hand, and 3 more from the walk." in text
    assert "The walk found 4 projects in the Hedera list of the showcase." in text
    assert "2 took a Hedera prize" in text
    assert f"the sponsor with the id {HEDERA_ID} is Hedera" in text
    assert "1 took a prize of another sponsor only, and 1 took no prize." in text
    assert "The walk is not finished: 2 page(s) of the list were read." in text
    assert "The run has 4 page(s): 0 saved, 4 to fetch." in text
    for listed in (WINNER, SECOND, OTHER, NO_PRIZE):
        assert listed in text
    assert PERSON not in text  # a page that a run does not read is not in its plan
    assert "That is 5 request(s)." in text  # robots.txt and four pages


def test_the_plan_of_a_long_list_shows_its_numbers_and_its_first_pages(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    many = [(f"https://ethglobal.com/showcase/w-{i}", ()) for i in range(40)]
    _write_walk(tmp_path, (WINNER, (HEDERA_ID,)), *many)
    lines = plan(_settings(tmp_path))
    text = "\n".join(lines)
    assert "The run has 41 page(s): 0 saved, 41 to fetch." in text
    assert "... and 31 more pages to fetch" in text
    assert "https://ethglobal.com/showcase/w-8  (to fetch)" in text
    assert "https://ethglobal.com/showcase/w-30" not in text
    assert "That is 42 request(s)." in text
    assert len(lines) < 40


def test_the_plan_says_why_a_walk_cannot_be_used(tmp_path: Path) -> None:
    _write_walk(tmp_path, *WALK)
    text = "\n".join(plan(_settings(tmp_path)))
    assert "which id is Hedera" in text
    assert "It would read" not in text


def test_a_page_seen_by_hand_that_is_not_in_the_walk_is_said_in_the_plan(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "by-hand" / "ethglobal.com"
    folder.mkdir(parents=True)
    (folder / "project-pages.txt").write_text(f"{WINNER}\n{PERSON}\n", encoding="utf-8")
    _write_walk(tmp_path, (WINNER, (HEDERA_ID,)), (SECOND, (HEDERA_ID,)))
    text = "\n".join(plan(_settings(tmp_path)))
    assert "1 page(s) seen by hand are not in the list." in text
    assert "2 page(s) by hand, and 1 more from the walk." in text


def _write_count(tmp_path: Path, content: str) -> None:
    folder = tmp_path / "requests"
    folder.mkdir(parents=True)
    (folder / "ethglobal.com.json").write_text(content, encoding="utf-8")


def test_a_built_collector_counts_its_requests_over_all_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COLLECT_ETHGLOBAL", raising=False)
    _write_page_list(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("COLLECT_ETHGLOBAL=on\n", encoding="utf-8")
    site, fake_time = FakeSite(pages()), FakeTime()
    collector = build_collector(
        _settings(tmp_path),
        env_file=env_file,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
    )
    collector.log = lambda message: None
    summary = collector.run()

    assert site.urls == [ROBOTS_URL, WINNER]
    assert summary.pages_saved == 1
    count = json.loads((tmp_path / "requests" / "ethglobal.com.json").read_text(encoding="utf-8"))
    assert count["sent"] == 2


def test_a_run_that_needs_more_requests_than_are_left_does_not_start(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    # 799 of the 800 are used. One page and robots.txt need two.
    _write_count(tmp_path, '{"site": "ethglobal.com", "sent": 799, "by_day": {}}')
    with pytest.raises(CollectorRefused, match="needs 2 requests, and 1 are left of the 800"):
        build_collector(_settings(tmp_path))


def test_a_run_does_not_start_when_the_count_cannot_be_read(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    _write_count(tmp_path, "broken")
    with pytest.raises(CollectorRefused, match="cannot be read"):
        build_collector(_settings(tmp_path))


def test_turning_the_switch_off_in_the_settings_file_stops_a_running_collector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COLLECT_ETHGLOBAL", raising=False)
    _write_page_list(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("COLLECT_ETHGLOBAL=on\n", encoding="utf-8")
    collector = build_collector(_settings(tmp_path), env_file=env_file)

    assert collector.client.is_enabled() is True
    env_file.write_text("COLLECT_ETHGLOBAL=off\n", encoding="utf-8")
    assert collector.client.is_enabled() is False  # read again, before the next request


def test_the_plan_says_what_would_be_read_and_makes_no_request(tmp_path: Path) -> None:
    _write_page_list(tmp_path)
    text = "\n".join(plan(_settings(tmp_path)))
    assert WINNER in text
    assert "robots.txt" in text
    assert str(ETHGLOBAL_SHAPE.verified_on) in text  # the shape was checked against real pages
    assert "maintainer@example.test" not in text  # the address is never printed
    assert "Requests sent to the site so far: 0 of 800." in text
    assert "That is 2 request(s)." in text  # robots.txt and the one page of the list
    assert not (tmp_path / "requests").exists()  # a plan writes nothing


def test_the_plan_says_when_the_list_is_missing(tmp_path: Path) -> None:
    text = "\n".join(plan(_settings(tmp_path)))
    assert "missing" in text


# --------------------------------------------------------------------- too many requests


def _built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, site_pages: dict, **options):
    """A collector as the command builds it, with its count on disk, on the invented site."""
    monkeypatch.delenv("COLLECT_ETHGLOBAL", raising=False)
    folder = tmp_path / "by-hand" / "ethglobal.com"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project-pages.txt").write_text(f"{WINNER}\n{SECOND}\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("COLLECT_ETHGLOBAL=on\n", encoding="utf-8")
    site, fake_time = FakeSite(site_pages), FakeTime()
    collector = build_collector(
        _settings(tmp_path),
        env_file=env_file,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        **options,
    )
    collector.log = lambda message: None
    return collector, site, fake_time


TOO_MANY = Reply(429, b"slow down")


def test_too_many_requests_stop_a_run_and_the_next_command_waits_for_the_cooldown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector, site, _ = _built(tmp_path, monkeypatch, pages(second=TOO_MANY))
    summary = collector.run()
    assert site.urls == [ROBOTS_URL, WINNER, SECOND]  # no second try
    assert "too many requests" in (summary.stopped or "")
    assert collector.store.has(WINNER)
    assert not collector.store.has(SECOND)

    # The next command, a minute later: it is refused before it is built, and it says until when.
    with pytest.raises(CollectorRefused, match="cooldown runs until") as refusal:
        _built(tmp_path, monkeypatch, pages())
    assert "--wait" in str(refusal.value)
    text = "\n".join(plan(_settings(tmp_path)))
    assert 'said "too many requests". The cooldown runs until' in text
    assert "the pause between two requests is 10 seconds" in text


def test_a_run_that_was_told_to_wait_goes_on_by_itself_and_slower(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The site says "too many requests" once for the second page, and answers it the next time.
    site_pages = pages() | {SECOND: [TOO_MANY, winner("Quartz Notes")]}
    said: list[str] = []
    collector, site, fake_time = _built(tmp_path, monkeypatch, site_pages, wait_for_cooldown=True)
    collector.log = said.append
    summary = collector.run()

    assert site.urls == [ROBOTS_URL, WINNER, SECOND, SECOND]
    assert summary.stopped is None
    assert summary.pages_saved == 2
    assert summary.cooldowns_waited == 1
    assert any(line.startswith("WAITING: ethglobal.com answered 429") for line in said)
    assert max(fake_time.sleeps) > 3590  # the hour of the cooldown
    assert collector.client.pause_in_use() == 10.0  # and five times slower from then on


def test_a_run_that_starts_during_a_cooldown_waits_first_when_it_was_told_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, _, _ = _built(tmp_path, monkeypatch, pages(second=TOO_MANY))
    first.run()
    later, site, fake_time = _built(tmp_path, monkeypatch, pages(), wait_for_cooldown=True)
    summary = later.run()
    assert site.urls == [SECOND]  # robots.txt and the first page are saved
    assert summary.pages_saved == 1
    assert fake_time.sleeps[0] > 3590  # it waited before its first request
    assert summary.pause_seconds == 10.0


def test_a_no_of_the_site_stops_every_later_command_until_a_person_decides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector, _, _ = _built(tmp_path, monkeypatch, pages(second=Reply(403, b"no")))
    assert "says no" in (collector.run().stopped or "")
    with pytest.raises(CollectorRefused, match="refused a request") as refusal:
        _built(tmp_path, monkeypatch, pages(), wait_for_cooldown=True)  # waiting does not help
    assert "--after-refusal" in str(refusal.value)
    assert "refused a request" in "\n".join(plan(_settings(tmp_path)))

    with pytest.raises(CollectorRefused, match="what was decided"):
        clear_refusal(_settings(tmp_path), "   ")
    lines = clear_refusal(
        _settings(tmp_path), "the site wrote on 12 October that the tool may go on"
    )
    assert lines == ["The refusal is cleared, and the decision is written next to the count."]
    assert clear_refusal(_settings(tmp_path), "again") == ["There is no refusal to clear."]
    later, site, _ = _built(tmp_path, monkeypatch, pages())
    assert later.run().pages_saved == 1
    assert site.urls == [SECOND]


def test_the_pause_can_be_made_longer_and_never_shorter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector, _, fake_time = _built(tmp_path, monkeypatch, pages(), pause_seconds=7.0)
    collector.run()
    assert fake_time.sleeps == [7.0, 7.0]
    with pytest.raises(CollectorRefused, match="never shorter than 2 seconds"):
        _built(tmp_path, monkeypatch, pages(), pause_seconds=1.0)


def test_the_record_of_a_run_keeps_what_the_site_said_about_its_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = sample("project_winner.html")
    limits = {"Content-Type": "text/html", "CF-Cache-Status": "MISS", "Set-Cookie": "a=b"}
    site_pages = pages() | {WINNER: Reply(200, body, limits)}
    said: list[str] = []
    collector, _, _ = _built(tmp_path, monkeypatch, site_pages)
    collector.log = said.append
    collector.run()
    # Said once, early, so that a person can see it while a long run goes on.
    assert [line for line in said if line.startswith("the site says about limits")] == [
        "the site says about limits and caches: {'cf-cache-status': 'MISS'}"
    ]
    record = json.loads(next((tmp_path / "runs").glob("*-ethglobal.json")).read_text("utf-8"))
    assert record["site_headers"] == {"cf-cache-status": "MISS"}
    assert record["cache_answers"] == {"cf-cache-status: MISS": 1}
    assert record["pause_seconds"] == 2.0
    assert "a=b" not in json.dumps(record)  # no cookie, and no other header
