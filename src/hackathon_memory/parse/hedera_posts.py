"""The winners of Hedera's older hackathons, read from Hedera's own saved posts (design 4.6).

    python -m hackathon_memory.parse.hedera_posts --counts    what each post gives, in numbers

collect/hedera_posts.py saved nine posts of hedera.com, with the lines about people cut out. Each
post was written by hand in its year, and five layouts were found (12 October 2026):

* Hedera20: a heading for each challenge; a winner is a link to the project on the event's
  platform, with its place in bold when a challenge has several; then its text and its prize.
* Hedera21 and Hedera22: a heading for each challenge; after "Winner(s)" or "Runners Up", a
  winner is a line with one link to the project on Devpost.
* Beyond Blockchain 2023: headings "1. Name (Award: $...)", each with the answer of the team to
  "What did you build and why is it important?" or a "Project Summary"; then "Best in Track"
  lines "Track : Name ($...)".
* Hello Future 2024 and 2.0: "1st Place: Name" for the overall winners; then a label for each
  track and a list of lines that start with the name in bold.
* Hello Future Origins, Ascension and Apex: a heading for each track, and "1st Place – Name"
  under it, then the prize, the text, and a link.

Each winner becomes a winner entry (winner_entries.py): the name, the event, the track or
challenge, the place when the post gives one, and the text as published. A project that won
twice in one post is one entry with both tracks. The page of the project on the event's
platform (BeMyApp, Devpost, DoraHacks) is kept as a link for a person to open; no program asks
for it.

Left out, and counted: a line that is only a name with no text about a project, because such a
list may name people; a line that lists several projects at once; and a winner whose name is
the name of a person, until the maintainer decides. Such names are listed by hand in
data/by-hand/hedera.com/names-of-people.sha256, as fingerprints (sha256 of the name in small
letters), so that the list itself holds no name.
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from hackathon_memory.collect.hedera_posts import POSTS, SITE
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.parse.project import WINNER_ENTRY
from hackathon_memory.parse.winner_entries import (
    WinnerEntriesError,
    WinnerEntry,
    entries_from_records,
)
from hackathon_memory.settings import Settings

PLATFORMS = ("bemyapp.com", "devpost.com", "dorahacks.io")
NAMES_OF_PEOPLE = "names-of-people.sha256"
_BEFORE_WORDS = re.compile(r"^[\W_]+")  # an emoji or a mark before the first word
_PLACE = re.compile(r"^(\d)(?:st|nd|rd|th)\s+place\s*[:–—-]\s*(.+)$", re.IGNORECASE)
_NUMBERED = re.compile(r"^(\d)\.\s+(.+?)\s*\(award:\s*([^)]+)\)\s*$", re.IGNORECASE)
_BEST = re.compile(r"^(.+?)\s+:\s+(.+?)\s*\(([^)]+)\)\s*$")
_PRIZE_LINE = re.compile(r"^(prizes?|\d(?:st|nd|rd|th)\s+place\s+prize)\b", re.IGNORECASE)
_LABEL = re.compile(r"^(winners?|runners?[- ]?ups?|prizes?)\s*[:–—-]?\s*$", re.IGNORECASE)
_QUESTION = re.compile(r"\?\s*$|^project (summary|description|demo)\s*:?$", re.IGNORECASE)
_END = re.compile(r"^(what.s next|closing|thank you|conclusion|continue learning)", re.IGNORECASE)
_GROUPS = {"results and winners", "overall winners", "track winners", "placed prizes"}
_HEADINGS = ("h2", "h3", "h4")


def _text(tag: Tag) -> str:
    return _BEFORE_WORDS.sub("", re.sub(r"\s+", " ", tag.get_text(" ", strip=True))).strip()


def _ordinal(digit: str) -> str:
    return digit + {"1": "st", "2": "nd", "3": "rd"}.get(digit, "th") + " place"


def _platform_links(tag: Tag) -> list[Tag]:
    return [
        link
        for link in tag.find_all("a", href=True)
        if any((urlsplit(str(link["href"])).hostname or "").endswith(p) for p in PLATFORMS)
    ]


def _points_elsewhere(tag: Tag) -> bool:
    """A line that only sends the reader to a link: "... here", "Click here for the demo"."""
    words = [_text(link).lower() for link in tag.find_all("a")]
    return any(word in ("here", "here.") or word.startswith("click here") for word in words)


@dataclass
class Found:
    winners: list[dict] = field(default_factory=list)
    skipped: Counter[str] = field(default_factory=Counter)

    def add(
        self,
        name: str,
        track: str,
        place: str,
        text: str,
        link: str | None,
        *,
        described: bool = True,  # False when `text` is only the winner's own line
    ) -> None:
        self.winners.append(
            {
                "name": name.strip(),
                "track": track,
                "place": place,
                "text": text,
                "link": link,
                "described": described,
            }  # fmt: skip
        )


def fingerprint(name: str) -> str:
    """How a name stands in the list of names of people: its sha256, in small letters."""
    return hashlib.sha256(name.strip().casefold().encode("utf-8")).hexdigest()


def _until_prize(start: Tag, text: str) -> str:
    """A winner's line, and the lines after it up to a heading, another winner or its prize."""
    parts = [text]
    for sibling in start.find_next_siblings():
        if sibling.name in _HEADINGS or _platform_links(sibling) or _PLACE.match(_text(sibling)):
            break
        line = _text(sibling)
        if _PRIZE_LINE.match(line):
            break
        if line and not _QUESTION.search(line):
            parts.append(line)
    return " ".join(parts)


