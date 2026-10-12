"""What the small collectors share: a few named pages of one site, read the polite way.

A small collector reads a handful of pages that the maintainer named, after the maintainer's yes
for that site (design rule 17). It keeps every promise of design 5.7: one request at a time with
a pause, the name of the tool and the maintainer's address in each request, a switch of its own in
.env that is read again before every request, a count of requests on disk with a small limit, and
a refusal of the site remembered until a person decides. This module builds such a client and
holds the few steps that every small collector takes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from hackathon_memory.collect.polite import (
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    FetchResult,
    PoliteClient,
    RequestCount,
    StopCollecting,
)
from hackathon_memory.collect.robots import read_rules
from hackathon_memory.settings import Settings


@dataclass(frozen=True)
class SmallSite:
    host: str
    switch: str  # the setting that turns the collector on, such as "collect_africa_winners"
    request_limit: int  # over all runs together

    @property
    def robots_url(self) -> str:
        return f"https://{self.host}/robots.txt"


def request_count_path(settings: Settings, host: str) -> Path:
    return Path(settings.data_dir) / "requests" / f"{host}.json"


def client_for(
    settings: Settings,
    site: SmallSite,
    *,
    allow: Callable[[str], bool],
    env_file: Path | None = None,
    **client_options: object,
) -> PoliteClient:
    """A polite client that may read what `allow` names, and nothing else.

    It is not made while the switch is off, after a refusal of the site, or during a cooldown.
    """
    if not getattr(settings, site.switch):
        raise CollectorRefused(
            f"The switch for {site.host} is off. Set {site.switch.upper()}=on in .env to allow "
            "it (design rule 17: only after the maintainer's yes for these pages)."
        )
    identity = CollectorIdentity.from_settings(settings)
    count = RequestCount(
        request_count_path(settings, site.host), site.host, limit=site.request_limit
    )
    try:
        refused = count.refusal()
    except StopCollecting as stop:
        raise CollectorRefused(str(stop)) from None
    if refused:
        raise CollectorRefused(
            f"{site.host} refused a request on {refused['at']} ({refused['status']}). Nothing is "
            "sent until a person decides how to go on."
        )
    if count.wait_left() > 0:
        raise CollectorRefused(
            f"{site.host} asked for a pause. Try again in {count.wait_left():.0f} s."
        )
    client_options.setdefault("max_requests", site.request_limit)

    def still_enabled() -> bool:
        # Read again before every request, so that turning the switch off stops at once.
        return bool(getattr(Settings(_env_file=env_file or ".env"), site.switch))

    return PoliteClient(
        site=site.host,
        identity=identity,
        allow=allow,
        is_enabled=still_enabled,
        count=count,
        **client_options,  # type: ignore[arg-type]
    )


def fetch(client: PoliteClient, url: str, what: str) -> FetchResult:
    """One page, or a stop that says why: a page that fails ends the command."""
    try:
        fetched = client.get(url)
    except FetchFailed as error:
        raise StopCollecting(f"{what} could not be read: {error}") from None
    if fetched.status != 200:
        raise StopCollecting(f"{what} answered {fetched.status}")
    return fetched


def obey_robots(
    client: PoliteClient, site: SmallSite, page: str, say: Callable[[str], None]
) -> None:
    """Read robots.txt once, say what it is, and stop if it forbids `page` to this tool."""
    rules, robots = read_rules(client, site.robots_url, site.host)
    if robots.status == 404:
        say("robots.txt: none (404), so nothing is forbidden by it.")
    else:
        say(f"robots.txt: read, {len(robots.body)} bytes. It is obeyed.")
    if not rules.allows(client.identity.name, page):
        raise StopCollecting(f"robots.txt of {site.host} does not allow this tool to read the page")


def count_line(client: PoliteClient) -> str:
    count = client.count
    if count is None:
        return "No count of requests."
    return f"Requests sent to {client.site} so far: {count.sent()} of {count.limit}."
