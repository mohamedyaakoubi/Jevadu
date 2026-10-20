"""Find the shape that makes the text blocks change the order of the letters. No text is printed.

For each text whose blocks hold the same letters in another order, it prints the tags around
the place where the order changes: tag names, and the length of each text only.

    .venv/Scripts/python.exe backlog/tools/ethglobal/find_reorder.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from hackathon_memory.parse.blocks import blocks_of, plain_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"
TITLES = ("project description", "how it's made")


def letters(text: str) -> str:
    return "".join(text.split())


def shape(tag: Tag, depth: int = 0, limit: int = 4) -> list[str]:
    """The tags under `tag`, with the length of their own text."""
    lines = []
    own = sum(len(s.strip()) for s in tag.children if type(s) is NavigableString)
    lines.append("  " * depth + f"{tag.name} (own text {own})")
    if depth < limit:
        for child in tag.children:
            if isinstance(child, Tag):
                lines.extend(shape(child, depth + 1, limit))
    return lines


for body_path in sorted(RAW.glob("*.html")):
    soup = BeautifulSoup(body_path.read_bytes().decode("utf-8", errors="replace"), "lxml")
    for heading in soup.find_all("h3"):
        if " ".join(heading.get_text().split()).lower() not in TITLES:
            continue
        box = heading.find_next_sibling()
        made = letters(plain_text(blocks_of(box)))
        page = letters(box.get_text())
        if made == page:
            continue
        at = next(i for i, (a, b) in enumerate(zip(made, page, strict=False)) if a != b)
        print(f"a text where the order changes, first at letter {at} of {len(page)}")
        # The element of the box whose text holds that letter of the page.
        count = 0
        for element in box.descendants:
            if type(element) is NavigableString:
                count += len(letters(str(element)))
                if count > at:
                    path = [p.name for p in reversed(list(element.parents)) if p is not None]
                    start = path.index(box.name) if box.name in path else 0
                    print("  the letter stands in:", " > ".join(path[start:]))
                    holder = element.parent
                    while holder is not None and holder.name not in ("li", "p", "td", "pre"):
                        holder = holder.parent
                    if holder is not None:
                        print("  the shape of its nearest block:")
                        print("\n".join("    " + line for line in shape(holder)))
                    break
        nested = [
            li
            for li in box.find_all("li")
            if any(
                isinstance(c, NavigableString) and c.strip() and lst in c.find_all_previous()
                for lst in li.find_all(["ul", "ol"])
                for c in lst.find_all_next(string=True)
                if li in c.parents
            )
        ]
        print(f"  items with text after a list inside them: {len(nested)}")
