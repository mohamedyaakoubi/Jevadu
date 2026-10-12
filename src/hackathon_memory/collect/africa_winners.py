"""The page with the winners of the Hedera Africa hackathon: one page, read by a small collector.

    python -m hackathon_memory.collect.africa_winners --look    2 requests, nothing saved
    python -m hackathon_memory.collect.africa_winners --read    the page and its winners, saved

The maintainer said yes for this one page on 10 October 2026 (design rule 17). Its winners become
winner entries (design 4.6). The site has no robots.txt (it answers 404) and shows no terms of
use (seen on 11 October 2026). It is read the way design 5.7 promises for every site:

* one request at a time, with a pause, and the name of the tool and the maintainer's address in
  each request;
* its own switch in .env, COLLECT_AFRICA_WINNERS, off unless the maintainer turns it on, and read
  again before every request;
* its own count of requests on disk, with a small limit, and a refusal remembered;
* only the page, its robots.txt, and the script files that the page itself loads from its own
  site. Its links lead to DoraHacks, and no program follows them (design 5.6).

The look keeps the page in memory and prints its SHAPE with the skeleton printer: no text, no
name, no link target beyond its shape, and the keys of its data with their counts.

The look showed that the page holds the winners of its first track only; its own scripts show
the other tracks. On 12 October 2026 the maintainer allowed the read to take the script files
that the page loads from its own site, each once and at most five ("option 1"). The read stops
at the first file that holds more winner links than the page, and saves that file next to the
page. Before it is saved, the literal value of every key that can name a person (team, members,
founders, handles...) is emptied and every email address is cut (design rule 5). If no file
holds the winners, nothing is saved, and the winners are copied by hand instead.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from hackathon_memory.collect import small_site
from hackathon_memory.collect.polite import CollectorRefused, PoliteClient, StopCollecting
from hackathon_memory.collect.rawstore import RawStore, SavedPage
from hackathon_memory.collect.skeleton import skeleton
from hackathon_memory.collect.small_site import SmallSite, count_line, fetch, obey_robots
from hackathon_memory.parse.jsdata import NotALiteral, objects_holding, read_literal
from hackathon_memory.parse.pagedata import page_data_text
from hackathon_memory.settings import Settings

SITE = "hedera-hackathon.hashgraph.swiss"
PAGE = f"https://{SITE}/"
ROBOTS_URL = f"https://{SITE}/robots.txt"
# Two looks, then a read: robots.txt, the page and at most five script files.
REQUEST_LIMIT = 10
SCRIPT_LIMIT = 5  # the maintainer's yes of 12 October 2026
USAGE = "usage: python -m hackathon_memory.collect.africa_winners --look | --read"
SMALL_SITE = SmallSite(SITE, "collect_africa_winners", REQUEST_LIMIT)

# The address of a winner's project page. No program asks for it.
WINNER_LINK = re.compile(r"https://dorahacks\.io/[^\s\"'`<>\\)]+")
# A script file of the page, as the data of the page names it.
_CHUNK = re.compile(r"(?:/_next/)?static/chunks/[^\"'\s\\]+?\.js")
# A key whose literal value can name or reach a person, with or without quotes around it.
PEOPLE_KEY = re.compile(
    r"(?<![\w$.])[\"']?(team|teams|members?|team_?members|founders?|authors?|builders?|people|"
    r"creators?|contributors?|participants?|hackers?|twitter|linkedin|telegram|discord|"
    r"e_?mail|handles?|socials?|avatars?|photos?)[\"']?\s*:(?!:)",
    re.IGNORECASE,
)
_ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.([A-Za-z]{2,24})\b")
_FILE_ENDINGS = frozenset(
    {"png", "jpg", "jpeg", "svg", "webp", "gif", "avif", "ico", "js", "css", "json", "woff",
     "woff2", "ttf", "mp4", "webm"}
)  # fmt: skip
_SPACE = re.compile(r"\s*")
_MEMBER_BLOCK = re.compile(r"team|member", re.IGNORECASE)


def is_allowed_url(url: str) -> bool:
    """Only the page and its robots.txt, over https, with nothing more in the address."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != SITE or parts.query or parts.fragment:
        return False
    if parts.port not in (None, 443) or parts.username or parts.password:
        return False
    return parts.path in ("", "/", "/robots.txt")


