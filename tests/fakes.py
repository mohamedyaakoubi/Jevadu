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
        pages: dict[str, Reply] | None = None,
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
