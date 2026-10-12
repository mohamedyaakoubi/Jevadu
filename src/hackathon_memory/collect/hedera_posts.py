"""Hedera's own posts with the winners of its older hackathons: nine pages of hedera.com.

    python -m hackathon_memory.collect.hedera_posts --look    robots.txt and one post, nothing saved

The maintainer's yes of 9 October 2026 (design rule 17): "For hedera by program if the tool call
wasnt refused by the server." If the server refuses the program, nothing is worked around: the
maintainer saves the posts by hand into data/by-hand/hedera.com/ instead (design 4.6). The terms
of use (last updated on 24 November 2025, read on 9 October 2026) say nothing about programs; the
content may not be copied for commercial purposes, and this tool is not commercial.

The posts are read the way of design 5.7 (small_site.py): a switch of their own,
COLLECT_HEDERA_POSTS, a count of requests on disk with a small limit, and only robots.txt and the
nine posts below, on hedera.com or on www.hedera.com if the site sends a request there.

A post may name the people of a team. The look keeps one post in memory, prints its SHAPE with
the skeleton printer, and counts the lines that start like a list of people ("Team:", "Built
by:"), without printing them, so that such lines can be cut out before any post is saved.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from collections.abc import Callable
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from hackathon_memory.collect import small_site
from hackathon_memory.collect.polite import CollectorRefused, PoliteClient, StopCollecting
from hackathon_memory.collect.skeleton import skeleton
from hackathon_memory.collect.small_site import SmallSite, count_line, fetch, obey_robots
from hackathon_memory.settings import Settings

SITE = "hedera.com"
HOSTS = frozenset({"hedera.com", "www.hedera.com"})
POSTS = {
    "Hedera20": f"https://{SITE}/blog/hedera20-hackathon-winners",
    "Hedera21": f"https://{SITE}/blog/announcing-the-hedera21-hackathon-winners",
    "Hedera22": f"https://{SITE}/blog/congratulations-to-the-hedera22-hello-smart-contract-"
    "hackathon-winners",
    "Beyond Blockchain 2023": f"https://{SITE}/blog/the-winning-projects-of-the-beyond-"
    "blockchain-hackathon-2023",
    "Hello Future 2024": f"https://{SITE}/blog/these-are-the-winners-of-the-2024-hellofuture-"
    "hackathon",
    "Hello Future 2.0": f"https://{SITE}/blog/these-are-the-winners-of-the-hellofuture-"
    "hackathon-2-0",
    "Hello Future Origins": f"https://{SITE}/blog/these-are-the-winners-of-the-hello-future-"
    "origins-hackathon",
    "Hello Future Ascension": f"https://{SITE}/blog/these-are-the-winners-of-the-hello-future-"
    "ascension-hackathon",
    "Hello Future Apex": f"https://{SITE}/blog/these-are-the-winners-of-the-hello-future-apex-"
    "hackathon",
}
# robots.txt and the nine posts, a look first, and room for one failure on each.
REQUEST_LIMIT = 25
SMALL_SITE = SmallSite(SITE, "collect_hedera_posts", REQUEST_LIMIT)
USAGE = "usage: python -m hackathon_memory.collect.hedera_posts --look"

_PATHS = frozenset(urlsplit(url).path for url in POSTS.values())
# A line that starts like a list of the people of a team.
PEOPLE_LINE = re.compile(
    r"^\s*(team members|team|members|built by|created by|developed by|founders?|developers?|"
    r"builders?|creators?|hackers?)\s*[:\-–—]",
    re.IGNORECASE,
)


def is_allowed_url(url: str) -> bool:
    """Only robots.txt and the nine posts, over https, with nothing more in the address."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in HOSTS or parts.query or parts.fragment:
        return False
    if parts.port not in (None, 443) or parts.username or parts.password:
        return False
    path = parts.path.rstrip("/") or "/"
    return path == "/robots.txt" or path in _PATHS


def client_for(settings: Settings, **client_options: object) -> PoliteClient:
    """A polite client that may read robots.txt and the nine posts (small_site.py)."""
    return small_site.client_for(settings, SMALL_SITE, allow=is_allowed_url, **client_options)


def _is_people_line(tag: Tag) -> bool:
    """Its text starts like a list of people, and something follows the label: a <strong>
    that holds only "Team:" is not the line, the paragraph around it with the names is."""
    text = tag.get_text(" ", strip=True)
    match = PEOPLE_LINE.match(text)
    return bool(match) and bool(text[match.end() :].strip())


def people_lines(soup: BeautifulSoup) -> list[Tag]:
    """The smallest elements that hold a whole line that lists the people of a team."""
    found: list[Tag] = []
    for tag in soup.find_all(["p", "li", "span", "div", "h3", "h4", "h5", "h6", "strong", "b"]):
        if not _is_people_line(tag):
            continue
        if any(_is_people_line(inner) for inner in tag.find_all(True)):
            continue  # an element inside it holds the whole line: that one is the line
        found.append(tag)
    return found


def _kind(line: Tag) -> str:
    """The words that make a line a list of people, such as "team" or "built by"."""
    match = PEOPLE_LINE.match(line.get_text(" ", strip=True))
    return match.group(1).lower() if match else ""


def look(client: PoliteClient, say: Callable[[str], None] = print) -> bool:
    """robots.txt, then the first post, kept in memory only, and its shape printed. True if all
    went well. Nothing is saved."""
    event, url = next(iter(POSTS.items()))
    try:
        obey_robots(client, SMALL_SITE, url, say)
        fetched = fetch(client, url, f"the post of {event}")
        say(
            f"--- The post of {event}: status {fetched.status}, {len(fetched.body)} bytes, "
            f"type {fetched.content_type or 'not given'}, final address on "
            f"{urlsplit(fetched.final_url).hostname}. It is not saved."
        )
        soup = BeautifulSoup(fetched.body.decode("utf-8", errors="replace"), "lxml")
        lines = people_lines(soup)
        kinds = Counter(_kind(line) for line in lines)
        shown = ", ".join(f"{kind}: {count}" for kind, count in kinds.most_common())
        say(
            f"Lines that start like a list of people: {len(lines)}"
            + (f" ({shown})" if shown else "")
        )
        say(skeleton(fetched.body))
        return True
    except StopCollecting as stop:
        say(f"STOPPED: {stop}")
        return False
    finally:
        say(count_line(client))


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
