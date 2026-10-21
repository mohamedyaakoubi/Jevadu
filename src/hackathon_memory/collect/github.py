"""Ask GitHub's API about the public repositories of the projects (design 7.3).

The maintainer said yes to GitHub's API on 10 October 2026: public repositories, one request at
a time. The token in .env reads public repositories only.

The rules of design 5.7 hold here too, through the polite client: the name of the tool and the
contact address in every request, one request at a time with a pause, a stop switch in .env
(COLLECT_GITHUB), and a limit of requests counted on disk. Every answer is saved, so a
repository is asked again only when a team registers it (design 9.2): GitHub's limits are far
above what the tool sends, and the rule of a page asked once holds for the sites that it was
promised to.

GitHub's own rules, read on docs.github.com on 11 October 2026:

* requests go one after the other. A GET costs one point; the limits are 900 points a minute
  and 5,000 requests an hour for one person;
* an answer of 403 or 429 with "x-ratelimit-remaining: 0", a "retry-after" or a message about a
  rate limit means: too fast. "Continuing to make requests while you are rate limited may result
  in the banning of your integration";
* a redirect is not an error. A repository that was moved or renamed answers 301;
* the version of the API is named in a header. 2026-03-10 is the newest, and none of its changes
  touches what this tool asks.

How an answer is read here:

* 200: the thing that was asked for. It is saved.
* 301, 302, 307: it has moved. The new address is followed, at most three times.
* 404: no such repository, or no README. It is saved: it is an answer.
* 403 or 451 with "Repository access blocked": GitHub blocked this one repository. It is saved,
  and the run goes on.
* 403 or 429 with a sign of a rate limit: too fast. The rule of a 429 holds: the run stops, the
  tool waits at least an hour, and then it goes on five times slower.
* 401: the token is not accepted. Everything stops, and a person decides.
* Another 403, 407 or 451, or a bot check: a no. Everything stops, and a person decides.
* 500 and more: an error. It is counted, and five in a row stop the run.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlsplit

import requests
from pydantic import SecretStr
from requests.structures import CaseInsensitiveDict

from hackathon_memory.collect.polite import (
    _REDIRECT_STATUSES,
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    FetchResult,
    PoliteClient,
    RawAnswer,
    RequestCount,
    StopCollecting,
)
from hackathon_memory.parse.hedera_code import LimitedStream
from hackathon_memory.settings import Settings

T = TypeVar("T")

SITE = "api.github.com"
# Where GitHub sends the archive of a repository: "Download a repository archive (tar)" answers
# 302 with an address on this host (docs.github.com and one request, 21 October 2026).
ARCHIVE_HOST = "codeload.github.com"
API_VERSION = "2026-03-10"
# Design rule 10: at least one second between two requests. That is 60 points a minute, a
# fifteenth of what GitHub allows.
PAUSE_SECONDS = 1.0
# Over all runs. The README of each repository (about 650), then the facts of the code (about
# eight requests for each repository) need about 6,000. The rest is room for redirects.
REQUEST_LIMIT = 8000
# When fewer requests than this are left in GitHub's hour, the run stops before it is told to.
HOURLY_RESERVE = 100
CODE_HOST = "github.com"

_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_RATE_LIMIT_WORDS = re.compile(r"rate limit", re.IGNORECASE)
_BLOCKED_WORDS = re.compile(r"^repository access blocked", re.IGNORECASE)


def repository_of(link: str) -> str | None:
    """The link of a repository on GitHub, in one spelling, or None for another link.

    "https://www.GitHub.com/Sample-Org/Pebble.git/" and "https://github.com/sample-org/pebble"
    are the same repository, so both give "https://github.com/sample-org/pebble". GitHub does not
    tell small and capital letters apart in these names.
    """
    try:
        parts = urlsplit(link.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower().removeprefix("www.")
    names = [name for name in parts.path.split("/") if name]
    if parts.scheme not in ("http", "https") or host != CODE_HOST or len(names) < 2:
        return None
    owner, name = names[0], names[1].removesuffix(".git")
    if not (_NAME.match(owner) and _NAME.match(name)) or name in (".", ".."):
        return None
    return f"https://{CODE_HOST}/{owner.lower()}/{name.lower()}"


def readme_address(repository: str) -> str:
    """The address of the README of a repository in GitHub's API."""
    owner, name = repository.removeprefix(f"https://{CODE_HOST}/").split("/")
    return f"https://{SITE}/repos/{owner}/{name}/readme"


def archive_address(repository: str) -> str:
    """The address in GitHub's API that sends the archive of the default branch of a
    repository ("If you omit :ref, the repository's default branch will be used")."""
    owner, name = repository.removeprefix(f"https://{CODE_HOST}/").split("/")
    return f"https://{SITE}/repos/{owner}/{name}/tarball"


