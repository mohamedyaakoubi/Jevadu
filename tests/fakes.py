"""Stand-ins for a website and for the clock, so the collector is tested without a network.

Nothing here touches the internet. FakeSite answers requests from a dictionary, and records every
request it gets: the address, the headers and the order. FakeTime replaces sleeping, so the test
of the two-second pause takes no time.
"""

from __future__ import annotations

import io
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path

import requests
from requests.adapters import BaseAdapter

SAMPLES = Path(__file__).resolve().parent / "samples" / "ethglobal"


def sample(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


@dataclass
class Reply:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


class FakeTime:
    """A clock that moves only when someone sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeSite(BaseAdapter):
    """Plugs into a requests.Session in place of the network."""

    def __init__(
        self,
        pages: dict[str, Reply | list[Reply]] | None = None,
        during_request: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.pages = pages or {}
        self.seen: list[requests.PreparedRequest] = []
        self._during_request = during_request
        self._lock = threading.Lock()
        self._active = 0
        self.most_at_once = 0

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):  # noqa: ANN001, ARG002
        with self._lock:
            self.seen.append(request)
            self._active += 1
            self.most_at_once = max(self.most_at_once, self._active)
        try:
            if self._during_request:
                self._during_request()
            reply = self.pages.get(request.url, Reply(status=404, body=b"not here"))
            if isinstance(reply, list):  # one answer for each visit, the last one for ever
                reply = reply.pop(0) if len(reply) > 1 else reply[0]
            response = requests.Response()
            response.status_code = reply.status
            response._content = reply.body
            response._content_consumed = True
            response.headers.update(reply.headers)
            response.url = request.url
            response.request = request
            response.raw = io.BytesIO(reply.body)
            return response
        finally:
            with self._lock:
                self._active -= 1

    def close(self) -> None:
        pass

    @property
    def urls(self) -> list[str]:
        return [str(r.url) for r in self.seen]


def session_for(site: FakeSite) -> requests.Session:
    session = requests.Session()
    session.mount("https://", site)
    session.mount("http://", site)
    return session


# ------------------------------------------------------------------ an invented showcase list

LIST = "https://ethglobal.com/showcase?partners=hedera"
HEDERA_ID = "hed01"  # an invented id for the sponsor Hedera
OTHER_ID = "oth02"  # an invented id for another sponsor
EVENT = "ETHGlobal Sample Event"


def listed(
    name: str, short_id: str, *sponsors: str, event: str = EVENT, short_line: str | None = None
) -> dict:
    """One INVENTED record of the list, with the keys that a real record has."""
    return {
        "uuid": short_id,
        "slug": name,
        "name": name.replace("-", " ").title(),
        "tagline": short_line or f"An invented short line about {name}.",
        "event": {"name": event},
        "banner": {"file": {"fullUrl": f"https://cdn.example.test/banners/{name}.png"}},
        "prizes": [
            {
                "prize": {
                    "sponsor": {
                        "organization": {
                            "uuid": sponsor,
                            "squareLogo": {
                                "fullUrl": f"https://cdn.example.test/logos/{sponsor}.png"
                            },
                        }
                    }
                }
            }
            for sponsor in sponsors
        ],
        "meta": {"tmpVideoId": 12345, "demoVideoReady": True},
    }


def list_page(
    number: int,
    records: list[dict],
    *,
    has_next: bool,
    cards: list[dict] | None = None,
    data: dict | None = None,
) -> bytes:
    """An INVENTED page of the showcase list, in the shape of the real ones.

    The cards are links to the project pages. The data of the page is one object in a row of
    text, pushed by two scripts: the row is cut in the middle, as a real page cuts it. `cards`
    and `data` let a test build a page whose cards and data do not fit.
    """
    payload = (
        data
        if data is not None
        else {
            "currentPage": number,
            "events": [{"id": 7, "name": EVENT, "slug": "sample-event", "type": "hackathon"}],
            "projects": records,
        }
    )
    row = f'2a:["$","$L2b",null,{json.dumps(payload, separators=(",", ":"))}]\n'
    cut = len(row) // 2
    pushes = [
        '1:"$Sreact.fragment"\n',
        '1b:T1c,a text row with a } and a "\n',
        row[:cut],
        row[cut:],
        '2c:T1c,a text row with a { and a "\n',
    ]
    scripts = "\n".join(
        f"<script>self.__next_f.push([1,{json.dumps(text)}])</script>" for text in pushes
    )
    links = "\n".join(
        f'<a href="/showcase/{r["slug"]}-{r["uuid"]}"><div class="card"><h2>{r["name"]}</h2>'
        f'<p>{r["tagline"]}</p><div class="rounded-full">{r["event"]["name"]}</div></div></a>'
        for r in (cards if cards is not None else records)
    )
    paging = ""
    if number > 1:
        paging += f'<a href="/showcase?partners=hedera&amp;page={number - 1}">Previous</a>'
    if has_next:
        paging += f'<a href="/showcase?partners=hedera&amp;page={number + 1}">Next</a>'
    return (
        "<!doctype html>\n"
        "<!-- INVENTED SAMPLE. Not taken from any real page. Every word in it is made up. -->\n"
        '<html lang="en"><head><meta charset="utf-8"><title>Showcase | ETHGlobal</title></head>\n'
        '<body><nav><a href="/">Home</a> <a href="/events">Events</a> '
        '<a href="/showcase">Showcase</a></nav>\n'
        f'<main>{links}\n<div class="paging">{paging}</div></main>\n'
        "<script>self.__next_f=self.__next_f||[];self.__next_f.push([0])</script>\n"
        f"{scripts}\n</body></html>\n"
    ).encode()


def list_reply(number: int, records: list[dict], *, has_next: bool) -> Reply:
    return Reply(
        200,
        list_page(number, records, has_next=has_next),
        {"Content-Type": "text/html; charset=utf-8"},
    )


# ------------------------------------------------------------------ an invented project page

PROJECT_PAGE = "https://ethglobal.com/showcase/pebble-pay-x1y2z"
# The scores that the site computes are planted with loud values. No test may ever see them come
# out of the parser (design rule 1).
PLANTED_SCORES = {
    "autoOriginality": 987654321,
    "autoPracticality": 876543219,
    "autoTechnicality": 765432198,
    "autoSummary": "A PLANTED SUMMARY OF THE SITE THAT MUST NEVER COME OUT",
}
_BETWEEN = "<!-- --> <!-- -->"  # what React writes between two pieces of text


def won(
    sponsor: str = "Hedera",
    sponsor_id: str = HEDERA_ID,
    *,
    track: str = "AI, Agents & Hedera Services",
    award: str | None = None,
    kind: str = "tier",
    pool: bool = False,
) -> dict:
    """One INVENTED prize of a project, with the keys that a real page has in its data.

    A prize of the kind "tier" has a place. For any other kind the award is the name of the
    prize once more, unless the test gives another one.
    """
    return {
        "uuid": f"{sponsor_id}-{kind}",
        "name": award if award is not None else ("1st place" if kind == "tier" else track),
        "poolPrize": pool,
        "prize": {
            "name": track,
            "type": kind,
            "sponsor": {
                "name": sponsor,
                "organization": {
                    "uuid": sponsor_id,
                    "name": sponsor,
                    "squareLogo": {"fullUrl": f"https://cdn.example.test/logos/{sponsor_id}.png"},
                },
            },
        },
    }


def shown_prize(prize: dict) -> str:
    """The line that a real page shows for a prize: a tier shows the prize and the place, any
    other kind shows what was won."""
    inner = prize["prize"]
    words = [inner["name"], prize["name"]] if inner["type"] == "tier" else [prize["name"]]
    return _BETWEEN.join([inner["sponsor"]["name"], "-", *(escape(word) for word in words)])


def project_page(
    *,
    name: str = "Pebble Pay",
    slug: str = "pebble-pay",
    short_id: str = "x1y2z",
    short_line: str = "Pay a street vendor with a coin on Hedera.",
    event_slug: str = "sample-event",
    event_name: str = EVENT,
    starts_at: str = "2026-03-06T16:00:00.000Z",
    prizes: list[dict] | None = None,
    description: str = "<p>Pebble Pay lets a street vendor take a payment with a coin.</p>",
    made: str = "<p>A small web page asks the buyer to sign.</p>",
    code: str | None = "https://github.com/sample-org/pebble-pay",
    demo: str | None = "https://demo.example.test/pebble-pay",
    video: bool = True,
    data_changes: dict | None = None,
) -> bytes:
    """An INVENTED project page, in the shape of the real ones as they are saved.

    `description` and `made` are the HTML of the two texts. `data_changes` is laid over the data
    of the page, so that a test can build a page whose data and whose visible part do not fit.
    """
    prizes = prizes or []
    data = {
        "uuid": short_id,
        "slug": slug,
        "name": name,
        "tagline": short_line,
        "description": "$1a",
        "howItsMade": "$1b",
        "url": demo,
        "sourceCodeUrl": None,
        "primaryRepository": {"url": code} if code else None,
        "event": {"slug": event_slug, "name": event_name, "startTime": starts_at},
        "banner": {"file": {"fullUrl": f"https://cdn.example.test/banners/{slug}.png"}},
        "logo": {"file": {"fullUrl": f"https://cdn.example.test/logos/{slug}.png"}},
        "screenshots": [],
        "video": (
            {
                "file": {"fullUrl": f"https://cdn.example.test/videos/{slug}.mp4"},
                "muxUrl": f"https://stream.example.test/{slug}.m3u8",
                "muxThumbnailUrl": f"https://stream.example.test/{slug}.png",
                "youtubeId": None,
            }
            if video
            else None
        ),
        "prizes": prizes,
        "meta": {**PLANTED_SCORES, "demoVideoReady": video, "tmpVideoId": 12345, "timer": None},
    }
    data.update(data_changes or {})
    row = f'3c:["$","$L3d",null,{json.dumps({"project": data}, separators=(",", ":"))}]\n'
    cut = len(row) // 2
    pushes = [
        '1:"$Sreact.fragment"\n',
        "1a:T2e,an invented text row with a } and a {\n",
        row[:cut],
        row[cut:],
        "1b:T1c,one more invented text row\n",
    ]
    scripts = "\n".join(
        f"<script>self.__next_f.push([1,{json.dumps(text)}])</script>" for text in pushes
    )
    links = "".join(
        f'<a href="{escape(url)}" target="_blank">{label}</a>'
        for label, url in (("Live Demo", demo), ("Source Code", code))
        if url
    )
    winner_of = ""
    if prizes:
        entries = "".join(
            f'<div class="entry"><img src="https://cdn.example.test/logos/sponsor.png" alt="">'
            f"<div><h4>{shown_prize(prize)}</h4></div></div>"
            for prize in prizes
        )
        winner_of = f'<hr><h3>Winner of</h3><div class="space-y-3">{entries}</div>'
    return (
        "<!doctype html>\n"
        "<!-- INVENTED SAMPLE. Not taken from any real page. Every word in it is made up. -->\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(name)} | ETHGlobal</title>'
        f'<meta name="description" content="{escape(short_line)}"></head>\n'
        '<body><nav><a href="/">Home</a> <a href="/events">Events</a> '
        '<a href="/showcase">Showcase</a></nav>\n'
        f'<div class="page"><header><h1>{escape(name)}</h1>'
        f'<p class="lg:text-lg text-black-500">{escape(short_line)}</p>'
        f"<div>{links}</div></header>\n"
        f'<div class="columns"><aside><div class="card"><h2>{escape(name)}</h2>'
        f'<h3>Created At</h3><a href="/events/{event_slug}"><div>{escape(event_name)}</div></a>'
        f"{winner_of}</div></aside>\n"
        f'<section><h3>Project Description</h3><div class="text-black-500 text-md">{description}'
        f'</div>\n<h3>How it\'s Made</h3><div class="text-black-500 text-md">{made}</div>'
        "</section></div>\n"
        "<h3>Get the latest news and updates</h3>"
        '<form><input id="email" placeholder="Your email address"><button>Subscribe</button>'
        "</form></div>\n"
        "<script>self.__next_f=self.__next_f||[];self.__next_f.push([0])</script>\n"
        f"{scripts}\n</body></html>\n"
    ).encode()


# ------------------------------------------------------------------ a stand-in mirror node


class StandInMirror:
    """Stands in for the mirror node client: answers from small tables, and remembers what
    it was asked. The kinds are written as words here, as the ledger facts write them."""

    def __init__(self, network: str = "testnet", **things: dict[str, dict]) -> None:
        self.network = network
        self.things = things  # kind -> id -> answer
        self.lists: dict[tuple[str, str], list[dict]] = {}  # (what, id) -> oldest first
        self.asked: list[tuple] = []

    @property
    def requests_made(self) -> int:
        return len(self.asked)

    def _one(self, kind: str, entity: str) -> dict | None:
        self.asked.append((kind, entity))
        return self.things.get(kind, {}).get(entity)

    def token(self, entity: str) -> dict | None:
        return self._one("token", entity)

    def topic(self, entity: str) -> dict | None:
        return self._one("topic", entity)

    def contract(self, entity: str) -> dict | None:
        return self._one("contract", entity)

    def account(self, entity: str) -> dict | None:
        return self._one("account", entity)

    def _end(self, what: str, entity: str, newest_first: bool, **more: object) -> list[dict]:
        self.asked.append((what, entity, "newest" if newest_first else "oldest", more))
        found = self.lists.get((what, entity), [])
        return found[-1:] if newest_first else found[:1]

    def topic_messages(self, entity: str, *, newest_first: bool) -> list[dict]:
        return self._end("messages", entity, newest_first)

    def contract_results(self, entity: str, *, newest_first: bool) -> list[dict]:
        return self._end("calls", entity, newest_first)

    def account_transactions(
        self, entity: str, *, newest_first: bool, since: datetime | None = None
    ) -> list[dict]:
        return self._end("transactions", entity, newest_first, since=since)
