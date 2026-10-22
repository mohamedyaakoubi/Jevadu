"""The look at ETHGlobal: two requests, nothing saved, no person printed. No network."""

from __future__ import annotations

from pathlib import Path

import pytest

from fakes import FakeSite, FakeTime, Reply, sample, session_for
from hackathon_memory.collect import __main__ as cli
from hackathon_memory.collect.ethglobal import ROBOTS_URL, is_allowed_url
from hackathon_memory.collect.look import Looker, build_looker, look_plan
from hackathon_memory.collect.polite import CollectorIdentity, CollectorRefused, PoliteClient
from hackathon_memory.settings import Settings

WINNER = "https://ethglobal.com/showcase/pebble-pay-x1y2z"
OTHER = "https://ethglobal.com/showcase/cedar-lens-k9l8m"
PROFILE = "https://ethglobal.com/showcase/eel-ledger-j5k6l"
PEOPLE = ["Samplewright", "orla-samplewright"]
CONTACT = "maintainer@example.test"


def page(body: bytes) -> Reply:
    return Reply(200, body, {"Content-Type": "text/html; charset=utf-8"})


def pages(**changes: Reply) -> dict[str, Reply]:
    result = {
        ROBOTS_URL: Reply(200, sample("robots.txt"), {"Content-Type": "text/plain"}),
        WINNER: page(sample("project_winner.html")),
        OTHER: page(sample("project_other_sponsor.html")),
        PROFILE: page(sample("project_profile_link.html")),
    }
    for key, reply in changes.items():
        result[{"robots": ROBOTS_URL, "winner": WINNER}[key]] = reply
    return result


def make(site_pages: dict[str, Reply], project: str = WINNER, **options):
    site = FakeSite(site_pages)
    fake_time = FakeTime()
    client = PoliteClient(
        site="ethglobal.com",
        identity=CollectorIdentity(name="TestTool-research", contact=CONTACT),
        allow=lambda url: is_allowed_url(url, {project}),
        is_enabled=lambda: True,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        max_requests=2,
        **options,
    )
    return Looker(client, project, log=lambda m: None), site, fake_time


def test_a_look_reads_two_pages_and_prints_the_shape_of_one() -> None:
    looker, site, fake_time = make(pages())
    report = looker.run()

    assert site.urls == [ROBOTS_URL, WINNER]  # robots.txt and the first project page
    assert report.requests_made == 2
    assert report.stopped is None
    assert fake_time.sleeps == [2.0]
    text = "\n".join(report.lines)
    assert "The project page: status 200" in text
    assert 'h3 "Winner of"' in text  # the structure of the page is visible
    assert "Team cut: passed" in text
    assert "Hedera prize on the page: yes" in text
    assert "No page was saved to disk." in text


def test_a_look_shows_no_page_text() -> None:
    report = make(pages())[0].run()
    text = "\n".join(report.lines)
    for page_text in ("Pebble Pay lets", "0.0.2345671", "Try it"):
        assert page_text not in text
    assert CONTACT not in text  # the address is only sent to the site


def test_every_request_of_a_look_carries_the_name_and_the_address() -> None:
    looker, site, _ = make(pages())
    looker.run()
    for request in site.seen:
        assert "TestTool-research" in request.headers["User-Agent"]
        assert request.headers["From"] == CONTACT


def test_a_look_never_makes_a_third_request() -> None:
    looker, site, _ = make(pages())
    looker.run()
    assert len(site.seen) == 2
    with pytest.raises(Exception, match="limit of 2 requests"):
        looker.client.get(WINNER)  # the client itself refuses
    assert len(site.seen) == 2


def test_a_refusal_by_the_site_stops_the_look_and_nothing_is_worked_around() -> None:
    looker, site, _ = make(pages(winner=Reply(403, b"no")))
    report = looker.run()
    assert report.stopped is not None
    assert "says no" in report.stopped
    assert site.urls == [ROBOTS_URL, WINNER]  # no second try


def test_robots_txt_is_obeyed_by_a_look() -> None:
    robots = Reply(200, b"User-agent: *\nDisallow: /showcase/\n")
    looker, site, _ = make(pages(robots=robots))
    report = looker.run()
    assert site.urls == [ROBOTS_URL]
    assert report.stopped is not None
    assert "robots.txt" in report.stopped


def test_a_page_that_the_team_cut_refuses_is_reported_and_the_look_goes_on() -> None:
    looker, site, _ = make(pages(), project=PROFILE)
    report = looker.run()
    text = "\n".join(report.lines)
    assert site.urls == [ROBOTS_URL, PROFILE]
    assert "Team cut: REFUSED (TeamShapeChanged" in text
    assert "A run would stop on this page." in text
    assert report.stopped is None
    for person in PEOPLE:
        assert person not in text  # the rule is named, never the person


def test_a_page_without_a_hedera_prize_is_reported() -> None:
    report = make(pages(), project=OTHER)[0].run()
    text = "\n".join(report.lines)
    assert "Hedera prize on the page: NO" in text
    assert "not kept" in text


def test_a_missing_robots_txt_forbids_nothing() -> None:
    site_pages = pages()
    del site_pages[ROBOTS_URL]
    report = make(site_pages)[0].run()
    assert "robots.txt: none (404)" in "\n".join(report.lines)
    assert report.requests_made == 2


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
    (folder / "project-pages.txt").write_text(WINNER + "\n", encoding="utf-8")


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


def test_a_look_reads_the_first_page_of_the_list_only(tmp_path: Path) -> None:
    _write_list(tmp_path)
    looker = build_looker(_settings(tmp_path))
    assert looker.project_page == WINNER
    assert looker.client.max_requests == 2
    assert looker.client.allow(WINNER)
    assert not looker.client.allow(OTHER)


def test_a_look_saves_no_page_and_counts_its_two_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COLLECT_ETHGLOBAL", raising=False)
    _write_list(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("COLLECT_ETHGLOBAL=on\n", encoding="utf-8")
    site, fake_time = FakeSite(pages()), FakeTime()
    looker = build_looker(
        _settings(tmp_path),
        env_file=env_file,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
    )
    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    report = looker.run()

    assert report.requests_made == 2
    written = {p for p in tmp_path.rglob("*") if p.is_file()} - before
    assert [p.relative_to(tmp_path).as_posix() for p in written] == ["requests/ethglobal.com.json"]
    count = written.pop().read_text(encoding="utf-8")
    assert '"sent": 2' in count
    assert "Pebble" not in count  # numbers only, no text of the page


def test_the_look_plan_says_what_would_be_read(tmp_path: Path) -> None:
    text = "\n".join(look_plan(_settings(tmp_path)))
    assert "missing" in text  # no list yet
    _write_list(tmp_path)
    text = "\n".join(look_plan(_settings(tmp_path)))
    assert ROBOTS_URL in text
    assert WINNER in text
    assert "at most two requests" in text
    assert CONTACT not in text


def test_the_command_line_refuses_a_look_while_the_switch_is_off(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    assert cli.main(["ethglobal", "--look"]) == 1
    assert "Refused" in capsys.readouterr().out
    assert cli.main(["ethglobal", "--look", "--plan"]) == 2  # one option at a time
    assert cli.main(["ethglobal", "--other"]) == 2