class AllowedUrls:
    """The page and its robots.txt, and the script files that are named once the page is read."""

    def __init__(self) -> None:
        self.scripts: set[str] = set()

    def __call__(self, url: str) -> bool:
        return is_allowed_url(url) or url in self.scripts


@dataclass(frozen=True)
class Paths:
    raw_dir: Path
    request_count: Path


def paths(settings: Settings) -> Paths:
    return Paths(
        raw_dir=Path(settings.data_dir) / "raw" / SITE,
        request_count=small_site.request_count_path(settings, SITE),
    )


def client_for(
    settings: Settings,
    *,
    env_file: Path | None = None,
    allow: Callable[[str], bool] = is_allowed_url,
    **client_options: object,
) -> PoliteClient:
    """A polite client that may read what `allow` names, and nothing else (small_site.py)."""
    return small_site.client_for(
        settings, SMALL_SITE, allow=allow, env_file=env_file, **client_options
    )


# --------------------------------------------------------------------- the look


def look(client: PoliteClient, say: Callable[[str], None] = print) -> bool:
    """robots.txt, then the page, kept in memory only, and its shape printed. True if all went
    well. Nothing is saved."""
    try:
        obey_robots(client, SMALL_SITE, PAGE, say)
        fetched = fetch(client, PAGE, "the page")
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
        say(count_line(client))


# --------------------------------------------------------------------- the read


def script_sources(html: bytes) -> list[str]:
    """The script files that the page loads from its own site, at most SCRIPT_LIMIT: first the
    ones that the data of the page names (the parts that run in the browser), then the script
    tags. A script for old browsers (nomodule) is left out, and one file is taken once, whatever
    follows its "?"."""
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml")
    named = ["/_next/" + found.removeprefix("/_next/") for found in _CHUNK.findall(
        page_data_text(soup))]  # fmt: skip
    tags = [str(tag["src"]) for tag in soup.find_all("script", src=True)
            if not tag.has_attr("nomodule")]  # fmt: skip
    sources: list[str] = []
    seen: set[str] = set()
    for written in (*named, *tags):
        url = urljoin(PAGE, written)
        parts = urlsplit(url)
        own = parts.scheme == "https" and parts.hostname == SITE and parts.port in (None, 443)
        script = parts.path.startswith("/_next/static/") and parts.path.endswith(".js")
        if own and script and not parts.fragment and parts.path not in seen:
            seen.add(parts.path)
            sources.append(url)
    return sources[:SCRIPT_LIMIT]


def shows_members(html: bytes) -> bool:
    """True when an element of the page is named for a team or its members."""
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml")
    for tag in soup.find_all(True):
        names = [*tag.get("class", []), str(tag.get("id", ""))]
        if any(_MEMBER_BLOCK.search(name) for name in names if name):
            return True
    return False


def cut_people(text: str) -> tuple[str, Counter[str]]:
    """The script with the literal value of every key about people emptied, and every email
    address cut. Returns the text and what was cut, by kind."""
    counts: Counter[str] = Counter()
    cuts: list[tuple[int, int, str]] = []
    for match in PEOPLE_KEY.finditer(text):
        begin = _SPACE.match(text, match.end()).end()  # type: ignore[union-attr]
        try:
            value, end = read_literal(text, begin)
        except NotALiteral:
            continue  # code, not data: nothing to cut
        empty = {str: '""', list: "[]", dict: "{}"}.get(type(value))
        if empty is None or not value:
            continue
        cuts.append((begin, end, empty))
        counts[match.group(1).lower()] += 1
    kept: list[tuple[int, int, str]] = []
    for cut in sorted(cuts):
        if not kept or cut[0] >= kept[-1][1]:  # a cut inside a cut is done already
            kept.append(cut)
    for begin, end, empty in reversed(kept):
        text = text[:begin] + empty + text[end:]

    def address(match: re.Match[str]) -> str:
        if match.group(1).lower() in _FILE_ENDINGS:
            return match.group(0)  # a file such as logo@2x.png
        counts["address"] += 1
        return "address-cut"

    return _ADDRESS.sub(address, text), counts


