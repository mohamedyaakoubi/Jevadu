"""How many links inside the two texts of the saved pages lead to a profile? Counts only.

The parser hides a profile link that is written as text. A link can also be a real link of the
page: an anchor whose address leads to a profile, with words such as a name. The address is not
copied, but the words are. This tool counts such anchors, by site, and how many words they hold.
It prints no address, no word and no name.

    .venv/Scripts/python.exe backlog/tools/ethglobal/profile_anchors_in_texts.py
"""

from __future__ import annotations

import sys
from collections import Counter

from bs4 import BeautifulSoup

from hackathon_memory.collect.ethglobal import data_paths
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.parse.people import profile_site
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TITLES = {"project description", "how it's made"}

store = RawStore(data_paths(Settings()).raw_dir)
by_site: Counter[str] = Counter()
words_in_them: Counter[str] = Counter()
pages = 0
for saved in store.saved():
    soup = BeautifulSoup(saved.read(), "lxml")
    found_here = 0
    for heading in soup.find_all("h3"):
        if " ".join(heading.get_text().split()).lower() not in TITLES:
            continue
        box = heading.find_next_sibling()
        if box is None:
            continue
        for anchor in box.find_all("a", href=True):
            site = profile_site(str(anchor["href"]))
            if site is None:
                continue
            by_site[site] += 1
            shown = " ".join(anchor.get_text().split())
            kind = (
                "no words"
                if not shown
                else "the address itself"
                if site in shown.lower()
                else "words starting with @"
                if shown.startswith("@")
                else "other words"
            )
            words_in_them[kind] += 1
            found_here += 1
    pages += found_here > 0

print("anchors in the two texts that lead to a profile, by site:", dict(by_site) or "none")
print("what such an anchor shows:", dict(words_in_them) or "nothing")
print("pages with at least one:", pages)