# --------------------------------------------------------------------- the five layouts


def _hedera20(content: Tag) -> Found:
    found = Found()
    track = place = ""
    for tag in content.find_all(["h4", "p"]):
        text = _text(tag)
        if tag.name == "h4":
            track, _, place = text.partition(" – ")
            if not re.search(r"place$", place, re.IGNORECASE):
                track, place = text, ""  # "Hedera Consensus Service – First Place" has one
            continue
        links = _platform_links(tag)
        if links:
            here = re.search(r"\b(\d(?:st|nd|rd|th)\s+place)\b", text, re.IGNORECASE)
            found.add(_text(links[0]), track, here.group(1) if here else place,
                      _until_prize(tag, text), str(links[0]["href"]))  # fmt: skip
    return found


def _devpost(content: Tag) -> Found:
    found = Found()
    track, place = "", ""
    for tag in content.find_all(["h4", "p"]):
        text = _text(tag)
        if tag.name == "h4":
            track = text
            place = "Winner" if re.search(r"\bwinners\b", text, re.IGNORECASE) else ""
            continue
        label = _LABEL.match(text)
        if label:
            word = label.group(1).lower()
            place = "Winner" if word.startswith("winner") else "Runner-up" * word.startswith("run")
            continue
        links = _platform_links(tag)
        if not place or not links:
            continue
        if len(links) > 1:
            found.skipped["a line that lists several projects"] += 1
            continue
        grand = re.match(r"^grand prize\b", text, re.IGNORECASE)
        found.add(_text(links[0]), track, "Grand Prize" if grand else place, text,
                  str(links[0]["href"]))  # fmt: skip
    return found


def _answer_after(tags: list[Tag], at: int) -> str:
    """The answer about the project after a winner: the lines after its first question
    ("What did you build...?", "Project Summary"), up to the next question, heading or winner."""
    parts: list[str] = []
    taking = False
    for tag in tags[at + 1 :]:
        text = _text(tag)
        if tag.name == "h4" or _BEST.match(text):
            break
        if not text:
            continue
        if _QUESTION.search(text):
            if parts:
                break  # the second question is about the hackathon, not about the project
            taking = True
        elif taking:
            parts.append(text)
    return " ".join(parts)


def _beyond_blockchain(content: Tag) -> Found:
    found = Found()
    section = ""
    tags = content.find_all(["h4", "p"])
    for at, tag in enumerate(tags):
        text = _text(tag)
        if tag.name == "h4":
            numbered = _NUMBERED.match(text)
            if numbered:
                place = f"{_ordinal(numbered.group(1))}, {numbered.group(3).strip()}"
                answer = _answer_after(tags, at)
                found.add(numbered.group(2), "Placed Prizes", place, answer or text, None,
                          described=bool(answer))  # fmt: skip
            section = text.lower()
            continue
        best = _BEST.match(text) if section == "best in track" else None
        if best:
            answer = _answer_after(tags, at)
            found.add(best.group(2), best.group(1), f"Best in Track, {best.group(3)}",
                      answer or text, None, described=bool(answer))  # fmt: skip
    return found


def _bold_start(tag: Tag) -> str:
    """The words in bold at the start of a line, such as "OsmiumLabs:", or "" if it has none."""
    bold = ""
    for child in tag.children:
        piece = child.get_text("", strip=False) if isinstance(child, Tag) else str(child)
        if isinstance(child, Tag) and child.name in ("strong", "b"):
            bold += piece
        elif not bold.strip() and not re.search(r"\w", piece):
            continue  # an emoji or a mark before the name, as in the posts of Hello Future
        else:
            break
    return _BEFORE_WORDS.sub("", bold).strip()


def _is_label(tag: Tag, text: str) -> bool:
    """A short line all in bold, such as the name of a track."""
    return tag.name == "p" and 0 < len(text) <= 80 and _bold_start(tag) == text


def _hello_future(content: Tag) -> Found:
    found = Found()
    track = ""
    for tag in content.find_all(["h4", "p", "li"]):
        text = _text(tag)
        if not text:
            continue
        if tag.name == "h4" and _END.match(text):
            break
        place = _PLACE.match(text)
        if place and tag.name in ("h4", "p") and len(text) <= 80:
            found.add(place.group(2), "Overall", _ordinal(place.group(1)),
                      _until_prize(tag, text), None)  # fmt: skip
            continue
        if tag.name == "h4" or _is_label(tag, text):
            if text.lower() not in _GROUPS:
                track = text
            continue
        if tag.find_parent("ul") or not track:
            continue  # the prize under an overall winner, or a line before the first track
        name = _bold_start(tag).rstrip(" :")
        if not name:
            if tag.name == "p" and track and len(text) <= 40 and not tag.find("a"):
                found.skipped["a line that is only a name"] += 1
            continue
        if not text[len(_bold_start(tag)) :].strip(" :"):
            found.skipped["a line that is only a name"] += 1
            continue
        found.add(name, track, "", text, None)
    return found


