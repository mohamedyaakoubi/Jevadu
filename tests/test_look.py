"""The look at ETHGlobal: three requests, nothing saved, no person printed. No network."""

from __future__ import annotations

from pathlib import Path

import pytest

from fakes import FakeSite, FakeTime, Reply, sample, session_for
from hackathon_memory.collect import __main__ as cli
from hackathon_memory.collect.ethglobal import ROBOTS_URL, is_allowed_url
from hackathon_memory.collect.look import Looker, build_looker, look_plan
from hackathon_memory.collect.polite import CollectorIdentity, CollectorRefused, PoliteClient
from hackathon_memory.settings import Settings

PRIZE = "https://ethglobal.com/events/sample-event-2099/prizes/hedera"
ZED = "https://ethglobal.com/showcase/zed-widget-a1b2c"
PEOPLE = ["Quillfeather", "Ledgerwood", "Orchardson", "quillfeather", "Samplewright"]
CONTACT = "owner@example.test"


def page(body: bytes) -> Reply:
    return Reply(200, body, {"Content-Type": "text/html; charset=utf-8"})


def pages(**changes: Reply) -> dict[str, Reply]:
    result = {
        ROBOTS_URL: Reply(200, sample("robots.txt"), {"Content-Type": "text/plain"}),
        PRIZE: page(sample("prize_page.html")),
        ZED: page(sample("project_zed_widget.html")),
    }
    for key, reply in changes.items():
        result[{"robots": ROBOTS_URL, "prize": PRIZE, "zed": ZED}[key]] = reply
    return result


def make(site_pages: dict[str, Reply], **options):
    site = FakeSite(site_pages)
    fake_time = FakeTime()
    client = PoliteClient(
        site="ethglobal.com",
        identity=CollectorIdentity(name="TestTool-research", contact=CONTACT),
        allow=is_allowed_url,
        is_enabled=lambda: True,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        max_requests=3,
        **options,
    )
    return Looker(client, PRIZE, log=lambda m: None), site, fake_time


def test_a_look_reads_three_pages_and_prints_the_shape_of_two() -> None:
    looker, site, fake_time = make(pages())
    report = looker.run()

    assert site.urls == [ROBOTS_URL, PRIZE, ZED]  # robots.txt, the prize page, the first project
    assert report.requests_made == 3
    assert report.stopped is None
    assert fake_time.sleeps == [2.0, 2.0]
    text = "\n".join(report.lines)
    assert "The prize page: status 200" in text
    assert "The project page: status 200" in text
    assert "Links on the prize page that go to a showcase project: 2" in text
    assert "section#team" in text  # the structure of the project page is visible
    assert 'h2 "Team"' in text
    assert "Nothing was saved to disk." in text


def test_a_look_shows_no_person_and_no_page_text() -> None:
    report = make(pages())[0].run()
    text = "\n".join(report.lines)
    for person in PEOPLE:
        assert person not in text
    for page_text in ("Zed Widget lets", "0.0.1234567", "Best use of Hedera"):
        assert page_text not in text
    assert CONTACT not in text  # the maintainer's address is only sent to the site


def test_every_request_of_a_look_carries_the_name_and_the_address() -> None:
    _, site, _ = (looker := make(pages()))[0], looker[1], looker[2]
    looker[0].run()
    for request in site.seen:
        assert "TestTool-research" in request.headers["User-Agent"]
        assert request.headers["From"] == CONTACT


def test_a_look_never_makes_a_fourth_request() -> None:
    looker, site, _ = make(pages())
    looker.run()
    assert len(site.seen) == 3
    with pytest.raises(Exception, match="limit of 3 requests"):
        looker.client.get(ZED)  # the client itself refuses
    assert len(site.seen) == 3


def test_a_refusal_by_the_site_stops_the_look_and_nothing_is_worked_around() -> None:
    looker, site, _ = make(pages(prize=Reply(403, b"no")))
    report = looker.run()
    assert report.stopped is not None
    assert "says no" in report.stopped
    assert site.urls == [ROBOTS_URL, PRIZE]  # no second try, no project page


def test_robots_txt_is_obeyed_by_a_look() -> None:
    robots = Reply(200, b"User-agent: *\nDisallow: /events/\n")
    looker, site, _ = make(pages(robots=robots))
    report = looker.run()
    assert site.urls == [ROBOTS_URL]
    assert report.stopped is not None
    assert "robots.txt" in report.stopped


def test_a_prize_page_with_no_project_link_is_reported_not_guessed() -> None:
    empty = page(b"<html><body><main><h1>Hedera</h1><p>No winners yet.</p></main></body></html>")
    looker, site, _ = make(pages(prize=empty))
    report = looker.run()
    assert site.urls == [ROBOTS_URL, PRIZE]
    assert "No project link was found" in "\n".join(report.lines)
    assert report.stopped is None


def test_a_missing_robots_txt_forbids_nothing() -> None:
    site_pages = pages()
    del site_pages[ROBOTS_URL]
    report = make(site_pages)[0].run()
    assert "robots.txt: none (404)" in "\n".join(report.lines)
    assert report.requests_made == 3


def _settings(tmp_path: Path, **values: object) -> Settings:
    defaults = {
        "data_dir": str(tmp_path),
        "collector_name": "TestTool-research",
        "collector_contact_email": CONTACT,
        "collect_ethglobal": True,
    }
    return Settings(_env_file=None, **(defaults | values))  # type: ignore[arg-type]


def _write_list(tmp_path: Path) -> None:
    folder = tmp_path / "by-hand" / "ethglobal.com"
    folder.mkdir(parents=True)
    (folder / "prize-pages.txt").write_text(PRIZE + "\n", encoding="utf-8")


def test_a_look_does_not_start_while_the_switch_is_off(tmp_path: Path) -> None:
    _write_list(tmp_path)
    with pytest.raises(CollectorRefused, match="switch"):
        build_looker(_settings(tmp_path, collect_ethglobal=False))


def test_a_look_needs_the_name_the_address_and_the_list(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="missing"):
        build_looker(_settings(tmp_path))
    _write_list(tmp_path)
    with pytest.raises(CollectorRefused, match="COLLECTOR_NAME"):
        build_looker(_settings(tmp_path, collector_contact_email=""))


def test_a_look_needs_no_checked_page_shape(tmp_path: Path) -> None:
    """The look is how the shape is found, so it cannot wait for the shape (unlike a run)."""
    _write_list(tmp_path)
    looker = build_looker(_settings(tmp_path))
    assert looker.prize_page == PRIZE
    assert looker.client.max_requests == 3


def test_a_look_writes_nothing_to_the_data_folder(tmp_path: Path) -> None:
    looker, _, _ = make(pages())
    before = sorted(p for p in tmp_path.rglob("*"))
    looker.run()
    assert sorted(p for p in tmp_path.rglob("*")) == before == []


def test_the_look_plan_says_what_would_be_read(tmp_path: Path) -> None:
    text = "\n".join(look_plan(_settings(tmp_path)))
    assert "missing" in text  # no list yet
    _write_list(tmp_path)
    text = "\n".join(look_plan(_settings(tmp_path)))
    assert ROBOTS_URL in text
    assert PRIZE in text
    assert "at most three requests" in text
    assert CONTACT not in text


def test_the_command_line_refuses_a_look_while_the_switch_is_off(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    assert cli.main(["ethglobal", "--look"]) == 1
    assert "Refused" in capsys.readouterr().out
    assert cli.main(["ethglobal", "--look", "--plan"]) == 2  # one option at a time
    assert cli.main(["ethglobal", "--other"]) == 2
