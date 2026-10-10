"""The polite request layer. Every promise made to a site (design 5.7) is code here.

| The promise                                         | Where it is kept                        |
|-----------------------------------------------------|-----------------------------------------|
| Only the pages we named                             | `allow`, checked before every request   |
|                                                     | and on every redirect                   |
| A fixed limit of 300 requests                       | `max_requests`                          |
| One request at a time, a pause of two seconds       | `_lock`, `_wait_turn`                   |
| The tool's name and a contact address in each one   | `CollectorIdentity`, `_headers`         |
| A stop switch for each site                         | `is_enabled`, read before every request |
| Stop after repeated errors, never work around a     | `_note_error`, `_BLOCK_STATUSES`        |
| block, never sign in                                | `_NoCookies`, `trust_env = False`       |

The maintainer's address goes to the site on purpose: the maintainer promised it in writing.
Nowhere else is it printed or saved.
"""

from __future__ import annotations

import http.cookiejar
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin

import requests

from hackathon_memory import __version__
from hackathon_memory.settings import Settings

PAUSE_SECONDS = 2.0  # "a pause of two seconds" (design 5.7)
MAX_REQUESTS = 300  # "a fixed limit stops it after 300 requests" (design 5.7)
MAX_ERRORS_IN_A_ROW = 5  # "stop after five errors in a row" (design 5.2)
MAX_BYTES = 5_000_000  # a saved page is 300 to 500 KB (design 11.6)
MAX_REDIRECTS = 3

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
# The site says no or stop. We stop. We never try another way in (design rule 10).
_BLOCK_STATUSES = {401, 403, 407, 429, 451}

_NAME = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CollectorRefused(Exception):
    """The collector will not start. The message says what is missing."""


class StopCollecting(Exception):
    """The run must stop now. The message says why and holds no page text."""


class FetchFailed(Exception):
    """One page could not be fetched. The run may go on with the next one."""


@dataclass(frozen=True)
class CollectorIdentity:
    """Who the collector says it is, in every request (design 5.7)."""

    name: str
    contact: str = field(repr=False)  # the maintainer's address: never printed
    version: str = __version__

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise CollectorRefused(
                "COLLECTOR_NAME must be 3 to 64 letters, digits, dots, dashes or underscores."
            )
        if not _EMAIL.match(self.contact):
            raise CollectorRefused("COLLECTOR_CONTACT_EMAIL does not look like an email address.")

    @classmethod
    def from_settings(cls, settings: Settings) -> CollectorIdentity:
        name = settings.collector_name.strip()
        contact = settings.collector_contact_email.get_secret_value().strip()
        if not name or not contact:
            raise CollectorRefused(
                "The collector does not start: COLLECTOR_NAME and COLLECTOR_CONTACT_EMAIL must "
                "both be set in .env. Every request must say who sends it (design 5.7)."
            )
        return cls(name=name, contact=contact)

    @property
    def user_agent(self) -> str:
        return f"{self.name}/{self.version} (research tool; contact: {self.contact})"


@dataclass(frozen=True)
class FetchResult:
    url: str  # the address that was asked for
    final_url: str  # the address after the redirects that were allowed
    status: int
    body: bytes
    content_type: str
    fetched_at: str  # UTC, ISO form


class _NoCookies(http.cookiejar.CookiePolicy):
    """Keeps no cookie. The collector never signs in, so it has nothing to remember."""

    netscape = True
    rfc2965 = False
    hide_cookie2 = False

    def set_ok(self, cookie, request):  # noqa: ANN001, ARG002
        return False

    def return_ok(self, cookie, request):  # noqa: ANN001, ARG002
        return False

    def domain_return_ok(self, domain, request):  # noqa: ANN001, ARG002
        return False

    def path_return_ok(self, path, request):  # noqa: ANN001, ARG002
        return False


@dataclass
class _Raw:
    status: int
    headers: requests.structures.CaseInsensitiveDict
    body: bytes