@dataclass(frozen=True)
class Read:
    page: SavedPage
    script: SavedPage
    winners: int
    keys: Counter[str]
    cut: Counter[str]


def read_and_save(
    client: PoliteClient,
    allowed: AllowedUrls,
    store: RawStore,
    say: Callable[[str], None] = print,
) -> Read | None:
    """The page and the script file that holds its winners, both saved. None if they are not."""
    if store.load(PAGE) is not None:
        say("The page is saved already, and it is never asked for twice: nothing is sent.")
        return None
    try:
        obey_robots(client, SMALL_SITE, PAGE, say)
        page = fetch(client, PAGE, "the page")
        if shows_members(page.body):
            raise StopCollecting("the page shows a block about a team or its members: nothing "
                                 "is saved, and the cut must be written first")  # fmt: skip
        on_page = set(WINNER_LINK.findall(page.body.decode("utf-8", errors="replace")))
        sources = script_sources(page.body)
        allowed.scripts.update(sources)
        say(f"The page shows {len(on_page)} winner link(s). Script files to try: {len(sources)}.")
        for number, url in enumerate(sources, start=1):
            script = fetch(client, url, f"script file {number}")
            text = script.body.decode("utf-8", errors="replace")
            links = set(WINNER_LINK.findall(text))
            if len(links) <= len(on_page) or not links & on_page:
                say(f"Script file {number}: {len(links)} winner link(s), not the winners.")
                continue
            winners = objects_holding(text, WINNER_LINK)
            if not winners:
                raise StopCollecting(
                    f"script file {number} holds {len(links)} winner links, but not as data "
                    "that can be read: nothing is saved"
                )
            body, cut = cut_people(text)
            keys = Counter(key for found in winners for key in found.value)
            collector = f"{client.identity.name}/{client.identity.version}"
            saved_page = store.save(page, page.body, received=page.body, collector=collector,
                                    team_cut={"members_on_the_page": 0})  # fmt: skip
            saved_script = store.save(
                script,
                body.encode("utf-8") if cut else script.body,
                received=script.body,
                collector=collector,
                team_cut={"people_values_cut": dict(cut)},
                suffix=".js",
            )
            say(
                f"Script file {number}: {len(links)} winner links, in {len(winners)} records. "
                "Saved, with the page."
            )
            say("The keys of the records (key: count, never a value): "
                + ", ".join(f"{key}: {count}" for key, count in keys.most_common()))  # fmt: skip
            say("Cut out before saving: "
                + (", ".join(f"{kind}: {count}" for kind, count in cut.most_common())
                   or "nothing"))  # fmt: skip
            return Read(saved_page, saved_script, len(winners), keys, cut)
        raise StopCollecting(
            f"none of the {len(sources)} script files holds the winners: nothing is saved. They "
            "can be copied by hand instead."
        )
    except StopCollecting as stop:
        say(f"STOPPED: {stop}")
        return None
    finally:
        say(count_line(client))


def main(argv: list[str]) -> int:
    if argv not in (["--look"], ["--read"]):
        print(USAGE)
        return 2
    settings = Settings()
    allowed = AllowedUrls()
    try:
        client = client_for(settings, allow=allowed)
    except CollectorRefused as refusal:
        print(f"Refused: {refusal}")
        return 1
    if argv == ["--look"]:
        return 0 if look(client) else 2
    read = read_and_save(client, allowed, RawStore(paths(settings).raw_dir))
    return 0 if read is not None else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
