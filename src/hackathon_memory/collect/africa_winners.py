"""The page with the winners of the Hedera Africa hackathon: one page, read by a small collector.

    python -m hackathon_memory.collect.africa_winners --look    2 requests, nothing saved

The maintainer said yes for this one page on 10 October 2026 (design rule 17). Its winners become
winner entries (design 4.6). The site has no robots.txt (it answers 404) and shows no terms of
use (seen on 11 October 2026). It is read the way design 5.7 promises for every site:

* one request at a time, with a pause, and the name of the tool and the maintainer's address in
  each request;
* its own switch in .env, COLLECT_AFRICA_WINNERS, off unless the maintainer turns it on, and read
  again before every request;
* its own count of requests on disk, with a small limit, and a refusal remembered;
* two addresses only: the page and its robots.txt. Its links lead to DoraHacks, and no program
  follows them (design 5.6).

The look keeps the page in memory and prints its SHAPE with the skeleton printer: no text, no
name, no link target beyond its shape, and the keys of its data with their counts. The shape says
where the winners are and where people are named, so that the part about people can be cut out
before the page is ever saved (design rule 5).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from hackathon_memory.collect.polite import (
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    PoliteClient,
    RequestCount,
    StopCollecting,
)
from hackathon_memory.collect.robots import read_rules
from hackathon_memory.collect.skeleton import skeleton
from hackathon_memory.settings import Settings

SITE = "hedera-hackathon.hashgraph.swiss"
PAGE = f"https://{SITE}/"
ROBOTS_URL = f"https://{SITE}/robots.txt"
# Two looks and a read of robots.txt and the page, with room for one failure.
REQUEST_LIMIT = 10
USAGE = "usage: python -m hackathon_memory.collect.africa_winners --look"


def is_allowed_url(url: str) -> bool:
    """Only the page and its robots.txt, over https, with nothing more in the address."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != SITE or parts.query or parts.fragment:
        return False
    if parts.port not in (None, 443) or parts.username or parts.password:
        return False
    return parts.path in ("", "/", "/robots.txt")


@dataclass(frozen=True)
class Paths:
    raw_dir: Path
    request_count: Path


def paths(settings: Settings) -> Paths:
    root = Path(settings.data_dir)
    return Paths(raw_dir=root / "raw" / SITE, request_count=root / "requests" / f"{SITE}.json")


def client_for(
    settings: Settings, *, env_file: Path | None = None, **client_options: object
) -> PoliteClient:
    """A polite client that may read the page and its robots.txt, and nothing else.

    It is not made while the switch is off, after a refusal of the site, or during a cooldown.
    """
    if not settings.collect_africa_winners:
        raise CollectorRefused(
            f"The switch for {SITE} is off. Set COLLECT_AFRICA_WINNERS=on in .env to allow it "
            "(design rule 17: only after the maintainer's yes for this page)."
        )
    identity = CollectorIdentity.from_settings(settings)
    count = RequestCount(paths(settings).request_count, SITE, limit=REQUEST_LIMIT)
    try:
        refused = count.refusal()
    except StopCollecting as stop:
        raise CollectorRefused(str(stop)) from None
    if refused:
        raise CollectorRefused(
            f"{SITE} refused a request on {refused['at']} ({refused['status']}). Nothing is sent "
            "until a person decides how to go on."
        )
    if count.wait_left() > 0:
        raise CollectorRefused(f"{SITE} asked for a pause. Try again in {count.wait_left():.0f} s.")
    client_options.setdefault("max_requests", REQUEST_LIMIT)

    def still_enabled() -> bool:
        # Read again before every request, so that turning the switch off stops at once.
        return Settings(_env_file=env_file or ".env").collect_africa_winners

    return PoliteClient(
        site=SITE,
        identity=identity,
        allow=is_allowed_url,
        is_enabled=still_enabled,
        count=count,
        **client_options,  # type: ignore[arg-type]
    )


def look(client: PoliteClient, say: Callable[[str], None] = print) -> bool:
    """robots.txt, then the page, kept in memory only, and its shape printed. True if all went
    well. Nothing is saved."""
    try:
        rules, robots = read_rules(client, ROBOTS_URL, SITE)
        if robots.status == 404:
            say("robots.txt: none (404), so nothing is forbidden by it.")
        else:
            say(f"robots.txt: read, {len(robots.body)} bytes. It is obeyed.")
        if not rules.allows(client.identity.name, PAGE):
            raise StopCollecting(f"robots.txt of {SITE} does not allow this tool to read the page")
        try:
            fetched = client.get(PAGE)
        except FetchFailed as error:
            raise StopCollecting(f"the page could not be read: {error}") from None
        if fetched.status != 200:
            raise StopCollecting(f"the page answered {fetched.status}")
        say(
            f"--- The page: status {fetched.status}, {len(fetched.body)} bytes, "
            f"type {fetched.content_type or 'not given'}. It is not saved."
        )
        say(skeleton(fetched.body))
        return True
    except StopCollecting as stop:
        say(f"STOPPED: {stop}")
        return False
    finally:
        if client.count is not None:
            say(f"Requests sent to {SITE} so far: {client.count.sent()} of {client.count.limit}.")


def main(argv: list[str]) -> int:
    if argv != ["--look"]:
        print(USAGE)
        return 2
    try:
        client = client_for(Settings())
    except CollectorRefused as refusal:
        print(f"Refused: {refusal}")
        return 1
    return 0 if look(client) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
