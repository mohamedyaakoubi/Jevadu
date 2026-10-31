"""Devfolio: every project that it ties to a Hedera prize track, at every event that had one
(design 5.6; the maintainer's yes of 31 October 2026, design rule 17).

    python -m hackathon_memory.collect.devfolio --plan     what the find and the read would ask
    python -m hackathon_memory.collect.devfolio --find     find the events and their projects
    python -m hackathon_memory.collect.devfolio --read [--pages N] [--wait]   each project once

Devfolio was not asked. Its terms (effective 29 December 2020, read on 31 October 2026) have no
clause on automated access, and the robots.txt of devfolio.co, of api.devfolio.co and of an
event's own address closes nothing (read the same day). The tool reads it the way of design 5.7
all the same (small_site.py): one request at a time with a pause, the name of the tool and the
maintainer's address in each request, a switch of its own, COLLECT_DEVFOLIO, read again before
every request, a count of requests on disk with a limit, and a refusal remembered until a person
decides.

How Devfolio answers, seen on 31 October 2026 (one visit of a gallery in a browser, then single
requests):

* The search of projects is a POST of JSON to api.devfolio.co/api/search/projects, a page at a
  time: {"hackathon_slugs": [...], "q": "...", "prize_tracks": [...], "from": 0, "size": 50}.
  With no event and the word "hedera", it searches every event of Devfolio. Each answer holds
  whole projects with their teams; the find keeps none of it but the name of each project, its
  event and the tracks of a Hedera sponsor that it entered.
* An event's gallery, https://<event>.devfolio.co/projects, carries in its page data the event's
  name and dates and every track with its sponsor. The find keeps those facts and no person: the
  same data names the judges.
* One project: GET api.devfolio.co/api/projects/<name>, in three parts: the project, its members
  and its event. The read saves the answer without its members (design rule 5).
* A prize of a Hedera track is not always filed under the sponsor Hedera: the first prizes of the
  three Hedera tracks of ETHDenver 2025 sit under "Organizer". So a prize belongs to the track
  whose name it carries, and the sponsor of that track decides (parse/devfolio_project.py).

The find meets an event through a project that writes the word "hedera" and entered a track of a
Hedera sponsor; then it reads every track of that event from the event's own data, and every
project of each Hedera track. An event whose Hedera tracks no such project entered is not met.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from hackathon_memory.collect import small_site
from hackathon_memory.collect.polite import (
    CollectorRefused,
    FetchFailed,
    PoliteClient,
    StopCollecting,
)
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.collect.robots import read_rules
from hackathon_memory.collect.small_site import SmallSite, count_line
from hackathon_memory.settings import Settings

SITE = "devfolio.co"
API = "api.devfolio.co"
SEARCH_URL = f"https://{API}/api/search/projects"
SUFFIX = ".json"
WORD = "hedera"  # the word that meets the events
HEDERA = re.compile(r"\b(hedera|hashgraph|hbar)\b", re.IGNORECASE)  # a sponsor of Hedera
PAGE_SIZE = 50  # projects in one page of the search
# Over all runs together. On 31 October 2026 the search for "hedera" found 1,276 projects of all
# Devfolio, 26 pages of 50; then one gallery for each event met and the pages of its Hedera
# tracks; then one request for each project. A limit of 1,000 leaves room for some hundreds of
# projects and a second find, and is not raised without a new decision.
REQUEST_LIMIT = 1000
SMALL_SITE = SmallSite(SITE, "collect_devfolio", REQUEST_LIMIT)
_PROJECT_PATH = re.compile(r"^/api/projects/[A-Za-z0-9-]{1,120}$")
_EVENT_HOST = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\.devfolio\.co$")
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>',
                        re.DOTALL)  # fmt: skip


def project_address(name: str) -> str:
    """Where the data service answers for one project."""
    return f"https://{API}/api/projects/{name}"


def project_page(name: str) -> str:
    """The project's own page, for a person: the address that a card links to."""
    return f"https://{SITE}/projects/{name}"


def page_of_address(url: str) -> str:
    """The project's own page, for the address of its answer in the data service."""
    return project_page(url.rstrip("/").rsplit("/", 1)[-1])


def gallery_address(subdomain: str) -> str:
    return f"https://{subdomain}.{SITE}/projects"


