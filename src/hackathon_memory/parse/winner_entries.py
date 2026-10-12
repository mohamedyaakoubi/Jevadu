"""Winner entries: the projects of an event whose submissions are not public (design 4.6).

For such an event, the only thing left is the organiser's list of winners. A person copied it by
hand into data/by-hand/<site>/<name>.entries.json: one record for each winner, with its name,
its event, its track, its place, the description as the organiser published it, and the address
of the page. A small file next to it says where and how it was copied.

A winner entry is a thin card: the name, the event, the track, the prize, the description as it
was published, and its source. It has ledger facts only when its description gives an id. Most
do not. Each entry becomes a project of the kind "winner_entry". Its address is the address of
the page with a "#" and the name of the project, so that two winners of one page are two
projects. Words about people are hidden in the description, as in any text (people.py).

A record that lacks what a card needs refuses the whole file, with the number of the record: a
file read in part would leave some winners out with no sign of it.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from hackathon_memory.parse.blocks import PARAGRAPH, Block, squash
from hackathon_memory.parse.hedera_ids import find_ids
from hackathon_memory.parse.people import hide_in_text
from hackathon_memory.parse.project import (
    HEDERA_PRIZE,
    WINNER_ENTRY,
    EventRef,
    Prize,
    ProjectPage,
    Section,
)

PARSER_VERSION = "winner-entries-1"
SUFFIX = ".entries.json"
AS_PUBLISHED = "as_published"  # the kind of the one text of a winner entry
_REQUIRED = ("name", "event", "source_url", "description_as_published")


class WinnerEntriesError(ValueError):
    """A file of winner entries cannot be read. The message names the record, not its text."""


@dataclass(frozen=True)
class WinnerEntry:
    page: ProjectPage
    sha256: str  # the fingerprint of the record, so that a changed record is read again


def slug(text: str) -> str:
    """Small letters and digits, joined by dashes: "Hedera x AI 2025" is "hedera-x-ai-2025"."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def read_entries(path: Path) -> list[WinnerEntry]:
    """Every winner of one file, as projects of the kind "winner_entry"."""
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise WinnerEntriesError(f"{path.name} cannot be read as JSON") from error
    return entries_from_records(records, site=path.parent.name, source=path.name)


def entries_from_records(records: object, *, site: str, source: str) -> list[WinnerEntry]:
    """Every winner of a list of records, as projects of the kind "winner_entry". `source`
    names the list in an error."""
    if not isinstance(records, list):
        raise WinnerEntriesError(f"{source} is not a list of records")
    entries: list[WinnerEntry] = []
    for number, record in enumerate(records, start=1):
        if not isinstance(record, dict) or record.get("kind") != WINNER_ENTRY:
            raise WinnerEntriesError(f"{source}, record {number}: not a winner entry")
        missing = [key for key in _REQUIRED if not str(record.get(key) or "").strip()]
        if not missing and not str(record["source_url"]).startswith("https://"):
            missing = ["source_url"]
        if missing:
            raise WinnerEntriesError(
                f"{source}, record {number}: missing or wrong: {', '.join(missing)}"
            )
        entry = _entry(site, record)
        if any(other.page.page == entry.page.page for other in entries):
            raise WinnerEntriesError(f"{source}, record {number}: a second winner of that name")
        entries.append(entry)
    return entries


def _entry(site: str, record: dict) -> WinnerEntry:
    name = squash(str(record["name"]))
    event = squash(str(record["event"]))
    track = squash(str(record.get("track") or ""))
    place = squash(str(record.get("place") or record.get("result_as_published") or ""))
    organiser = squash(str(record.get("organiser") or "Hedera"))
    description, hidden = hide_in_text(squash(str(record["description_as_published"])))
    line = " - ".join(part for part in (organiser, track, place) if part)
    page = ProjectPage(
        site=site,
        page=f"{record['source_url']}#{slug(name)}",
        site_key=slug(name),
        name=name,
        short_line="",
        event=EventRef(site=site, slug=slug(event), name=event, starts_at=None),
        prizes=(
            Prize(
                sponsor=organiser,
                sponsor_id=None,
                track=track,
                award=place,
                kind=None,
                pool=False,
                line=line,
            ),
        ),
        prize_state=HEDERA_PRIZE,  # a prize in a hackathon of Hedera
        links=(),
        sections=(Section(AS_PUBLISHED, "As published", (Block(PARAGRAPH, description),)),),
        hedera_ids=tuple(find_ids(description)),
        has_video=False,
        parser=PARSER_VERSION,
        people_words_hidden=hidden,
        entry_kind=WINNER_ENTRY,
    )
    fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    return WinnerEntry(page, fingerprint)


def entry_files(folder: Path) -> list[Path]:
    """The files of winner entries in the folder of things typed or copied by hand."""
    return sorted(folder.glob(f"*/*{SUFFIX}"))
