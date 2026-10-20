"""Which words of the data make the visible line of a prize. Counts only, no page text.

    .venv/Scripts/python.exe backlog/tools/ethglobal/inspect_prize_text.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

from hackathon_memory.parse.pagedata import objects_with_key, page_data_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"


def squash(text: str) -> str:
    return " ".join(text.split())


made_of: Counter[str] = Counter()
by_type: Counter[str] = Counter()
award_is_track: Counter[str] = Counter()
pages = 0

for body_path in sorted(RAW.glob("*.html")):
    soup = BeautifulSoup(body_path.read_bytes().decode("utf-8", errors="replace"), "lxml")
    objects = [o for o in objects_with_key(page_data_text(soup), "tagline") if "slug" in o]
    if not objects:
        continue
    pages += 1
    prizes = objects[0].get("prizes") or []
    lines = []
    for h3 in soup.find_all("h3"):
        if squash(h3.get_text()).lower() == "winner of":
            block = h3.find_next_sibling()
            lines.extend(squash(h4.get_text(" ")) for h4 in (block.find_all("h4") if block else []))
    if len(lines) != len(prizes):
        made_of["a different number of lines and prizes"] += 1
        continue
    for line, prize in zip(lines, prizes, strict=True):
        inner = prize.get("prize") or {}
        sponsor = squash(str((inner.get("sponsor") or {}).get("name")))
        track = squash(str(inner.get("name")))
        award = squash(str(prize.get("name")))
        kind = str(inner.get("type"))
        shapes = {
            "sponsor - track": f"{sponsor} - {track}",
            "sponsor - track award": f"{sponsor} - {track} {award}",
            "sponsor - award": f"{sponsor} - {award}",
            "sponsor - award track": f"{sponsor} - {award} {track}",
        }
        fits = [name for name, text in shapes.items() if text == line]
        label = fits[0] if fits else "none of these"
        made_of[label] += 1
        by_type[f"type {kind}, pool {prize.get('poolPrize')}: {label}"] += 1
        award_is_track[f"type {kind}: award " + ("is" if award == track else "is not") + " the track name"] += 1

print(f"pages: {pages}")
for title, counter in (
    ("the visible line is made of", made_of),
    ("by the type of the prize", by_type),
    ("the award against the name of the track", award_is_track),
):
    print(f"{title}:")
    for value, count in counter.most_common():
        print(f"  {count:4}  {value}")