def allowed(url: str) -> bool:
    """Only the search, one project of the data service, an event's gallery, and robots.txt."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.port not in (None, 443) or parts.username or parts.password:
        return False
    if parts.query or parts.fragment:
        return False
    host = parts.hostname or ""
    if parts.path == "/robots.txt":
        return host in (SITE, API) or bool(_EVENT_HOST.match(host))
    if host == API:
        return parts.path == "/api/search/projects" or bool(_PROJECT_PATH.match(parts.path))
    return bool(_EVENT_HOST.match(host)) and host != f"www.{SITE}" and parts.path == "/projects"


class DevfolioClient(PoliteClient):
    """The polite client, asking for JSON first: the data service answers in it."""

    def _headers(self) -> dict[str, str]:
        return {**super()._headers(), "Accept": "application/json, text/html;q=0.9"}


def client_for(settings: Settings, **options: object) -> PoliteClient:
    return small_site.client_for(settings, SMALL_SITE, allow=allowed, client_class=DevfolioClient,
                                 **options)  # fmt: skip


# --------------------------------------------------------------------- what the find keeps


@dataclass(frozen=True)
class Track:
    uuid: str
    name: str
    sponsor: str  # the name that Devfolio gives the track's sponsor


@dataclass(frozen=True)
class Event:
    slug: str
    subdomain: str
    name: str
    starts_at: str | None  # as the event's data gives it, with its time zone
    ends_at: str | None
    tracks: tuple[Track, ...]  # every track of the event, with its sponsor

    @property
    def hedera_tracks(self) -> tuple[Track, ...]:
        return tuple(track for track in self.tracks if HEDERA.search(track.sponsor))

    @property
    def last_day(self) -> date | None:
        """The last day of the event, in UTC."""
        if not self.ends_at:
            return None
        return datetime.fromisoformat(self.ends_at).astimezone(UTC).date()


@dataclass(frozen=True)
class Found:
    found_at: str
    matches: int  # the projects of all Devfolio that the search for the word found
    events: dict[str, Event]  # by the event's short name
    projects: dict[str, str]  # each project's short name, and its event's
    tracks_of: dict[str, tuple[str, ...]]  # each project's Hedera tracks that it entered

    def ends(self) -> dict[str, date]:
        return {slug: event.last_day for slug, event in self.events.items() if event.last_day}


def found_path(settings: Settings) -> Path:
    return Path(settings.data_dir) / "found" / SITE / "found.json"


def raw_dir(settings: Settings) -> Path:
    return Path(settings.data_dir) / "raw" / SITE


def write_found(path: Path, found: Found) -> None:
    data = {
        "found_at": found.found_at,
        "matches": found.matches,
        "events": {slug: {"subdomain": event.subdomain, "name": event.name,
                          "starts_at": event.starts_at, "ends_at": event.ends_at,
                          "tracks": [[t.uuid, t.name, t.sponsor] for t in event.tracks]}
                   for slug, event in sorted(found.events.items())},
        "projects": {name: {"event": found.projects[name], "tracks": list(found.tracks_of[name])}
                     for name in sorted(found.projects)},
    }  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def read_found(path: Path) -> Found | None:
    """What the last find kept, or None when there was none."""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    events = {slug: Event(slug, event["subdomain"], event["name"], event["starts_at"],
                          event["ends_at"], tuple(Track(*track) for track in event["tracks"]))
              for slug, event in data["events"].items()}  # fmt: skip
    projects = {name: entry["event"] for name, entry in data["projects"].items()}
    tracks = {name: tuple(entry["tracks"]) for name, entry in data["projects"].items()}
    return Found(data["found_at"], data["matches"], events, projects, tracks)


# --------------------------------------------------------------------- the find


def _obey_robots(client: PoliteClient, host: str, page: str, say: Callable[[str], None]) -> None:
    rules, robots = read_rules(client, f"https://{host}/robots.txt", host)
    say(f"robots.txt of {host}: " + ("none (404)." if robots.status == 404 else "read, obeyed."))
    if not rules.allows(client.identity.name, page):
        raise StopCollecting(f"robots.txt of {host} does not allow this tool to read {page}")


def search(client: PoliteClient, *, events: Sequence[str], word: str = "",
           tracks: Sequence[str] = (),
           page_size: int = PAGE_SIZE) -> Iterator[dict]:  # fmt: skip
    """Each project that the search finds, page after page, as the data service gives it."""
    start, total = 0, None
    while total is None or start < total:
        body = {"hackathon_slugs": list(events), "q": word, "filter": "all", "prizes": [],
                "prize_tracks": list(tracks), "hashtags": [], "tracks": [], "category": [],
                "from": start, "size": page_size}  # fmt: skip
        answer = client.post_json(SEARCH_URL, body)
        if answer.status != 200:
            raise StopCollecting(f"the search of projects answered {answer.status}")
        try:
            hits = json.loads(answer.body.decode("utf-8"))["hits"]
            total, page = int(hits["total"]["value"]), list(hits["hits"])
        except (UnicodeDecodeError, ValueError, KeyError, TypeError):
            raise StopCollecting("the search of projects answered in an unknown shape") from None
        if not page:
            return
        for hit in page:
            source = hit.get("_source") if isinstance(hit, dict) else None
            if isinstance(source, dict):
                yield source
        start += len(page)


def _objects_with(value: object, key: str) -> Iterator[dict]:
    """Every object inside `value` that has `key`."""
    if isinstance(value, dict):
        if key in value:
            yield value
        for inner in value.values():
            yield from _objects_with(inner, key)
    elif isinstance(value, list):
        for inner in value:
            yield from _objects_with(inner, key)


def event_of(html: bytes, slug: str, subdomain: str) -> Event:
    """The facts of an event from its gallery's page data: its name, its dates, its tracks."""
    found = _NEXT_DATA.search(html.decode("utf-8", errors="replace"))
    if found is None:
        raise StopCollecting(f"the gallery of {slug} has no page data")
    data = json.loads(found.group(1))
    props = data.get("props", {}).get("pageProps", {})
    tracks: list[Track] = []
    for group in props.get("tracksWithSponsors") or []:
        sponsor = str((group.get("sponsor") or {}).get("name") or "")
        tracks.extend(Track(str(track["uuid"]), str(track.get("name") or ""), sponsor)
                      for track in group.get("tracks") or [] if track.get("uuid"))  # fmt: skip
    facts = next((one for one in _objects_with(props, "starts_at") if one.get("slug") == slug),
                 None)  # fmt: skip
    if facts is None:
        raise StopCollecting(f"the gallery of {slug} does not give the dates of the event")
    return Event(slug, subdomain, str(facts.get("name") or slug), facts.get("starts_at"),
                 facts.get("ends_at"), tuple(tracks))  # fmt: skip


