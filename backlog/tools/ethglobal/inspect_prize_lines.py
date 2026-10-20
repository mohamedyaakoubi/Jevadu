"""How a prize line of a page is built from the data of the page. Counts only, no page text.

    .venv/Scripts/python.exe backlog/tools/ethglobal/inspect_prize_lines.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup, Comment

from hackathon_memory.parse.pagedata import objects_with_key, page_data_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"


def squash(text: str) -> str:
    return " ".join(text.split())


shape: Counter[str] = Counter()
first_part: Counter[str] = Counter()
third_part: Counter[str] = Counter()
fourth_part: Counter[str] = Counter()
order: Counter[str] = Counter()
same_names: Counter[str] = Counter()
prize_types: Counter[str] = Counter()
three_parts_place: Counter[str] = Counter()
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
            for h4 in block.find_all("h4") if block else []:
                lines.append(
                    [squash(s) for s in h4.strings if not isinstance(s, Comment) and s.strip()]
                )
    if len(lines) != len(prizes):
        order["a different number of lines and prizes"] += 1
        continue
    in_order = True
    for parts, prize in zip(lines, prizes, strict=True):
        inner = prize.get("prize") or {}
        sponsor = inner.get("sponsor") or {}
        organization = sponsor.get("organization") or {}
        shape[f"{len(parts)} parts, dash second: {len(parts) > 1 and parts[1] in '-‐‑‒–—―'}"] += 1
        prize_types[str(inner.get("type"))] += 1
        same_names["sponsor.name is organization.name"
                   if sponsor.get("name") == organization.get("name")
                   else "sponsor.name is not organization.name"] += 1
        first = parts[0] if parts else ""
        first_part[
            "is sponsor.name and organization.name"
            if first == sponsor.get("name") == organization.get("name")
            else "is organization.name"
            if first == organization.get("name")
            else "is sponsor.name"
            if first == sponsor.get("name")
            else "is neither"
        ] += 1
        if len(parts) >= 3:
            third_part["is prize.name" if parts[2] == squash(str(inner.get("name"))) else "differs"] += 1
            in_order &= parts[2] == squash(str(inner.get("name")))
        if len(parts) >= 4:
            fourth_part["is the place (prizes[].name)" if parts[3] == squash(str(prize.get("name")))
                        else "differs"] += 1
        if len(parts) == 3:
            place = prize.get("name")
            three_parts_place[
                f"place is {'empty or null' if not place else 'given'}, poolPrize {prize.get('poolPrize')}"
            ] += 1
    order["the lines stand in the order of the data" if in_order else "another order"] += 1


def show(title: str, counter: Counter) -> None:
    print(f"{title}:")
    for value, count in counter.most_common(12):
        print(f"  {count:4}  {value}")


print(f"pages: {pages}")
show("lines against prizes, per page", order)
show("the shape of an h4 line", shape)
show("the first part", first_part)
show("the third part", third_part)
show("the fourth part", fourth_part)
show("a line with three parts", three_parts_place)
show("sponsor.name against organization.name", same_names)
show("prize.type", prize_types)
