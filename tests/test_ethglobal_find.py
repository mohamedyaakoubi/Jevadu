"""The walk through the Hedera list of the showcase, on an invented site. No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fakes import (
    HEDERA_ID,
    LIST,
    OTHER_ID,
    FakeSite,
    FakeTime,
    Reply,
    list_page,
    list_reply,
    listed,
    sample,
    session_for,
)
from hackathon_memory.collect import __main__ as cli
from hackathon_memory.collect.ethglobal import ROBOTS_URL, is_allowed_url
from hackathon_memory.collect.ethglobal_find import ListWalker, build_walker, walk_plan
from hackathon_memory.collect.ethglobal_found import FoundList, PrizeProject, load_found
from hackathon_memory.collect.ethglobal_list import is_list_url
from hackathon_memory.collect.polite import CollectorIdentity, CollectorRefused, PoliteClient
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.settings import Settings

PAGE_2 = LIST + "&page=2"
PAGE_3 = LIST + "&page=3"
CONTACT = "maintainer@example.test"

# The invented list has six projects. As on the real site, a page ends with the row that the
# next page starts with: here a page shows three rows and the list moves on by two.
PEBBLE = listed("pebble-pay", "x1y2z", HEDERA_ID)
CEDAR = listed("cedar-lens", "k9l8m", OTHER_ID)
DUNE = listed("dune-notes", "p0o9i")  # no prize, shared by the pages 1 and 2
QUARTZ = listed("quartz-notes", "q3w4e", OTHER_ID, HEDERA_ID, event="ETHGlobal Other Event")
EEL = listed("eel-ledger", "j5k6l", HEDERA_ID)  # a prize, shared by the pages 2 and 3
FIG = listed("fig-registry", "u7y6t", HEDERA_ID)
FIRST = [PEBBLE, CEDAR, DUNE]
SECOND = [DUNE, QUARTZ, EEL]
THIRD = [EEL, FIG]


def the_list(**changes: Reply) -> dict[str, Reply]:
    result = {
        ROBOTS_URL: Reply(200, sample("robots.txt"), {"Content-Type": "text/plain"}),
        LIST: list_reply(1, FIRST, has_next=True),
        PAGE_2: list_reply(2, SECOND, has_next=True),
        PAGE_3: list_reply(3, THIRD, has_next=False),
    }
    names = {"robots": ROBOTS_URL, "first": LIST, "second": PAGE_2, "third": PAGE_3}
    for key, reply in changes.items():
        result[names[key]] = reply
    return result


def make(tmp_path: Path, site_pages: dict[str, Reply], max_pages: int | None = None, **options):
    site = FakeSite(site_pages)
    fake_time = FakeTime()
    client = PoliteClient(
        site="ethglobal.com",
        identity=CollectorIdentity(name="TestTool-research", contact=CONTACT),
        allow=lambda url: is_list_url(url) or is_allowed_url(url, ()),
        is_enabled=lambda: True,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        **options,
    )
    walker = ListWalker(
        client=client,
        store=RawStore(tmp_path / "raw"),
        found_path=tmp_path / "found" / "hedera-list.json",
        runs_dir=tmp_path / "runs",
        max_pages=max_pages,
        log=lambda message: None,
    )
    return walker, site, fake_time


def found_in(tmp_path: Path) -> FoundList:
    found = load_found(tmp_path / "found" / "hedera-list.json")
    assert found is not None
    return found


# --------------------------------------------------------------------- a full walk


def test_a_walk_reads_the_list_to_its_last_page_and_keeps_the_projects_with_a_prize(
    tmp_path: Path,
) -> None:
    walker, site, fake_time = make(tmp_path, the_list())
    summary = walker.run()

    assert site.urls == [ROBOTS_URL, LIST, PAGE_2, PAGE_3]
    assert fake_time.sleeps == [2.0, 2.0, 2.0]
    assert summary.stopped is None
    assert summary.complete is True
    assert (summary.pages_read, summary.projects_listed, summary.projects_with_prize) == (3, 6, 5)
    assert summary.requests_made == 4

    found = found_in(tmp_path)
    assert found.complete is True
    assert found.pages_read == 3
    assert found.listed_by_event == {"ETHGlobal Sample Event": 5, "ETHGlobal Other Event": 1}
    assert found.with_prize == [
        PrizeProject(
            "https://ethglobal.com/showcase/pebble-pay-x1y2z",
            "ETHGlobal Sample Event",
            (HEDERA_ID,),
            1,
        ),
        PrizeProject(
            "https://ethglobal.com/showcase/cedar-lens-k9l8m",
            "ETHGlobal Sample Event",
            (OTHER_ID,),
            1,
        ),
        PrizeProject(
            "https://ethglobal.com/showcase/quartz-notes-q3w4e",
            "ETHGlobal Other Event",
            (OTHER_ID, HEDERA_ID),
            2,
        ),
        PrizeProject(
            "https://ethglobal.com/showcase/eel-ledger-j5k6l",
            "ETHGlobal Sample Event",
            (HEDERA_ID,),
            2,  # named once, by the first page that showed it
        ),
        PrizeProject(
            "https://ethglobal.com/showcase/fig-registry-u7y6t",
            "ETHGlobal Sample Event",
            (HEDERA_ID,),
            3,
        ),
    ]


def test_every_request_of_a_walk_carries_the_name_and_the_address(tmp_path: Path) -> None:
    walker, site, _ = make(tmp_path, the_list())
    walker.run()
    assert len(site.seen) == 4
    for request in site.seen:
        assert "TestTool-research" in request.headers["User-Agent"]
        assert request.headers["From"] == CONTACT


def test_a_walk_saves_no_page_of_the_list_and_no_text_of_a_project(tmp_path: Path) -> None:
    walker, _, _ = make(tmp_path, the_list())
    walker.run()
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert [name for name in written if name.endswith(".html")] == []
    assert "found/hedera-list.json" in written
    for path in tmp_path.rglob("*"):
        if path.is_file() and "raw" not in path.parts:  # raw holds robots.txt only
            text = path.read_text(encoding="utf-8")
            for kept_out in ("invented short line", "Pebble Pay", "Dune Notes", "dune-notes"):
                assert kept_out not in text, path.name
    # A project without a prize leaves only a count: its address is not kept.
    assert "dune-notes" not in (tmp_path / "found" / "hedera-list.json").read_text(encoding="utf-8")


def test_the_walk_leaves_a_record_with_counts_only(tmp_path: Path) -> None:
    walker, _, _ = make(tmp_path, the_list())
    walker.run()
    records = list((tmp_path / "runs").glob("*-ethglobal-list.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["requests_made"] == 4
    assert record["pages_read"] == 3
    assert record["projects_with_prize"] == 5
    assert record["complete"] is True
    assert record["stopped"] is None
    assert "pebble" not in records[0].read_text(encoding="utf-8")


# --------------------------------------------------------------------- the row that two pages share


def test_the_row_that_two_pages_share_is_counted_once(tmp_path: Path) -> None:
    walker, _, _ = make(tmp_path, the_list())
    walker.run()
    found = found_in(tmp_path)
    assert found.listed == 6  # eight rows were shown, and two of them twice
    assert found.listed_by_event == {"ETHGlobal Sample Event": 5, "ETHGlobal Other Event": 1}
    assert [project.page.rsplit("/", 1)[1] for project in found.with_prize].count(
        "eel-ledger-j5k6l"
    ) == 1
    assert found.page_ends_not_shared == 0


def test_a_page_that_does_not_start_with_the_last_row_is_counted_whole_and_noted(
    tmp_path: Path,
) -> None:
    # A list whose pages share no row: every row is new, and the file says how often this was.
    pages = the_list(
        second=list_reply(2, [QUARTZ, EEL], has_next=True),
        third=list_reply(3, [FIG], has_next=False),
    )
    walker, _, _ = make(tmp_path, pages)
    walker.run()
    found = found_in(tmp_path)
    assert found.listed == 6
    assert found.page_ends_not_shared == 2


# --------------------------------------------------------------------- one time


def test_a_second_walk_makes_no_request_when_the_list_was_finished(tmp_path: Path) -> None:
    make(tmp_path, the_list())[0].run()
    again, site, _ = make(tmp_path, the_list())
    summary = again.run()
    assert site.seen == []
    assert summary.requests_made == 0
    assert summary.complete is True
    assert summary.pages_read == 0


def test_a_walk_can_be_made_in_parts_and_no_page_is_asked_for_twice(tmp_path: Path) -> None:
    first, site, _ = make(tmp_path, the_list(), max_pages=1)
    summary = first.run()
    assert site.urls == [ROBOTS_URL, LIST]
    assert (summary.pages_read, summary.complete, summary.stopped) == (1, False, None)
    assert found_in(tmp_path).pages_read == 1

    second, site, _ = make(tmp_path, the_list(), max_pages=5)
    summary = second.run()
    assert site.urls == [PAGE_2, PAGE_3]  # robots.txt is saved, page 1 is not asked for again
    assert (summary.first_page, summary.pages_read, summary.complete) == (2, 2, True)
    found = found_in(tmp_path)
    assert len(found.with_prize) == 5
    assert found.listed == 6  # the row shared by two walks is also counted once


def test_what_was_found_is_written_after_every_page(tmp_path: Path) -> None:
    walker, site, _ = make(tmp_path, the_list(third=Reply(500, b"oops")))
    summary = walker.run()
    assert site.urls == [ROBOTS_URL, LIST, PAGE_2, PAGE_3]
    assert summary.stopped is not None
    assert "Page 3 of the list could not be read" in summary.stopped
    found = found_in(tmp_path)
    assert (found.pages_read, found.complete) == (2, False)  # two pages are kept

    later, site, _ = make(tmp_path, the_list())  # the site is well again
    assert later.run().complete is True
    assert site.urls == [PAGE_3]


# --------------------------------------------------------------------- the site says stop


def test_a_refusal_stops_the_walk_at_once(tmp_path: Path) -> None:
    walker, site, _ = make(tmp_path, the_list(second=Reply(429, b"slow down")))
    summary = walker.run()
    assert site.urls == [ROBOTS_URL, LIST, PAGE_2]  # no second try, no page 3
    assert summary.stopped is not None
    assert "says no" in summary.stopped
    assert found_in(tmp_path).pages_read == 1


def test_a_bot_check_stops_the_walk(tmp_path: Path) -> None:
    check = Reply(
        200, b"<html>Performing security verification</html>", {"cf-mitigated": "challenge"}
    )
    walker, site, _ = make(tmp_path, the_list(first=check))
    summary = walker.run()
    assert site.urls == [ROBOTS_URL, LIST]
    assert "says no" in (summary.stopped or "")
    assert load_found(tmp_path / "found" / "hedera-list.json") is None  # nothing was found


def test_robots_txt_is_read_first_and_obeyed_by_a_walk(tmp_path: Path) -> None:
    robots = Reply(200, b"User-agent: *\nDisallow: /showcase\n")
    walker, site, _ = make(tmp_path, the_list(robots=robots))
    summary = walker.run()
    assert site.urls == [ROBOTS_URL]
    assert "robots.txt" in (summary.stopped or "")


def test_the_limit_of_requests_stops_a_walk(tmp_path: Path) -> None:
    walker, site, _ = make(tmp_path, the_list(), max_requests=2)
    summary = walker.run()
    assert site.urls == [ROBOTS_URL, LIST]
    assert "limit of 2 requests" in (summary.stopped or "")
    assert found_in(tmp_path).pages_read == 1


# --------------------------------------------------------------- a page that is not as expected


def test_a_page_that_changed_shape_stops_the_walk_and_is_not_counted(tmp_path: Path) -> None:
    odd = Reply(200, b"<html><body><h1>Showcase</h1></body></html>", {"Content-Type": "text/html"})
    walker, site, _ = make(tmp_path, the_list(second=odd))
    summary = walker.run()
    assert site.urls == [ROBOTS_URL, LIST, PAGE_2]
    assert "Page 2 of the list is not shaped as expected" in (summary.stopped or "")
    assert found_in(tmp_path).pages_read == 1


def test_an_answer_for_another_page_stops_the_walk(tmp_path: Path) -> None:
    # The site answers page 2 with the content of page 1 (a list that starts again).
    wrong = Reply(200, list_page(1, FIRST, has_next=True), {"Content-Type": "text/html"})
    walker, site, _ = make(tmp_path, the_list(second=wrong))
    summary = walker.run()
    assert site.urls == [ROBOTS_URL, LIST, PAGE_2]
    assert "answered with page 1 of the list when page 2 was asked for" in (summary.stopped or "")
    assert found_in(tmp_path).pages_read == 1


def test_a_redirect_away_from_the_list_is_not_followed(tmp_path: Path) -> None:
    away = Reply(302, b"", {"Location": "https://ethglobal.com/login"})
    walker, site, _ = make(tmp_path, the_list(second=away))
    summary = walker.run()
    assert site.urls == [ROBOTS_URL, LIST, PAGE_2]  # the login page is never asked for
    assert "not on the list of pages named" in (summary.stopped or "")


def test_a_page_that_is_missing_stops_the_walk(tmp_path: Path) -> None:
    pages = the_list()
    del pages[PAGE_2]
    walker, _, _ = make(tmp_path, pages)
    assert "Page 2 of the list answered 404" in (walker.run().stopped or "")


def test_the_walk_only_follows_the_link_to_the_next_page(tmp_path: Path) -> None:
    walker, _, _ = make(tmp_path, {})
    for url in (
        "https://ethglobal.com/showcase/pebble-pay-x1y2z",  # a project page
        "https://ethglobal.com/showcase",  # the whole showcase
        "https://ethglobal.com/showcase?partners=other",
        "https://ethglobal.com/events",
    ):
        assert not walker.client.allow(url)
    assert walker.client.allow(LIST)
    assert walker.client.allow(PAGE_3)
    assert walker.client.allow(ROBOTS_URL)


def test_a_file_of_the_walk_that_cannot_be_read_is_not_taken_for_an_empty_one(
    tmp_path: Path,
) -> None:
    path = tmp_path / "found" / "hedera-list.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"format": 1, "site": "ethglobal.com", "pages_read": "many"}', encoding="utf-8"
    )
    walker, site, _ = make(tmp_path, the_list())
    with pytest.raises(CollectorRefused, match="cannot be read"):
        walker.run()
    assert site.seen == []  # a new walk from page 1 would ask for pages again


# --------------------------------------------------------------------- starting


def _settings(tmp_path: Path, **values: object) -> Settings:
    defaults = {
        "data_dir": str(tmp_path),
        "collector_name": "TestTool-research",
        "collector_contact_email": CONTACT,
        "collect_ethglobal": True,
    }
    return Settings(_env_file=None, **(defaults | values))  # type: ignore[arg-type]


def test_a_walk_does_not_start_while_the_switch_is_off(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="switch"):
        build_walker(_settings(tmp_path, collect_ethglobal=False))


def test_a_walk_does_not_start_without_the_name_and_the_address(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="COLLECTOR_NAME"):
        build_walker(_settings(tmp_path, collector_contact_email=""))


def test_the_number_of_pages_of_a_walk_is_one_or_more(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="1 or more"):
        build_walker(_settings(tmp_path), max_pages=0)


def test_a_built_walk_counts_its_requests_and_writes_where_the_run_looks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COLLECT_ETHGLOBAL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("COLLECT_ETHGLOBAL=on\n", encoding="utf-8")
    site, fake_time = FakeSite(the_list()), FakeTime()
    walker = build_walker(
        _settings(tmp_path),
        max_pages=2,
        env_file=env_file,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
    )
    walker.log = lambda message: None
    summary = walker.run()

    assert site.urls == [ROBOTS_URL, LIST, PAGE_2]
    assert summary.pages_read == 2
    assert (tmp_path / "found" / "ethglobal.com" / "hedera-list.json").exists()
    count = json.loads((tmp_path / "requests" / "ethglobal.com.json").read_text(encoding="utf-8"))
    assert count["sent"] == 3


def test_the_plan_of_a_walk_says_what_was_read_and_makes_no_request(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    text = "\n".join(walk_plan(settings))
    assert LIST in text
    assert "No walk was made yet" in text
    assert CONTACT not in text

    folder = tmp_path / "found" / "ethglobal.com"
    walker, _, _ = make(tmp_path, the_list(), max_pages=2)
    walker.found_path = folder / "hedera-list.json"
    walker.run()
    text = "\n".join(walk_plan(settings))
    assert "Read so far: 2 page(s), 5 projects, 4 of them with a prize" in text
    assert "The next walk starts at page 3." in text


def test_the_command_line_takes_one_command_at_a_time(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    assert cli.main(["ethglobal", "--find"]) == 1  # the switch is off
    assert "Refused" in capsys.readouterr().out
    for wrong in (
        ["ethglobal", "--find", "--plan"],
        ["ethglobal", "--pages", "3"],  # --pages goes with --find
        ["ethglobal", "--find", "--pages", "0"],
        ["ethglobal", "--find", "--pages", "many"],
        ["devpost", "--find"],
        [],
    ):
        assert cli.main(wrong) == 2, wrong
        assert "usage:" in capsys.readouterr().out