def _of_hedera(track: object) -> bool:
    """A track of a sponsor of Hedera, as the search gives it."""
    sponsor = track.get("sponsor") if isinstance(track, dict) else None
    return isinstance(sponsor, dict) and bool(HEDERA.search(str(sponsor.get("name") or "")))


def find(client: PoliteClient, say: Callable[[str], None] = print, *,
         page_size: int = PAGE_SIZE) -> Found:  # fmt: skip
    """The events that had a track of a Hedera sponsor, and every project of those tracks."""
    _obey_robots(client, API, SEARCH_URL, say)
    met: dict[str, str] = {}  # event -> its subdomain
    matches = 0
    for source in search(client, events=[], word=WORD, page_size=page_size):
        matches += 1
        event = source.get("hackathon") or {}
        entered = [track for track in source.get("prize_tracks") or [] if _of_hedera(track)]
        if entered and event.get("slug"):
            met[str(event["slug"])] = str(event.get("subdomain") or event["slug"])
    say(f'The search for "{WORD}": {matches} projects of all Devfolio; {len(met)} events with '
        "a track of a Hedera sponsor among them.")  # fmt: skip
    events: dict[str, Event] = {}
    for slug, subdomain in sorted(met.items()):
        page = gallery_address(subdomain)
        _obey_robots(client, f"{subdomain}.{SITE}", page, say)
        answer = client.get(page)
        if answer.status != 200:
            raise StopCollecting(f"the gallery of {slug} answered {answer.status}")
        events[slug] = event_of(answer.body, slug, subdomain)
        say(f"{events[slug].name}: {len(events[slug].hedera_tracks)} Hedera tracks.")
    projects: dict[str, str] = {}
    tracks_of: dict[str, set[str]] = defaultdict(set)
    for slug, event in events.items():
        for track in event.hedera_tracks:
            count = 0
            for source in search(client, events=[slug], tracks=[track.uuid], page_size=page_size):
                name = str(source.get("slug") or "")
                if name:
                    projects[name] = slug
                    tracks_of[name].add(track.uuid)
                    count += 1
            say(f"  {track.name}: {count} projects.")
    return Found(client.now().strftime("%Y-%m-%dT%H:%M:%SZ"), matches, events, projects,
                 {name: tuple(sorted(tracks_of[name])) for name in projects})  # fmt: skip


# --------------------------------------------------------------------- the read