def _placed(content: Tag) -> Found:
    found = Found()
    track = ""
    for heading in content.find_all(_HEADINGS):
        text = _text(heading)
        place = _PLACE.match(text)
        if not place:
            if _END.match(text):
                break
            track = text
            continue
        name = re.split(r"\s+[–—-]\s+", place.group(2), maxsplit=1)[0]
        parts: list[str] = []
        link: str | None = None
        for sibling in heading.find_next_siblings():
            if sibling.name in _HEADINGS:
                break
            links = _platform_links(sibling)
            if links and link is None:
                link = str(links[0]["href"])
            line = _text(sibling)
            if line and not (_PRIZE_LINE.match(line) or _QUESTION.search(line)
                             or _points_elsewhere(sibling)):  # fmt: skip
                parts.append(line)
        found.add(name, track, _ordinal(place.group(1)), " ".join(parts) or text, link)
    return found


LAYOUTS: dict[str, Callable[[Tag], Found]] = {
    "Hedera20": _hedera20,
    "Hedera21": _devpost,
    "Hedera22": _devpost,
    "Beyond Blockchain 2023": _beyond_blockchain,
    "Hello Future 2024": _hello_future,
    "Hello Future 2.0": _hello_future,
    "Hello Future Origins": _placed,
    "Hello Future Ascension": _placed,
    "Hello Future Apex": _placed,
}


# --------------------------------------------------------------------- the entries


def winners_of(event: str, html: bytes) -> Found:
    """The winners of one saved post, by the layout of its event."""
    content = BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml").select_one(
        ".blog-post-content"
    )
    if content is None:
        raise WinnerEntriesError(f"the post of {event} has no block of content")
    return LAYOUTS[event](content)


def _names_of_people(path: Path) -> set[str]:
    """The fingerprints of the names of people, one in each line; "#" starts a comment."""
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.strip().lower() for line in lines if line.strip() and not line.startswith("#")}


def records_of(event: str, url: str, found: Found, people: set[str]) -> list[dict]:
    """One record of a winner entry for each project of a post. A project that won twice keeps
    its tracks and places together, and a text that describes it rather than its line alone."""
    merged: dict[str, dict] = {}
    described: set[str] = set()
    for winner in found.winners:
        key = winner["name"].casefold()
        if fingerprint(winner["name"]) in people:
            found.skipped["a winner named after a person (listed by hand)"] += 1
            continue
        record = merged.setdefault(
            key,
            {
                "kind": WINNER_ENTRY,
                "name": winner["name"],
                "event": event,
                "tracks": [],
                "places": [],
                "organiser": "Hedera",
                "description_as_published": "",
                "source_url": url,
                "project_page": "",
            },
        )
        record["tracks"].append(winner["track"])
        record["places"].append(winner["place"])
        better = winner["described"] and key not in described
        if better or not record["description_as_published"]:
            record["description_as_published"] = winner["text"]
            if winner["described"]:
                described.add(key)
        record["project_page"] = record["project_page"] or winner["link"] or ""
    records = []
    for record in merged.values():
        record["track"] = " and ".join(t for t in dict.fromkeys(record.pop("tracks")) if t)
        record["place"] = "; ".join(p for p in dict.fromkeys(record.pop("places")) if p)
        records.append(record)
    return records


def read_hedera_posts(raw_dir: Path, by_hand: Path) -> list[WinnerEntry]:
    """The winner entries of every saved post. A post that is not saved gives none."""
    store = RawStore(raw_dir)
    people = _names_of_people(by_hand / NAMES_OF_PEOPLE)
    entries: list[WinnerEntry] = []
    for event, url in POSTS.items():
        saved = store.load(url)
        if saved is None:
            continue
        records = records_of(event, url, winners_of(event, saved.read()), people)
        entries += entries_from_records(records, site=SITE, source=f"the post of {event}")
    return entries


def main(argv: list[str]) -> int:
    if argv != ["--counts"]:
        print("usage: python -m hackathon_memory.parse.hedera_posts --counts")
        return 2
    data = Path(Settings().data_dir)
    store = RawStore(data / "raw" / SITE)
    people = _names_of_people(data / "by-hand" / SITE / NAMES_OF_PEOPLE)
    for event, url in POSTS.items():
        saved = store.load(url)
        if saved is None:
            print(f"{event}: not saved")
            continue
        found = winners_of(event, saved.read())
        records = records_of(event, url, found, people)
        left = ", ".join(f"{why}: {n}" for why, n in found.skipped.most_common()) or "nothing"
        print(f"{event}: {len(found.winners)} winner lines, {len(records)} projects; left out: "
              f"{left}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
