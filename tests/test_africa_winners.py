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


def test_the_command_needs_look_or_read(capsys: pytest.CaptureFixture[str]) -> None:
    assert africa.main([]) == 2
    assert africa.main(["--look", "--read"]) == 2
    assert africa.USAGE in capsys.readouterr().out


# --------------------------------------------------------------------- the read

STATIC = f"https://{africa.SITE}/_next/static/chunks"
NO_DATA = "self.webpackChunk=[];function a(){return 1}"
WINNERS = (
    'const w=[{name:"Invented Pay",track:"cross",place:"1st",about:"Pays shops.",'
    'link:"https://dorahacks.io/buidl/1",team:["Quillfeather","Ledgerwood"],'
    'contact:"quill@example.org",logo:"/logos/pay@2x.png"},'
    '{name:"Invented Post",track:"cross",place:"2nd",about:"Moves parcels.",'
    'link:"https://dorahacks.io/buidl/2"},'
    "{name:'Invented Vote',track:'ai',place:'1st',about:'Counts ballots.',"
    "link:'https://dorahacks.io/buidl/3',members:[{name:'Orchardson'}]}];export default w;"
)


def page_with_scripts() -> bytes:
    """Two winner cards, the script tags of a Next.js page, and its data that names one script."""
    pushed = json.dumps('2:I[77,["static/chunks/bbb.js"],"default"]\n')
    return (
        "<html><head>"
        '<script src="/_next/static/chunks/aaa.js?dpl=x" async></script>'
        '<script src="/_next/static/chunks/bbb.js?dpl=x" async></script>'
        '<script src="/_next/static/chunks/ccc.js?dpl=x" async></script>'
        '<script src="/_next/static/chunks/polyfills.js" nomodule></script>'
        '<script src="https://cdn.example.test/x.js"></script>'
        "</head><body><section id='winners'>"
        '<a class="winner-card" href="https://dorahacks.io/buidl/1"><h3>Invented Pay</h3></a>'
        '<a class="winner-card" href="https://dorahacks.io/buidl/2"><h3>Invented Post</h3></a>'
        f"</section><script>self.__next_f.push([1,{pushed}])</script></body></html>"
    ).encode()


def site_with(page: bytes, scripts: dict[str, str]) -> FakeSite:
    pages: dict = {africa.ROBOTS_URL: Reply(404, b"not here"), africa.PAGE: Reply(200, page)}
    for url, text in scripts.items():
        pages[url] = Reply(200, text.encode(), {"Content-Type": "application/javascript"})
    return FakeSite(pages)


def read(tmp_path: Path, site: FakeSite, said: list[str]) -> africa.Read | None:
    allowed = africa.AllowedUrls()
    collector = africa.client_for(
        settings(tmp_path), env_file=env_file(tmp_path), allow=allowed,
        session=session_for(site), sleep=FakeTime().sleep, clock=FakeTime().clock,
    )  # fmt: skip
    store = africa.RawStore(africa.paths(settings(tmp_path)).raw_dir)
    return africa.read_and_save(collector, allowed, store, said.append)


def test_the_script_files_are_the_page_s_own_and_the_named_ones_come_first() -> None:
    assert africa.script_sources(page_with_scripts()) == [
        f"{STATIC}/bbb.js",  # named by the data of the page; its tag (with "?dpl=x") is the same
        f"{STATIC}/aaa.js?dpl=x",
        f"{STATIC}/ccc.js?dpl=x",
    ]  # no script for old browsers, nothing from another site


def test_the_read_stops_at_the_winners_and_saves_them_without_people(tmp_path: Path) -> None:
    site = site_with(page_with_scripts(), {f"{STATIC}/bbb.js": WINNERS,
                                           f"{STATIC}/aaa.js?dpl=x": NO_DATA})  # fmt: skip
    said: list[str] = []
    done = read(tmp_path, site, said)
    assert done is not None and done.winners == 3
    assert site.urls == [africa.ROBOTS_URL, africa.PAGE, f"{STATIC}/bbb.js"]  # then it stopped
    saved = done.script.body_path.read_text(encoding="utf-8")
    for kept in ("Invented Pay", "Invented Vote", "https://dorahacks.io/buidl/3", "pay@2x.png"):
        assert kept in saved
    for person in (*PEOPLE, "Orchardson", "quill@example.org"):
        assert person not in saved
    assert dict(done.cut) == {"team": 1, "members": 1, "address": 1}
    assert done.script.meta["team_cut"] == {"people_values_cut": dict(done.cut)}
    assert done.page.body_path.read_bytes() == page_with_scripts()  # the page, as received
    text = "\n".join(said)
    assert "name: 3" in text and "link: 3" in text
    for hidden in ("Invented", "Quillfeather", "dorahacks.io/buidl", CONTACT):
        assert hidden not in text


def test_no_script_with_the_winners_saves_nothing(tmp_path: Path) -> None:
    scripts = {f"{STATIC}/bbb.js": NO_DATA, f"{STATIC}/aaa.js?dpl=x": NO_DATA,
               f"{STATIC}/ccc.js?dpl=x": 'x="https://dorahacks.io/buidl/1"'}  # fmt: skip
    site = site_with(page_with_scripts(), scripts)
    said: list[str] = []
    assert read(tmp_path, site, said) is None
    assert len(site.urls) == 5  # robots.txt, the page, and each of the three files once
    assert any("none of the 3 script files holds the winners" in line for line in said)
    assert not africa.paths(settings(tmp_path)).raw_dir.exists()


def test_a_page_with_a_block_about_members_is_not_saved(tmp_path: Path) -> None:
    page = page_with_scripts().replace(b"<section id='winners'>", b"<section class='team-list'>")
    site = site_with(page, {f"{STATIC}/bbb.js": WINNERS})
    said: list[str] = []
    assert read(tmp_path, site, said) is None
    assert site.urls == [africa.ROBOTS_URL, africa.PAGE]  # no script file was asked for
    assert not africa.paths(settings(tmp_path)).raw_dir.exists()


def test_a_saved_page_is_never_asked_for_again(tmp_path: Path) -> None:
    site = site_with(page_with_scripts(), {f"{STATIC}/bbb.js": WINNERS})
    assert read(tmp_path, site, []) is not None
    again = site_with(page_with_scripts(), {f"{STATIC}/bbb.js": WINNERS})
    said: list[str] = []
    assert read(tmp_path, again, said) is None
    assert again.urls == []
    assert "never asked for twice" in said[0]


def test_only_literal_values_of_keys_about_people_are_cut() -> None:
    text = (
        'a={team:["Ann"],"members":[{name:"Bo"}],founder:"Cy",author:e.name,'
        'name:"Kept",photo:"",x:"mail@example.org",y:"icon@2x.png"}'
    )
    cut, counts = africa.cut_people(text)
    assert cut == (
        'a={team:[],"members":[],founder:"",author:e.name,'
        'name:"Kept",photo:"",x:"address-cut",y:"icon@2x.png"}'
    )
    assert dict(counts) == {"team": 1, "members": 1, "founder": 1, "address": 1}