def cut_members(body: bytes) -> tuple[bytes, int]:
    """The answer for one project without its members, and how many were cut (design rule 5)."""
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("project"), dict):
        raise ValueError("the answer holds no project")
    members = data.pop("members", None) or []
    return json.dumps(data, ensure_ascii=False).encode("utf-8"), len(members)


@dataclass
class ReadRun:
    saved: int = 0
    saved_before: int = 0
    failed: int = 0
    left_for_later: int = 0
    members_cut: int = 0
    stopped: str | None = None


def read(client: PoliteClient, store: RawStore, found: Found, say: Callable[[str], None] = print,
         *, limit: int | None = None) -> ReadRun:  # fmt: skip
    """Each project of the find once, saved without its members. A project saved before is not
    asked for again; with `limit`, at most that many are asked for in this run."""
    run = ReadRun()
    collector = f"{client.identity.name}/{client.identity.version}"
    try:
        _obey_robots(client, API, project_address(next(iter(sorted(found.projects)), "x")), say)
        for name in sorted(found.projects):
            url = project_address(name)
            if store.load(url, SUFFIX) is not None:
                run.saved_before += 1
                continue
            if limit is not None and run.saved + run.failed >= limit:
                run.left_for_later += 1
                continue
            try:
                answer = client.get(url)
            except FetchFailed as error:
                run.failed += 1
                say(f"{name}: not read ({error}).")
                continue
            if answer.status != 200:
                run.failed += 1
                say(f"{name}: answered {answer.status}.")
                continue
            try:
                body, cut = cut_members(answer.body)
            except (UnicodeDecodeError, ValueError):
                run.failed += 1
                say(f"{name}: the answer is not a project.")
                continue
            store.save(answer, body, received=answer.body, collector=collector,
                       team_cut={"members_cut": cut}, suffix=SUFFIX)  # fmt: skip
            run.saved += 1
            run.members_cut += cut
    except StopCollecting as stop:
        run.stopped = str(stop)
        say(f"STOPPED: {stop}")
    finally:
        say(count_line(client))
    return run


# --------------------------------------------------------------------- the command


def plan(settings: Settings, say: Callable[[str], None] = print) -> None:
    """What the find and the read would ask, with no request."""
    say(f'The find: the search for "{WORD}" in every event ({SEARCH_URL}, {PAGE_SIZE} projects '
        "a page), the gallery of each event met that had a track of a Hedera sponsor, and the "
        "pages of the search of each of those tracks.")  # fmt: skip
    found = read_found(found_path(settings))
    if found is None:
        say("No find yet: the read has nothing to read.")
        return
    saved = sum(RawStore(raw_dir(settings)).has(project_address(name), SUFFIX)
                for name in found.projects)  # fmt: skip
    say(f"The last find ({found.found_at}): {len(found.events)} events, {len(found.projects)} "
        f"projects, {saved} of them saved. The read asks for the {len(found.projects) - saved} "
        "others, one request each.")  # fmt: skip
    for event in found.events.values():
        tracks = ", ".join(track.name for track in event.hedera_tracks)
        say(f"  {event.name} ({event.starts_at} to {event.ends_at}): {tracks}")


def main(argv: list[str], say: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(prog="python -m hackathon_memory.collect.devfolio")
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--plan", action="store_true")
    what.add_argument("--find", action="store_true")
    what.add_argument("--read", action="store_true")
    parser.add_argument("--pages", type=int)
    parser.add_argument("--wait", action="store_true")
    arguments = parser.parse_args(argv)
    settings = Settings()
    if arguments.plan:
        plan(settings, say)
        return 0
    try:
        client = client_for(settings, wait_for_cooldown=arguments.wait)
    except CollectorRefused as refusal:
        say(f"Refused: {refusal}")
        return 1
    if arguments.find:
        try:
            found = find(client, say)
        except StopCollecting as stop:
            say(f"STOPPED: {stop}. Nothing of this find was kept.")
            say(count_line(client))
            return 2
        write_found(found_path(settings), found)
        say(f"Kept: {len(found.events)} events, {len(found.projects)} projects "
            f"({found_path(settings)}).")  # fmt: skip
        say(count_line(client))
        return 0
    found = read_found(found_path(settings))
    if found is None:
        say("No find yet: run --find first.")
        return 2
    done = read(client, RawStore(raw_dir(settings)), found, say, limit=arguments.pages)
    say(f"Saved now: {done.saved} (members cut: {done.members_cut}); saved before: "
        f"{done.saved_before}; failed: {done.failed}; left for a later run: "
        f"{done.left_for_later}.")  # fmt: skip
    return 0 if done.stopped is None else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
