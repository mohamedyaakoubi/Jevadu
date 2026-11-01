"""An invented Devfolio, in the shape that the real one answered on 31 October 2026: the search of
projects (a POST of JSON), an event's gallery with its page data, and one project of the data
service. Every name, text and number here is invented."""

from __future__ import annotations

import json
from pathlib import Path

from fakes import FakeSite, FakeTime, Reply, session_for
from hackathon_memory.collect.devfolio import (
    SEARCH_URL,
    SITE,
    DevfolioClient,
    allowed,
    gallery_address,
    project_address,
)
from hackathon_memory.collect.polite import CollectorIdentity, RequestCount

EVENT = "sample-hack"
OTHER_EVENT = "other-hack"
HEDERA_TRACK, EXPLORER_TRACK, ZERO_TRACK = "h1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "h2bb", "z1cc"
STARTS, ENDS = "2025-02-23T17:00:00+00:00", "2025-03-01T17:30:00+00:00"
ROBOTS = Reply(200, b"User-agent: *\nDisallow:\n", {"Content-Type": "text/plain"})
JSON = {"Content-Type": "application/json"}
PERSON = {"first_name": "Invented", "last_name": "Person", "username": "invented_person",
          "profile_image": "https://img.example.test/p.png"}  # fmt: skip


def track(uuid: str, name: str, sponsor: str) -> dict:
    return {"uuid": uuid, "name": name, "description": "The event's words.",
            "sponsor": {"name": sponsor, "uuid": sponsor.lower()}}  # fmt: skip


def hit(name: str, event: str, tracks: list[dict]) -> dict:
    """One project of the search, with its team, as the search gives it."""
    return {"_source": {"slug": name, "name": name.title(), "members": [PERSON],
                        "hackathon": {"slug": event, "subdomain": event, "name": event.title()},
                        "prize_tracks": tracks}}  # fmt: skip


# The word "hedera" meets: a project of a Hedera track, a project of another event with no
# Hedera track, and a project that only writes the word.
WORD_HITS = [
    hit("pebble-pay-a1", EVENT, [track(HEDERA_TRACK, "Hedera Builder", "Hedera"),
                                 track(ZERO_TRACK, "Zero Track", "Zeroth")]),
    hit("cedar-b2", OTHER_EVENT, [track("o9", "Other Track", "Otherco")]),
    hit("fern-c3", EVENT, []),
]  # fmt: skip
TRACK_HITS = {
    HEDERA_TRACK: [hit("pebble-pay-a1", EVENT, []), hit("quartz-d4", EVENT, [])],
    EXPLORER_TRACK: [hit("willow-e5", EVENT, [])],  # a Hedera track that no word met
}


def searched(request) -> Reply:  # noqa: ANN001
    """The search: the projects that the body asks for, a page at a time."""
    body = json.loads(request.body)
    if body["hackathon_slugs"] == [] and body["q"] == "hedera":
        found = WORD_HITS
    elif body["hackathon_slugs"] == [EVENT] and len(body["prize_tracks"]) == 1:
        found = TRACK_HITS.get(body["prize_tracks"][0], [])
    else:
        found = []
    page = found[body["from"] : body["from"] + body["size"]]
    answer = {"hits": {"total": {"value": len(found)}, "hits": page}}
    return Reply(200, json.dumps(answer).encode(), {"Content-Type": "application/json"})


def gallery() -> bytes:
    """The gallery of the invented event, with its page data: tracks, sponsors, dates, judges."""
    hedera = [{"uuid": HEDERA_TRACK, "name": "Hedera Builder"},
              {"uuid": EXPLORER_TRACK, "name": "Hedera Explorer"}]  # fmt: skip
    facts = {"slug": EVENT, "name": "Sample Hack 2025", "starts_at": STARTS, "ends_at": ENDS,
             "judges": [{"first_name": "Invented Judge"}]}  # fmt: skip
    header = {"queryKey": ["hackathonMicrositeHeader", EVENT],
              "state": {"data": [{"hackathons": [facts]}]}}  # fmt: skip
    props = {
        "tracksWithSponsors": [
            {"sponsor": {"name": "Hedera"}, "tracks": hedera},
            {"sponsor": {"name": "Zeroth"}, "tracks": [{"uuid": ZERO_TRACK, "name": "Zero Track"}]},
        ],
        "dehydratedState": {"queries": [header]},
    }
    data = {"props": {"pageProps": props}}
    script = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    return f"<html><body><h1>Projects</h1>{script}</body></html>".encode()


def project_answer(name: str) -> bytes:
    """One project of the data service, in its three parts."""
    project = {"slug": name, "name": name.title(), "tagline": "A made-up project.",
               "description": [], "links": "", "video_url": "", "prizes": [],
               "prize_tracks": [], "hashtags": []}  # fmt: skip
    event = {"name": "Sample Hack 2025", "slug": EVENT}
    return json.dumps(
        {"project": project, "members": [PERSON, PERSON], "hackathon": event}
    ).encode()


def devfolio(tmp_path: Path, extra: dict | None = None) -> tuple[DevfolioClient, FakeSite]:
    """The polite client of Devfolio, with its real rules, over the invented site."""
    pages: dict = {
        f"https://api.{SITE}/robots.txt": ROBOTS,
        f"https://{EVENT}.{SITE}/robots.txt": ROBOTS,
        SEARCH_URL: searched,
        gallery_address(EVENT): Reply(200, gallery(), {"Content-Type": "text/html"}),
        **{project_address(name): Reply(200, project_answer(name), JSON)
           for name in ("pebble-pay-a1", "quartz-d4", "willow-e5")},
        **(extra or {}),
    }  # fmt: skip
    site = FakeSite(pages)
    clock = FakeTime()
    client = DevfolioClient(
        site=SITE,
        identity=CollectorIdentity(name="TestTool-research", contact="owner@example.test"),
        allow=allowed,
        is_enabled=lambda: True,
        session=session_for(site),
        count=RequestCount(tmp_path / "count.json", SITE, limit=200),
        clock=clock.clock,
        sleep=clock.sleep,
    )
    return client, site
