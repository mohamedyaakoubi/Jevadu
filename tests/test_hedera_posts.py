"""The small collector of Hedera's winner posts, against a fake site. Every page is invented."""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from fakes import FakeSite, FakeTime, Reply, session_for
from hackathon_memory.collect import hedera_posts as posts
from hackathon_memory.collect.polite import CollectorRefused
from hackathon_memory.settings import Settings

CONTACT = "tests@example.org"
FIRST = next(iter(posts.POSTS.values()))
ROBOTS = "https://hedera.com/robots.txt"
POST = (
    b"<html><head><title>Invented winners</title></head><body><article>"
    b"<h1>The winners</h1><h3>Invented Pay</h3><p>Pays shops with a coin.</p>"
    b"<p><strong>Team:</strong> Quillfeather, Ledgerwood</p>"
    b"<h3>Invented Post</h3><p>Moves parcels.</p><p>Built by - Orchardson</p>"
    b"</article></body></html>"
)


def settings(tmp_path: Path, *, switch: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=str(tmp_path / "data"),
        collector_name="TestTool",
        collector_contact_email=CONTACT,
        collect_hedera_posts=switch,
    )


def client(tmp_path: Path, site: FakeSite):
    env = tmp_path / ".env"
    env.write_text("COLLECT_HEDERA_POSTS=on\n", encoding="utf-8")
    fake_time = FakeTime()
    return posts.client_for(settings(tmp_path), env_file=env, session=session_for(site),
                            sleep=fake_time.sleep, clock=fake_time.clock)  # fmt: skip


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        (FIRST, True),
        (FIRST + "/", True),
        (FIRST.replace("https://hedera.com", "https://www.hedera.com"), True),
        (ROBOTS, True),
        ("https://hedera.com/blog/another-post", False),
        (FIRST + "?page=2", False),
        (FIRST.replace("https://", "http://"), False),
        ("https://hedera.com.example.test/blog/hedera20-hackathon-winners", False),
    ],
)
def test_only_robots_and_the_nine_posts_may_be_read(url: str, allowed: bool) -> None:
    assert posts.is_allowed_url(url) is allowed


def test_there_are_nine_posts() -> None:
    assert len(posts.POSTS) == 9
    assert all(posts.is_allowed_url(url) for url in posts.POSTS.values())


def test_nothing_is_sent_while_the_switch_is_off(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="COLLECT_HEDERA_POSTS=on"):
        posts.client_for(settings(tmp_path, switch=False))


def test_the_people_lines_are_found_and_counted_but_not_shown(tmp_path: Path) -> None:
    site = FakeSite({ROBOTS: Reply(404, b"not here"), FIRST: Reply(200, POST)})
    said: list[str] = []
    assert posts.look(client(tmp_path, site), said.append) is True
    text = "\n".join(said)
    assert "Lines that start like a list of people: 2 (team: 1, built by: 1)" in text
    assert "It is not saved." in text
    for hidden in ("Quillfeather", "Ledgerwood", "Orchardson", "Invented", CONTACT):
        assert hidden not in text
    assert site.urls == [ROBOTS, FIRST]
    assert not (tmp_path / "data" / "raw").exists()


def test_a_people_line_is_the_whole_line_with_the_names() -> None:
    lines = posts.people_lines(BeautifulSoup(POST, "lxml"))
    assert [line.name for line in lines] == ["p", "p"]  # not the <strong> that holds "Team:"
    assert "Quillfeather" in lines[0].get_text() and "Orchardson" in lines[1].get_text()


def test_a_move_to_www_is_followed(tmp_path: Path) -> None:
    www = FIRST.replace("https://hedera.com", "https://www.hedera.com")
    site = FakeSite({ROBOTS: Reply(404, b""), FIRST: Reply(301, b"", {"Location": www}),
                     www: Reply(200, POST)})  # fmt: skip
    said: list[str] = []
    assert posts.look(client(tmp_path, site), said.append) is True
    assert "final address on www.hedera.com" in "\n".join(said)


def test_a_refusal_stops_at_once_and_is_remembered(tmp_path: Path) -> None:
    site = FakeSite({ROBOTS: Reply(403, b"no")})
    said: list[str] = []
    assert posts.look(client(tmp_path, site), said.append) is False
    assert site.urls == [ROBOTS]  # the first request was refused: nothing more is tried
    with pytest.raises(CollectorRefused, match="refused a request"):
        client(tmp_path, site)


def test_the_command_needs_the_word_look(capsys: pytest.CaptureFixture[str]) -> None:
    assert posts.main([]) == 2
    assert posts.USAGE in capsys.readouterr().out
