"""Stand-ins for a website and for the clock, so the collector is tested without a network.

Nothing here touches the internet. FakeSite answers requests from a dictionary, and records every
request it gets: the address, the headers and the order. FakeTime replaces sleeping, so the test
of the two-second pause takes no time.
"""

from __future__ import annotations

import io
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
