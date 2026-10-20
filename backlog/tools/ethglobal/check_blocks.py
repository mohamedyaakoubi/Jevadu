"""The text blocks of the parser, on every saved page. Counts only, no text of a page.

For each of the two texts of a page: the blocks must hold exactly the letters of the box, in the
same order.

    .venv/Scripts/python.exe backlog/tools/ethglobal/check_blocks.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

from hackathon_memory.parse.blocks import blocks_of, plain_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"
TITLES = ("project description", "how it's made")


def letters(text: str) -> str:
    return "".join(text.split())


pages = 0
result: Counter[str] = Counter()
kinds: Counter[str] = Counter()
blocks_per_text: list[int] = []
longest = 0

for body_path in sorted(RAW.glob("*.html")):
    soup = BeautifulSoup(body_path.read_bytes().decode("utf-8", errors="replace"), "lxml")
    pages += 1
    for heading in soup.find_all("h3"):
        title = " ".join(heading.get_text().split()).lower()
        if title not in TITLES:
            continue
        box = heading.find_next_sibling()
        if box is None:
            result[f"{title}: no box"] += 1
            continue
        blocks = blocks_of(box)
        blocks_per_text.append(len(blocks))
        kinds.update(f"{block.kind} level {block.level}" for block in blocks)
        longest = max(longest, *(len(block.text) for block in blocks), 0)
        same = letters(plain_text(blocks)) == letters(box.get_text())
        same_set = sorted(letters(plain_text(blocks))) == sorted(letters(box.get_text()))
        result[
            f"{title}: "
            + (
                "the same letters in the same order"
                if same
                else "the same letters in another order"
                if same_set
                else "LETTERS LOST OR ADDED"
            )
        ] += 1
        if not blocks:
            result[f"{title}: empty"] += 1

blocks_per_text.sort()
print(f"pages: {pages}")
for line, count in sorted(result.items()):
    print(f"  {count:4}  {line}")
print(f"blocks in one text: smallest {blocks_per_text[0]}, median "
      f"{blocks_per_text[len(blocks_per_text) // 2]}, largest {blocks_per_text[-1]}")
print(f"the longest block has {longest} characters")
for kind, count in kinds.most_common():
    print(f"  {count:5}  {kind}")
