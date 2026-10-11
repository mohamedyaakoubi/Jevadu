"""What a project page of ETHGlobal's showcase says (design 6.1).

This is the one place that knows where a fact stands on a project page. The collector asks it
whether a page shows a Hedera prize, and so does the proof of the lists.

The block "Winner of" has one line for each prize: the sponsor, a dash, the name of the prize
and, for some prizes, the place ("Hedera - <prize name> <place>").
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

# The line of a prize on a project page: the sponsor, a dash, the prize name, the place.
HEDERA_PRIZE_LINE = re.compile(r"^\s*hedera\s*[-‐-―]\s*\S", re.IGNORECASE)
_BEFORE_THE_DASH = re.compile(r"\s+[-\u2010-\u2015]\s+")


def prize_lines(html: bytes) -> list[str]:
    """The lines of the "Winner of" blocks of a page, one for each prize, with plain spaces."""
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml")
    lines: list[str] = []
    for heading in soup.find_all("h3"):
        if " ".join(heading.get_text().split()).lower() != "winner of":
            continue
        block = heading.find_next_sibling()
        if block is not None:
            lines.extend(" ".join(line.get_text(" ").split()) for line in block.find_all("h4"))
    return lines


def took_a_hedera_prize(html: bytes) -> bool:
    """True if a "Winner of" block of the page has a line that starts with "Hedera -"."""
    return any(HEDERA_PRIZE_LINE.match(line) for line in prize_lines(html))


def prize_sponsors(html: bytes) -> list[str]:
    """The sponsors that the "Winner of" blocks name: the part of each line before the dash.

    Only for a message of the run, so that a person can see what a page shows.
    """
    names = (_BEFORE_THE_DASH.split(line, maxsplit=1)[0][:60] for line in prize_lines(html))
    return list(dict.fromkeys(name for name in names if name))
