"""The small collector of the Africa winners page, against a fake site. The page is invented."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fakes import FakeSite, FakeTime, Reply, session_for
from hackathon_memory.collect import africa_winners as africa
from hackathon_memory.collect.polite import CollectorRefused
from hackathon_memory.settings import Settings

CONTACT = "tests@example.org"
PEOPLE = ("Quillfeather", "Ledgerwood")


def invented_page() -> bytes:
    """A winners page in the shape of a Next.js page: its data is pushed by a script."""
    data = {
        "winners": [
            {"project": "Invented Pay", "track": "Payments", "place": 1,
             "team": [{"name": PEOPLE[0]}], "link": "https://dorahacks.io/buidl/1"},
            {"project": "Invented Post", "track": "Logistics", "place": 2,
             "team": [{"name": PEOPLE[1]}], "link": "https://dorahacks.io/buidl/2"},
        ]
    }  # fmt: skip
    pushed = json.dumps(f"0:{json.dumps(data)}\n")
    return (
        "<html><head><title>Invented Winners</title></head><body><h1>Winners</h1>"
        f"<script>self.__next_f.push([1,{pushed}])</script></body></html>"
    ).encode()


def settings(tmp_path: Path, *, switch: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=str(tmp_path / "data"),
        collector_name="TestTool",
        collector_contact_email=CONTACT,
        collect_africa_winners=switch,
    )


def env_file(tmp_path: Path, switch: str = "on") -> Path:
    path = tmp_path / ".env"
    path.write_text(f"COLLECT_AFRICA_WINNERS={switch}\n", encoding="utf-8")
    return path


def client(tmp_path: Path, site: FakeSite, fake_time: FakeTime):
    return africa.client_for(
        settings(tmp_path),
        env_file=env_file(tmp_path),
        session=session_for(site),
        sleep=fake_time.sleep,
        clock=fake_time.clock,
    )


def answering(page: Reply) -> FakeSite:
    return FakeSite({africa.ROBOTS_URL: Reply(404, b"not here"), africa.PAGE: page})


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        (africa.PAGE, True),
        (f"https://{africa.SITE}", True),
        (africa.ROBOTS_URL, True),
        (f"https://{africa.SITE}/winners", False),
        (f"https://{africa.SITE}/?page=2", False),
        (f"http://{africa.SITE}/", False),
        ("https://dorahacks.io/buidl/1", False),  # its links are never followed
        (f"https://{africa.SITE}.example.test/", False),
    ],
)
def test_only_the_page_and_its_robots_file_may_be_read(url: str, allowed: bool) -> None:
    assert africa.is_allowed_url(url) is allowed


def test_nothing_is_sent_while_the_switch_is_off(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="COLLECT_AFRICA_WINNERS=on"):
        africa.client_for(settings(tmp_path, switch=False))


def test_the_look_prints_the_shape_and_saves_nothing(tmp_path: Path) -> None:
    site = answering(Reply(200, invented_page(), {"Content-Type": "text/html"}))
    fake_time = FakeTime()
    said: list[str] = []
    assert africa.look(client(tmp_path, site, fake_time), said.append) is True
    text = "\n".join(said)
    assert "robots.txt: none (404)" in text
    assert "It is not saved." in text
    for shown in ("project: 2", "track: 2", "team: 2", "name: 2", "link: 2"):
        assert shown in text
    for hidden in (*PEOPLE, "Invented", "Payments", "dorahacks.io/buidl", CONTACT):
        assert hidden not in text
    assert f"Requests sent to {africa.SITE} so far: 2 of {africa.REQUEST_LIMIT}." in text
    assert site.urls == [africa.ROBOTS_URL, africa.PAGE]
    for request in site.seen:  # who asks, and how to reach the maintainer, in each request
        assert "TestTool/" in request.headers["User-Agent"]
        assert CONTACT in request.headers["User-Agent"]
    assert fake_time.sleeps  # a pause between the two requests
    assert not africa.paths(settings(tmp_path)).raw_dir.exists()


def test_a_refusal_stops_the_look_and_is_remembered(tmp_path: Path) -> None:
    site = answering(Reply(403, b"no"))
    said: list[str] = []
    assert africa.look(client(tmp_path, site, FakeTime()), said.append) is False
    assert any(line.startswith("STOPPED:") for line in said)
    with pytest.raises(CollectorRefused, match="refused a request"):
        client(tmp_path, answering(Reply(200, b"")), FakeTime())


def test_the_command_needs_the_word_look(capsys: pytest.CaptureFixture[str]) -> None:
    assert africa.main([]) == 2
    assert africa.USAGE in capsys.readouterr().out