def _raw_reader(response: requests.Response) -> Callable[[int], bytes]:
    """Read the bytes of an answer as they came: an archive is gzip, and is not unpacked on the
    way, also when a server names gzip as the encoding of the answer (urllib3 2.8.0,
    HTTPResponse.read(amt, decode_content))."""
    return lambda size: response.raw.read(size, decode_content=False)


def allowed(url: str) -> bool:
    """Only the API's own pages about repositories. A redirect elsewhere is refused."""
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.netloc == SITE
        and parts.path.startswith(("/repos/", "/repositories/"))
        and ".." not in parts.path
    )


def api_message(body: bytes) -> str:
    """The "message" of an answer of the API, or nothing."""
    try:
        answer = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ""
    return str(answer.get("message", ""))[:200] if isinstance(answer, dict) else ""


class GitHubClient(PoliteClient):
    """The polite client with the headers and the answers of GitHub's API."""

    def __init__(self, *, token: SecretStr, **options: object) -> None:
        super().__init__(**options)  # type: ignore[arg-type]
        self._token = token  # a SecretStr: it never prints
        self.hourly_left: int | None = None  # what GitHub said in its last answer
        self.hourly_reset: int | None = None  # when its hour starts again, in epoch seconds

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.identity.user_agent,
            "From": self.identity.contact,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "Authorization": f"Bearer {self._token.get_secret_value()}",
        }

    def _check_allowed(self, url: str) -> None:
        super()._check_allowed(url)
        if self.hourly_left is not None and self.hourly_left < HOURLY_RESERVE:
            raise StopCollecting(
                f"GitHub says that only {self.hourly_left} requests are left in its hour, until "
                f"{_hour_end(self.hourly_reset)}. The run stops before GitHub has to say no. "
                "Start it again after that time: it goes on where it stopped."
            )

    def _judge(self, raw: RawAnswer) -> None:
        self._note_hour(raw.headers)
        message = api_message(raw.body)
        if raw.status in (403, 429) and (
            raw.headers.get("x-ratelimit-remaining") == "0"
            or "retry-after" in raw.headers
            or _RATE_LIMIT_WORDS.search(message)
        ):
            self._too_many(raw.status, self._asked_to_wait(raw.headers))
        if raw.status in (403, 451) and _BLOCKED_WORDS.match(message):
            return  # GitHub blocked this one repository: that is an answer about it
        if raw.status == 404:
            return  # no such repository, or no README: an answer
        super()._judge(raw)  # 401 and every other no, 429, and the errors of the server

    def read_archive(
        self,
        url: str,
        read: Callable[[LimitedStream], T],
        *,
        max_bytes: int | None = None,
        seconds: float | None = None,
    ) -> tuple[FetchResult, T | None]:
        """Ask the API for the archive of a repository, then download it from GitHub's archive
        host as a stream and hand it to `read`: nothing of the archive is kept here. Two
        requests, one after the other, each counted and paused like every other. The token
        goes to the API only; the download carries the name of the tool and its contact.

        An answer of the API that is not a redirect (404, a blocked repository) comes back with
        no result. A download that does not answer 200 is judged like every answer: a no stops
        the run, too many requests starts the cooldown, anything else fails. A download that
        broke off on the way counts as an error in a row, like a network error."""
        with self._lock:
            answer, location = self._archive_address(url)
            if location is None:
                return answer, None
            result, content_type = self._download(location, read, max_bytes, seconds)
            return FetchResult(url, location, 200, b"", content_type, answer.fetched_at), result

    def _archive_address(self, url: str) -> tuple[FetchResult, str | None]:
        """Ask the API where the archive of a repository is. Returns the API's answer, with the
        address of the archive, or with None when the answer is not a redirect."""
        self._check_allowed(url)
        errors = self._errors_in_a_row
        raw = self._request_once(url)
        stamp = self.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        answer = FetchResult(url, url, raw.status, raw.body, raw.headers.get("Content-Type", ""),
                             stamp)  # fmt: skip
        if raw.status not in _REDIRECT_STATUSES:
            return answer, None
        # The redirect is half of the exchange: it clears no error in a row, so that downloads
        # that keep breaking off stop the run.
        self._errors_in_a_row = errors
        location = str(raw.headers.get("Location", ""))
        target = urlsplit(location)
        if target.scheme != "https" or target.netloc != ARCHIVE_HOST:
            raise StopCollecting(
                f"GitHub sent the archive to {target.netloc or 'no address'}, not to "
                f"{ARCHIVE_HOST}. Nothing is downloaded."
            )
        return answer, location

    def _download(
        self,
        location: str,
        read: Callable[[LimitedStream], T],
        max_bytes: int | None,
        seconds: float | None,
    ) -> tuple[T, str]:
        """Download an archive from GitHub's archive host as a stream and hand it to `read`.
        Returns what `read` gave, with the type of the answer."""
        self._check_may_send()
        self._wait_turn()
        self.requests_made += 1
        if self.count is not None:
            self.count.add_one()
        headers = {"User-Agent": self.identity.user_agent, "From": self.identity.contact}
        try:
            response = self.session.get(location, headers=headers, timeout=self.timeout,
                                        allow_redirects=False, stream=True)  # fmt: skip
        except requests.RequestException as error:
            self._last_end = self.clock()
            self._note_error(f"network error {type(error).__name__}")
            raise FetchFailed(f"network error {type(error).__name__}") from None
        try:
            if response.status_code != 200:  # a no, too many requests, or an error
                self._last_end = self.clock()
                self._judge(RawAnswer(response.status_code, response.headers, b""))
                self._failed(f"status {response.status_code} for the archive")
            stream = LimitedStream(_raw_reader(response), max_bytes=max_bytes, seconds=seconds,
                                   clock=self.clock)  # fmt: skip
            result = read(stream)
        finally:
            response.close()
            self._last_end = self.clock()
        if stream.broken is not None:
            self._note_error(f"the download broke off ({stream.broken})")
        else:
            self._errors_in_a_row = 0
        return result, response.headers.get("Content-Type", "")

    def _note_hour(self, headers: CaseInsensitiveDict) -> None:
        left = str(headers.get("x-ratelimit-remaining", ""))
        reset = str(headers.get("x-ratelimit-reset", ""))
        if left.isdigit():
            self.hourly_left = int(left)
        if reset.isdigit():
            self.hourly_reset = int(reset)

    def _asked_to_wait(self, headers: CaseInsensitiveDict) -> str:
        """How long GitHub asks the tool to wait, in seconds, as text."""
        asked = str(headers.get("retry-after", "")).strip()
        if asked:
            return asked[:40]
        if headers.get("x-ratelimit-remaining") == "0" and self.hourly_reset is not None:
            return str(max(0, self.hourly_reset - int(self.now().timestamp())))
        return "60"  # "Otherwise, wait for at least one minute before retrying."


