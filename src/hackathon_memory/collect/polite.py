"""The polite request layer. Every rule for reading a site (design 5.7) is code here.

| The rule                                            | Where it is kept                        |
|-----------------------------------------------------|-----------------------------------------|
| Only named pages                                    | `allow`, checked before every request   |
|                                                     | and on every redirect                   |
| A fixed limit of requests for each site             | `max_requests` for one run, and         |
|                                                     | `RequestCount` over all runs, and for   |
|                                                     | each day where answers are asked again  |
| One request at a time, a pause of two seconds       | `_lock`, `_wait_turn`                   |
| The tool's name and a contact address in each one   | `CollectorIdentity`, `_headers`         |
| A stop switch for each site, for a stop order of    | `is_enabled`, read before every request |
| the people who run the site                         |                                         |
| Never sign in                                       | `_NoCookies`, `trust_env = False`       |
| A no of the site (401, 403, 451, a bot check) is    | `RequestCount.note_refusal`, checked    |
| never worked around: a person decides how to go on  | before every request                    |
| "Too many requests" (429): a cooldown, then slower  | `RequestCount.note_too_many`,           |
|                                                     | `wait_left`, `min_pause`                |
| Stop after repeated errors                          | `_note_error`                           |

The maintainer's address goes to the site on purpose: the site was told that every request
carries it. Nowhere else is it printed or saved.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import NoReturn
from urllib.parse import urljoin

import requests

from hackathon_memory import __version__
from hackathon_memory.settings import Settings

PAUSE_SECONDS = 2.0  # "a pause of two seconds" (design 5.7)
MAX_REQUESTS = 300  # "a fixed limit stops it after 300 requests" (design 5.7)
MAX_ERRORS_IN_A_ROW = 5  # "stop after five errors in a row" (design 5.2)
MAX_BYTES = 5_000_000  # a saved page is 300 to 500 KB (design 11.6)
MAX_REDIRECTS = 3

# "Too many requests" (429) is a speed limit, not a no. It means: you came too fast. So the run
# stops, the tool waits at least one hour (longer if the site names a longer time), and from
# then on it leaves five times more room between two requests. No person has to decide that.
# But a site that says it a third time within a day means more than speed: then the tool
# takes it for a no, and a person decides.
TOO_MANY_REQUESTS = 429
COOLDOWN_SECONDS = 3600.0
SLOWER_BY = 5.0
MAX_TOO_MANY_A_DAY = 2

# Answer headers that say how a site limits or caches requests. Only these are kept, as they
# came, so that a person can see what the site counts. They hold no text of a page.
LIMIT_HEADERS = (
    "retry-after",
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
    "ratelimit-policy",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "cf-cache-status",
    "x-vercel-cache",
    "x-nextjs-cache",
    "age",
    "cache-control",
    "server",
)

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
# The site says no. We stop, and a person decides. We never try another way in (design rule 10).
_BLOCK_STATUSES = {401, 403, 407, 451}

_NAME = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CollectorRefused(Exception):
    """The collector will not start. The message says what is missing."""


class StopCollecting(Exception):
    """The run must stop now. The message says why and holds no page text."""


class TooManyRequests(StopCollecting):
    """The site answered 429. Nothing is asked again before the cooldown is over."""


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
    etag: str = ""  # the ETag header of the answer, for a conditional request later


class RequestCount:
    """Every request that was ever sent to one site, counted in one small file.

    A limit that only one run knows is not a limit: a look, a walk through a list and a run would
    each start at zero. So the count is kept on disk, and every command draws on the same limit.

    A file that cannot be read is never taken for zero. It stops everything until it is repaired.

    The same file remembers what the site answered.

    * "Too many requests" (429) is a speed limit. The file then holds a time before which nothing
      is sent (one hour later, or longer if the site names a longer time), and a longer pause for
      every later request (five times what it was). Every command keeps to both by itself.
    * A no (401, 403, 451, a bot check, or a third 429 within a day) is a refusal. No command
      sends a request to this site again until a person has decided how to go on.
    """

    def __init__(
        self,
        path: Path,
        site: str,
        limit: int = MAX_REQUESTS,
        now: Callable[[], datetime] | None = None,
        *,
        daily_limit: int | None = None,
    ) -> None:
        self.path = path
        self.site = site
        self.limit = limit
        # A limit for each day (UTC), for a site whose answers are asked again as they change
        # (design 7.3, 25 October 2026); None for a site whose pages are read once.
        self.daily_limit = daily_limit
        self.now = now or (lambda: datetime.now(UTC))

    def sent(self) -> int:
        return self._read()["sent"]

    def sent_today(self) -> int:
        return int(self._read()["by_day"].get(self.now().strftime("%Y-%m-%d"), 0))

    def left(self) -> int:
        left = max(0, self.limit - self.sent())
        if self.daily_limit is not None:
            left = min(left, max(0, self.daily_limit - self.sent_today()))
        return left

    def day_is_full(self) -> bool:
        """True when the limit of the day, and not the one over all runs, stops the requests."""
        return (self.daily_limit is not None and self.sent_today() >= self.daily_limit
                and self.sent() < self.limit)  # fmt: skip

    def add_one(self) -> None:
        record = self._read()
        day = self.now().strftime("%Y-%m-%d")
        record["sent"] += 1
        record["by_day"][day] = record["by_day"].get(day, 0) + 1
        self._write(record)

    # ------------------------------------------------------------------ a refusal

    def refusal(self) -> dict | None:
        """The refusal that is still open: when, which answer, and what the site asked for."""
        return self._read().get("refused")

    def note_refusal(
        self, status: int, asked_to_wait: str | None = None, pause_seconds: float = PAUSE_SECONDS
    ) -> None:
        record = self._read()
        record["refused"] = {
            "at": _stamp(self.now()),
            "status": status,
            "asked_to_wait": asked_to_wait,
            "pause_seconds": pause_seconds,  # how fast the tool was going when the site said no
        }
        self._write(record)

    def clear_refusal(self, decision: str) -> bool:
        """A person decided how to go on. The refusal and the decision stay in the notes."""
        record = self._read()
        refused = record.pop("refused", None)
        if refused is None:
            return False
        record.setdefault("notes", []).append(
            f"{_stamp(self.now())}: the refusal of {refused['at']} (answer {refused['status']}) "
            f"was cleared. The decision: {decision}"
        )
        self._write(record)
        return True

    # ------------------------------------------------------------------ too many requests

    def note_too_many(
        self,
        asked_to_wait: str | None = None,
        pause_seconds: float = PAUSE_SECONDS,
        at: datetime | None = None,
    ) -> bool:
        """The site said "too many requests". Returns False when a person must now decide.

        Sets the cooldown and the slower pace. `at` is the time of the answer, for one that
        came before this file knew about it.
        """
        record = self._read()
        when = at or self.now()
        events = record.setdefault("too_many", [])
        events.append(
            {"at": _stamp(when), "asked_to_wait": asked_to_wait, "pause_seconds": pause_seconds}
        )
        wait = max(COOLDOWN_SECONDS, _asked_seconds(asked_to_wait, when))
        until = when + timedelta(seconds=wait)
        earlier = record.get("not_before")
        if not earlier or _moment(earlier) < until:
            record["not_before"] = _stamp(until)
        record["min_pause_seconds"] = max(
            float(record.get("min_pause_seconds", 0.0)), float(pause_seconds) * SLOWER_BY
        )
        day_ago = when - timedelta(hours=24)
        in_a_day = sum(1 for event in events if _moment(event["at"]) > day_ago)
        if in_a_day > MAX_TOO_MANY_A_DAY:
            record["refused"] = {
                "at": _stamp(when),
                "status": TOO_MANY_REQUESTS,
                "asked_to_wait": asked_to_wait,
                "pause_seconds": pause_seconds,
            }
        self._write(record)
        return in_a_day <= MAX_TOO_MANY_A_DAY

    def not_before(self) -> datetime | None:
        """The end of the cooldown after "too many requests", if one was set."""
        stamp = self._read().get("not_before")
        return _moment(stamp) if stamp else None

    def wait_left(self) -> float:
        """Seconds until the cooldown ends. Zero when there is none, or when it is over."""
        until = self.not_before()
        return max(0.0, (until - self.now()).total_seconds()) if until else 0.0

    def min_pause(self) -> float:
        """The shortest pause that this site allows the tool since its last "too many requests"."""
        return float(self._read().get("min_pause_seconds", 0.0))

    # ------------------------------------------------------------------ the file

    def _write(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".part")
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary, self.path)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"site": self.site, "sent": 0, "by_day": {}}
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            sent, by_day = record["sent"], record["by_day"]
            if record["site"] != self.site or type(sent) is not int or sent < 0:
                raise ValueError("not the count of this site")
            if not isinstance(by_day, dict):
                raise ValueError("no count by day")
            refused = record.get("refused")
            if refused is not None:
                _moment(refused["at"])
                if type(refused["status"]) is not int:
                    raise ValueError("a refusal with no answer")
            if record.get("not_before"):
                _moment(record["not_before"])
            if float(record.get("min_pause_seconds", 0.0)) < 0:
                raise ValueError("a pause cannot be negative")
        except (OSError, ValueError, KeyError, TypeError):
            raise StopCollecting(
                f"The count of requests to {self.site} cannot be read ({self.path.name}). "
                "Nothing is requested until it is repaired."
            ) from None
        return record


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _moment(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _asked_to_wait(headers: requests.structures.CaseInsensitiveDict) -> str | None:
    """What the Retry-After header of an answer says, as it came, or None."""
    return (headers.get("Retry-After") or "").strip()[:40] or None


def _asked_seconds(asked: str | None, refused_at: datetime) -> float:
    """What a Retry-After header asks for, in seconds: a number, or a date. Zero if unclear."""
    if not asked:
        return 0.0
    if asked.strip().isdigit():
        return float(asked.strip())
    try:
        until = parsedate_to_datetime(asked)
    except (TypeError, ValueError):
        return 0.0
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    return max(0.0, (until - refused_at).total_seconds())


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
class RawAnswer:
    """An answer of a site as it came: its status, its headers and its body."""

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
        count: RequestCount | None = None,
        pause_seconds: float = PAUSE_SECONDS,
        max_requests: int = MAX_REQUESTS,
        max_errors_in_a_row: int = MAX_ERRORS_IN_A_ROW,
        max_bytes: int = MAX_BYTES,
        timeout: tuple[float, float] = (10.0, 30.0),
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
        wait_for_cooldown: bool = False,
    ) -> None:
        self.site = site
        self.identity = identity
        self.allow = allow
        self.is_enabled = is_enabled
        self.count = count  # the requests of all runs; None only in a test of something else
        # While a cooldown runs: wait for its end (True), or stop and say when it ends (False).
        self.wait_for_cooldown = wait_for_cooldown
        self.cooldowns_waited = 0
        self.pause_seconds = pause_seconds
        self.max_requests = max_requests
        self.max_errors_in_a_row = max_errors_in_a_row
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.clock = clock
        self.sleep = sleep
        self.now = now or (lambda: datetime.now(UTC))
        self.requests_made = 0
        # What the last answers said about limits and caches (LIMIT_HEADERS), and how often
        # each cache answer came. For a person who wants to see what the site counts.
        self.site_headers: dict[str, str] = {}
        self.cache_answers: dict[str, int] = {}
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

    def get(self, url: str, *, etag: str | None = None) -> FetchResult:
        """The answer for `url`. With `etag`, the ETag of the last answer, the request is
        conditional (If-None-Match): a site answers 304 and no body when nothing changed."""
        extra = {"If-None-Match": etag} if etag else None
        with self._lock:
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                self._check_allowed(current)
                raw = self._request_once(current, extra)
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
                    etag=str(raw.headers.get("ETag", ""))[:200],
                )
            raise StopCollecting(f"{self.site} sent too many redirects in a row.")

    def post_json(self, url: str, body: Mapping[str, object]) -> FetchResult:
        """The answer of a search that a site takes as JSON sent to `url` (Devfolio's search of
        projects, 31 October 2026). Every rule of `get` holds: the switch, the list of pages, the
        pause, the count on disk, the name and the address, the judging of the answer. A
        redirect is not followed: it stops the run."""
        data = json.dumps(dict(body), separators=(",", ":"), sort_keys=True).encode("utf-8")
        with self._lock:
            self._check_allowed(url)
            raw = self._request_once(url, {"Content-Type": "application/json"}, data=data)
            if raw.status in _REDIRECT_STATUSES:
                raise StopCollecting(f"{self.site} answered a search with a redirect.")
            return FetchResult(
                url=url,
                final_url=url,
                status=raw.status,
                body=raw.body,
                content_type=raw.headers.get("Content-Type", ""),
                fetched_at=self.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            )

    # ------------------------------------------------------------------ inside

    def _check_allowed(self, url: str) -> None:
        """May this address be asked now? The rules of every request, then the list of pages."""
        self._check_may_send()
        if not self.allow(url):
            raise StopCollecting(f"{url} is not on the list of pages named for {self.site}.")

    def _check_may_send(self) -> None:
        """May a request be sent now: the switch, a no of the site, a cooldown, the limits."""
        if not self.is_enabled():
            raise StopCollecting(f"The switch for {self.site} is off. Nothing more is requested.")
        refused = self.count.refusal() if self.count is not None else None
        if refused:
            raise StopCollecting(
                f"{self.site} refused a request on {refused['at']} (answer {refused['status']}). "
                "No request is sent to it again until the maintainer has decided how to go on."
            )
        wait = self.count.wait_left() if self.count is not None else 0.0
        if wait > 0:
            if not self.wait_for_cooldown:
                raise StopCollecting(
                    f'{self.site} said "too many requests". The cooldown runs until '
                    f"{_stamp(self.count.not_before())}. Nothing is requested before."
                )
            self.cooldowns_waited += 1
            self.sleep(wait)
            if not self.is_enabled():  # the switch may have been turned off in the meantime
                raise StopCollecting(
                    f"The switch for {self.site} is off. Nothing more is requested."
                )
        if self.requests_made >= self.max_requests:
            raise StopCollecting(f"The limit of {self.max_requests} requests is reached.")
        if self.count is not None and self.count.left() <= 0:
            if self.count.day_is_full():
                raise StopCollecting(
                    f"The limit of {self.count.daily_limit} requests to {self.site} for one day "
                    "is reached. Nothing more is requested today (UTC)."
                )
            raise StopCollecting(
                f"The limit of {self.count.limit} requests to {self.site} over all runs is "
                "reached. Nothing more is requested."
            )

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.identity.user_agent,
            "From": self.identity.contact,
            "Accept": "text/html, text/plain;q=0.9",
        }

    def pause_in_use(self) -> float:
        """The pause between two requests: ours, or a longer one that the site made necessary."""
        slower = self.count.min_pause() if self.count is not None else 0.0
        return max(self.pause_seconds, slower)

    def _wait_turn(self) -> None:
        if self._last_end is None:
            return
        wait = self.pause_in_use() - (self.clock() - self._last_end)
        if wait > 0:
            self.sleep(wait)

    def _note_site_headers(self, headers: requests.structures.CaseInsensitiveDict) -> None:
        for name in LIMIT_HEADERS:
            value = headers.get(name)
            if value:
                self.site_headers[name] = str(value)[:80]
        for name in ("cf-cache-status", "x-vercel-cache", "x-nextjs-cache"):
            value = headers.get(name)
            if value:
                key = f"{name}: {str(value)[:20]}"
                self.cache_answers[key] = self.cache_answers.get(key, 0) + 1

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

    def _request_once(
        self, url: str, extra: dict[str, str] | None = None, *, data: bytes | None = None
    ) -> RawAnswer:
        """One request: a GET, or a POST of `data` when there is some."""
        self._wait_turn()
        self.requests_made += 1
        if self.count is not None:
            self.count.add_one()  # before it is sent: a request that fails was still a request
        try:
            response = self.session.request(
                "GET" if data is None else "POST",
                url,
                data=data,
                headers={**self._headers(), **(extra or {})},
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

        raw = RawAnswer(status=response.status_code, headers=response.headers, body=body)
        self._note_site_headers(raw.headers)
        self._judge(raw)
        self._errors_in_a_row = 0
        return raw

    def _judge(self, raw: RawAnswer) -> None:
        """What an answer means for the run. Raises when the run must stop or the page failed.

        This is the one place that reads the status of an answer. A client for a site whose
        answers mean something else, such as an API, changes this method only.
        """
        asked = _asked_to_wait(raw.headers)
        if raw.status in _BLOCK_STATUSES or "cf-mitigated" in raw.headers:
            self._refused(raw.status, asked)
        if raw.status == TOO_MANY_REQUESTS:
            self._too_many(raw.status, asked)
        if raw.status >= 500:
            self._failed(f"status {raw.status}")

    def _refused(self, status: int, asked: str | None) -> NoReturn:
        """The site says no. It is remembered for every later command: a person decides."""
        if self.count is not None:
            self.count.note_refusal(status, asked, self.pause_in_use())
        raise StopCollecting(
            f"{self.site} answered {status}: the site says no. Nothing is worked around."
        )

    def _too_many(self, status: int, asked: str | None) -> NoReturn:
        """The site says "too many requests": a cooldown, and then a slower pace."""
        pace = self.pause_in_use()
        goes_on = self.count.note_too_many(asked, pace) if self.count is not None else True
        raise TooManyRequests(
            f"{self.site} answered {status}: too many requests, with {pace:.0f} seconds between "
            "two of them. Nothing is asked again before the cooldown is over, and then "
            "the tool goes on more slowly."
            + (f" The site asks to wait: {asked}." if asked else "")
            + ("" if goes_on else " This was one time too many: a person decides now.")
        )

    def _failed(self, reason: str) -> NoReturn:
        """This page failed. The run may go on, until too many fail in a row."""
        self._note_error(reason)
        raise FetchFailed(reason)
