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


@pytest.mark.parametrize(
    "label",
    ["Team Member:", "Team members –", "Team lead:", "Led by:", "Co-founder -", "Members:"],
)
def test_every_label_of_a_list_of_people_is_known(label: str) -> None:
    html = f"<p>{label} Quillfeather</p><ul><li><strong>{label}</strong> Quillfeather</li></ul>"
    lines = posts.people_lines(BeautifulSoup(html, "lxml"))
    assert [line.name for line in lines] == ["p", "li"]  # the whole lines, with the name


def test_the_signature_under_a_quote_is_a_line_about_people() -> None:
    soup = BeautifulSoup(
        "<p>What did you build?</p><p>An invented wallet.</p><p>— Quill Feather</p>"
        "<p>– Ann van Ledgerwood</p><p>— Prize: $5,000</p><p>- a list item</p>",
        "lxml",
    )
    lines = posts.people_lines(soup)
    assert [line.get_text() for line in lines] == ["— Quill Feather", "– Ann van Ledgerwood"]
    assert {posts._kind(line) for line in lines} == {"signature"}


def test_a_line_that_only_mentions_a_team_is_not_a_list_of_people() -> None:
    soup = BeautifulSoup("<p>The team built a wallet.</p><p>Teams: see the rules.</p>", "lxml")
    assert posts.people_lines(soup) == []


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


def test_the_command_needs_look_or_read(capsys: pytest.CaptureFixture[str]) -> None:
    assert posts.main([]) == 2
    assert posts.main(["--look", "--read"]) == 2
    assert posts.USAGE in capsys.readouterr().out


# --------------------------------------------------------------------- the read

WITH_AUTHOR = POST.replace(
    b"<head>",
    b'<head><meta name="author" content="Invented Writer">'
    b'<script type="application/ld+json">{"@context":"https://schema.org","@graph":['
    b'{"@type":"Article","headline":"Invented winners"},'
    b'{"@type":"Person","name":"Invented Writer"}]}</script>',
)


def all_posts(**instead: Reply) -> FakeSite:
    """robots.txt (none) and the nine posts, each with a team line and an author."""
    pages: dict = {ROBOTS: Reply(404, b"")}
    for event, url in posts.POSTS.items():
        pages[url] = instead.get(event, Reply(200, WITH_AUTHOR, {"Content-Type": "text/html"}))
    return FakeSite(pages)


def read(tmp_path: Path, site: FakeSite, said: list[str]) -> list | None:
    store = posts.RawStore(posts.raw_dir(settings(tmp_path)))
    return posts.read_and_save(client(tmp_path, site), store, said.append)


def test_the_read_saves_each_post_once_without_the_people(tmp_path: Path) -> None:
    site = all_posts()
    said: list[str] = []
    saved = read(tmp_path, site, said)
    assert saved is not None and len(saved) == 9
    assert site.urls == [ROBOTS, *posts.POSTS.values()]
    body = saved[0].body_path.read_text(encoding="utf-8")
    assert "Invented Pay" in body and '"@type": "Article"' in body
    for person in ("Quillfeather", "Ledgerwood", "Orchardson", "Invented Writer"):
        assert person not in body
    assert saved[0].meta["team_cut"] == {"people_cut": {"author": 2, "team": 1, "built by": 1}}
    assert "Hedera20: saved, " in said[1] and "cut out: author: 2, team: 1, built by: 1" in said[1]


def test_a_post_with_nothing_to_cut_is_saved_as_received() -> None:
    plain = b"<html><body><h3>Invented Pay</h3><p>Pays shops.</p></body></html>"
    assert posts.cut_people(plain) == (plain, {})


def test_a_saved_post_is_never_asked_for_again(tmp_path: Path) -> None:
    assert read(tmp_path, all_posts(), []) is not None
    again = all_posts()
    said: list[str] = []
    assert read(tmp_path, again, said) == []
    assert again.urls == [ROBOTS]
    assert sum("not asked for again" in line for line in said) == 9


def test_a_refusal_stops_the_read_and_the_rest_is_not_asked(tmp_path: Path) -> None:
    site = all_posts(Hedera22=Reply(403, b"no"))
    said: list[str] = []
    assert read(tmp_path, site, said) is None
    assert site.urls == [ROBOTS, *list(posts.POSTS.values())[:3]]
    assert any("Posts saved before the stop: 2" in line for line in said)
