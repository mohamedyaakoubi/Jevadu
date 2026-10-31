"""The collector of Devfolio (collect/devfolio.py) on an invented Devfolio: the addresses it may
ask for, the find of the events that had a Hedera track and of every project of those tracks, and
the read of each project once, saved without its members. No request leaves the test."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from devfolio_fakes import (
    ENDS,
    EVENT,
    EXPLORER_TRACK,
    HEDERA_TRACK,
    STARTS,
    devfolio,
)

from fakes import Reply
from hackathon_memory.collect.devfolio import (
    SEARCH_URL,
    SUFFIX,
    allowed,
    find,
    project_address,
    read,
    read_found,
    write_found,
)
from hackathon_memory.collect.rawstore import RawStore


def quiet(_: str) -> None:
    return None


def test_only_the_search_a_project_a_gallery_and_robots_may_be_asked() -> None:
    event = "https://sample-hack.devfolio.co"
    for url in (SEARCH_URL, project_address("pebble-pay-a1"), f"{event}/projects",
                "https://api.devfolio.co/robots.txt", f"{event}/robots.txt"):  # fmt: skip
        assert allowed(url), url
    for url in ("http://api.devfolio.co/api/search/projects", f"{SEARCH_URL}?q=x",
                "https://api.devfolio.co/api/users/someone", "https://devfolio.co/projects/x",
                "https://www.devfolio.co/projects", "https://sample-hack.devfolio.co/projects/x",
                "https://evil.example.test/projects", "https://api.devfolio.co/api/projects/../x",
                "https://user:pass@api.devfolio.co/api/search/projects"):  # fmt: skip
        assert not allowed(url), url


def test_the_find_meets_the_events_of_a_hedera_track_and_lists_every_project(
    tmp_path: Path,
) -> None:
    """The word meets the event through a project of its Hedera track; the event's own data gives
    its second Hedera track, which no project with the word entered; each track is listed whole.
    A project that only writes the word is not taken, nor an event with no Hedera track."""
    client, site = devfolio(tmp_path)
    found = find(client, quiet, page_size=2)
    assert found.matches == 3 and list(found.events) == [EVENT]
    event = found.events[EVENT]
    assert (event.name, event.starts_at, event.ends_at) == ("Sample Hack 2025", STARTS, ENDS)
    assert [track.name for track in event.hedera_tracks] == ["Hedera Builder", "Hedera Explorer"]
    assert found.projects == {"pebble-pay-a1": EVENT, "quartz-d4": EVENT, "willow-e5": EVENT}
    assert found.tracks_of["willow-e5"] == (EXPLORER_TRACK,)
    assert found.tracks_of["pebble-pay-a1"] == (HEDERA_TRACK,)
    posts = [json.loads(request.body) for request in site.seen if request.method == "POST"]
    assert [post["from"] for post in posts if post["q"] == "hedera"] == [0, 2]  # two pages of 2
    for request in site.seen:
        assert "TestTool-research" in request.headers["User-Agent"]
        assert request.headers["From"] == "owner@example.test"
    path = tmp_path / "found" / "found.json"
    write_found(path, found)
    kept = path.read_text(encoding="utf-8")
    assert "Invented" not in kept and "judge" not in kept.lower()  # no person, no text of a page
    assert read_found(path) == found and found.ends() == {EVENT: date(2025, 3, 1)}


def test_the_read_saves_each_project_once_without_its_members(tmp_path: Path) -> None:
    client, site = devfolio(tmp_path, {project_address("quartz-d4"): Reply(404, b"{}")})
    found = find(client, quiet, page_size=2)
    store = RawStore(tmp_path / "raw")
    done = read(client, store, found, quiet)
    assert (done.saved, done.failed, done.members_cut) == (2, 1, 4)
    for name in ("pebble-pay-a1", "willow-e5"):
        saved = store.load(project_address(name), SUFFIX)
        body = saved.read().decode("utf-8")
        assert "members" not in json.loads(body) and "Invented" not in body
        assert saved.meta["team_cut"] == {"members_cut": 2}
    asked = len(site.seen)
    again = read(client, store, found, quiet, limit=5)
    assert again.saved_before == 2 and again.failed == 1  # only the missing one is asked again
    assert len(site.seen) == asked + 2  # robots.txt, and the one that failed


def test_a_refusal_stops_the_read_and_is_remembered(tmp_path: Path) -> None:
    client, _ = devfolio(tmp_path, {project_address("pebble-pay-a1"): Reply(403, b"no")})
    found = find(client, quiet, page_size=2)
    done = read(client, RawStore(tmp_path / "raw"), found, quiet)
    assert done.stopped and "says no" in done.stopped and done.saved == 0
    assert client.count.refusal() is not None  # every later command sees it