def _hour_end(reset: int | None) -> str:
    if reset is None:
        return "the end of GitHub's hour"
    return datetime.fromtimestamp(reset, UTC).strftime("%Y-%m-%d %H:%M UTC")


def request_count(settings: Settings) -> RequestCount:
    return RequestCount(
        Path(settings.data_dir) / "requests" / f"{SITE}.json", SITE, limit=REQUEST_LIMIT
    )


def raw_dir(settings: Settings) -> Path:
    return Path(settings.data_dir) / "raw" / SITE


def github_client(
    settings: Settings,
    *,
    env_file: Path | None = None,
    is_enabled: Callable[[], bool] | None = None,
    **options: object,
) -> GitHubClient:
    """A client for GitHub's API. Refuses (CollectorRefused) when a promise cannot be kept."""
    token = settings.github_token
    if not token.get_secret_value().strip():
        raise CollectorRefused("GITHUB_TOKEN is empty in .env. Nothing is asked of GitHub.")
    pause = float(options.pop("pause_seconds", PAUSE_SECONDS))  # type: ignore[arg-type]
    if pause < PAUSE_SECONDS:
        raise CollectorRefused(
            f"The pause between two requests is never shorter than {PAUSE_SECONDS:.0f} second."
        )
    identity = CollectorIdentity.from_settings(settings)
    count = request_count(settings)
    try:
        refused = count.refusal()
        waiting = count.wait_left()
    except StopCollecting as stop:
        raise CollectorRefused(str(stop)) from None
    if refused:
        raise CollectorRefused(
            f"{SITE} refused a request on {refused['at']} (answer {refused['status']}). Nothing "
            "is asked of it until the maintainer has decided how to go on."
        )
    if waiting > 0 and not options.get("wait_for_cooldown"):
        raise CollectorRefused(
            f'{SITE} said "too many requests". Nothing is asked before '
            f"{count.not_before():%Y-%m-%d %H:%M} UTC. Start again then, or add --wait."
        )

    def still_enabled() -> bool:
        # Read again before every request, so that turning the switch off stops a run at once.
        return Settings(_env_file=env_file or ".env").collect_github

    options.setdefault("max_requests", REQUEST_LIMIT)
    return GitHubClient(
        token=token,
        site=SITE,
        identity=identity,
        allow=allowed,
        is_enabled=is_enabled or still_enabled,
        count=count,
        pause_seconds=pause,
        **options,
    )