class PoliteClient:
    def __init__(
        self,
        *,
        site: str,
        identity: CollectorIdentity,
        allow: Callable[[str], bool],
        is_enabled: Callable[[], bool],
        session: requests.Session | None = None,
        pause_seconds: float = PAUSE_SECONDS,
        max_requests: int = MAX_REQUESTS,
        max_errors_in_a_row: int = MAX_ERRORS_IN_A_ROW,
        max_bytes: int = MAX_BYTES,
        timeout: tuple[float, float] = (10.0, 30.0),
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.site = site
        self.identity = identity
        self.allow = allow
        self.is_enabled = is_enabled
        self.pause_seconds = pause_seconds
        self.max_requests = max_requests
        self.max_errors_in_a_row = max_errors_in_a_row
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.clock = clock
        self.sleep = sleep
        self.now = now or (lambda: datetime.now(UTC))
        self.requests_made = 0
        self._errors_in_a_row = 0
        self._last_end: float | None = None
        self._lock = threading.Lock()  # one request at a time, also across threads

        self.session = session or requests.Session()
        self.session.cookies.set_policy(_NoCookies())
        self.session.trust_env = False  # no ~/.netrc login, no proxy from the environment
        self.session.auth = None

    # ------------------------------------------------------------------ public

    def raise_pause_to(self, seconds: float) -> None:
        """A site asked for a longer pause (robots.txt Crawl-delay). Never shorten the pause."""
        self.pause_seconds = max(self.pause_seconds, seconds)

    def get(self, url: str) -> FetchResult:
        with self._lock:
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                self._check_allowed(current)
                raw = self._request_once(current)
                if raw.status in _REDIRECT_STATUSES:
                    location = raw.headers.get("Location")
                    if not location:
                        raise StopCollecting(f"{self.site} sent a redirect with no address.")
                    current = urljoin(current, location)
                    continue
                return FetchResult(
                    url=url,
                    final_url=current,
                    status=raw.status,
                    body=raw.body,
                    content_type=raw.headers.get("Content-Type", ""),
                    fetched_at=self.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                )
            raise StopCollecting(f"{self.site} sent too many redirects in a row.")

    # ------------------------------------------------------------------ inside

    def _check_allowed(self, url: str) -> None:
        if not self.is_enabled():
            raise StopCollecting(f"The switch for {self.site} is off. Nothing more is requested.")
        if self.requests_made >= self.max_requests:
            raise StopCollecting(f"The limit of {self.max_requests} requests is reached.")
        if not self.allow(url):
            raise StopCollecting(f"{url} is not on the list of pages named for {self.site}.")

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.identity.user_agent,
            "From": self.identity.contact,
            "Accept": "text/html, text/plain;q=0.9",
        }

    def _wait_turn(self) -> None:
        if self._last_end is None:
            return
        wait = self.pause_seconds - (self.clock() - self._last_end)
        if wait > 0:
            self.sleep(wait)

    def _note_error(self, reason: str) -> None:
        self._errors_in_a_row += 1
        if self._errors_in_a_row >= self.max_errors_in_a_row:
            raise StopCollecting(
                f"{self._errors_in_a_row} errors in a row (the last: {reason}). Stopped."
            )

    def _read_body(self, response: requests.Response) -> bytes:
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > self.max_bytes:
                raise FetchFailed(f"the answer is larger than {self.max_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

    def _request_once(self, url: str) -> _Raw:
        self._wait_turn()
        self.requests_made += 1
        try:
            response = self.session.get(
                url,
                headers=self._headers(),
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
            )
            try:
                body = self._read_body(response)
            finally:
                response.close()
        except FetchFailed as error:
            self._last_end = self.clock()
            self._note_error(str(error))
            raise
        except requests.RequestException as error:
            self._last_end = self.clock()
            self._note_error(f"network error {type(error).__name__}")
            raise FetchFailed(f"network error {type(error).__name__}") from None
        self._last_end = self.clock()

        status = response.status_code
        if status in _BLOCK_STATUSES or "cf-mitigated" in response.headers:
            raise StopCollecting(
                f"{self.site} answered {status}: the site says no. Nothing is worked around."
            )
        if status >= 500:
            self._note_error(f"status {status}")
            raise FetchFailed(f"status {status}")
        self._errors_in_a_row = 0
        return _Raw(status=status, headers=response.headers, body=body)
