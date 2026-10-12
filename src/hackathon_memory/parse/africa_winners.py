"""The winners of the Hedera Africa hackathon, read from its saved winners page (design 4.6).

The page and the script file that holds its winners were saved by collect/africa_winners.py. The
script keeps its data as JavaScript: a list of the tracks (`{id:"cross",label:"Cross-Track"}`) and
a map from each track to its winners (`{onchain:[{title, logo, buidlUrl, description}, ...]}`).
The logo is code, not data, and is passed over (jsdata.py). A winner of the Cross-Track also
stands in its own track: it is one project, with both tracks, its own track first. The page gives
no place inside a track.

Each winner becomes a winner entry, like the ones copied by hand: a thin card that points to the
saved page, and that keeps the address of the project's page on DoraHacks for a person to open.
No program asks for that address (design 5.6).

Read on the files saved on 12 October 2026.
"""

from __future__ import annotations

import re
from pathlib import Path

from hackathon_memory.collect.africa_winners import PAGE, SITE, WINNER_LINK
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.parse.jsdata import (
    NotALiteral,
    enclosing_object,
    objects_holding,
    read_object,
)
from hackathon_memory.parse.project import WINNER_ENTRY
from hackathon_memory.parse.winner_entries import (
    WinnerEntriesError,
    WinnerEntry,
    entries_from_records,
)

EVENT = "Hedera Africa Hackathon 2025"
CROSS_TRACK = "cross"  # the track of the projects recognized across several tracks
SOURCE = "the saved winners page of the Africa hackathon"
_TRACK = re.compile(r"\{\s*id\s*:")


def _track_labels(script: str, ids: set[str]) -> dict[str, str]:
    """The label of each track, in the order of the page's tabs."""
    labels: dict[str, str] = {}
    for match in _TRACK.finditer(script):
        try:
            found = read_object(script, match.start(), lenient=True).value
        except NotALiteral:
            continue
        track, label = found.get("id"), found.get("label")
        if isinstance(track, str) and track in ids and isinstance(label, str):
            labels.setdefault(track, label.strip())
    return labels


def winner_records(script: str) -> list[dict]:
    """One record of a winner entry for each winning project, in the order of the tracks."""
    winners = objects_holding(script, WINNER_LINK, lenient=True)
    if not winners:
        raise WinnerEntriesError(f"{SOURCE}: no winner in the saved script")
    grouped = enclosing_object(script, winners[0], lenient=True)
    if grouped is None or not all(isinstance(v, list) for v in grouped.value.values()):
        raise WinnerEntriesError(f"{SOURCE}: the winners are not grouped by track")
    labels = _track_labels(script, set(grouped.value))
    tabs = [track for track in labels if track in grouped.value]
    tabs += [track for track in grouped.value if track not in tabs]
    by_link: dict[str, dict] = {}
    for track in tabs:
        for number, winner in enumerate(grouped.value[track], start=1):
            link = winner.get("buidlUrl") if isinstance(winner, dict) else None
            if not isinstance(link, str) or not WINNER_LINK.fullmatch(link):
                raise WinnerEntriesError(f"{SOURCE}, track {track}, winner {number}: no link")
            record = by_link.setdefault(
                link,
                {
                    "kind": WINNER_ENTRY,
                    "name": str(winner.get("title") or ""),
                    "event": EVENT,
                    "tracks": [],
                    "organiser": "Hedera",
                    "description_as_published": str(winner.get("description") or ""),
                    "source_url": PAGE,
                    "project_page": link,
                },
            )
            record["tracks"].append(track)
    records = []
    for record in by_link.values():
        own_first = sorted(record.pop("tracks"), key=lambda track: track == CROSS_TRACK)
        record["track"] = " and ".join(labels.get(track, track) for track in own_first)
        records.append(record)
    return records


def read_africa_winners(raw_dir: Path) -> list[WinnerEntry]:
    """The winner entries of the saved page, or none when the page was not saved yet."""
    store = RawStore(raw_dir)
    if store.load(PAGE) is None:
        return []
    scripts = store.saved(suffix=".js")
    if len(scripts) != 1:
        raise WinnerEntriesError(f"{SOURCE}: one saved script was expected, {len(scripts)} found")
    script = scripts[0].read().decode("utf-8")
    return entries_from_records(winner_records(script), site=SITE, source=SOURCE)
