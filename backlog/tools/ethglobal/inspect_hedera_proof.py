"""What the saved pages offer as proof of Hedera use, from the VISIBLE text. Counts only.

The first version read the texts from the page data and found them too short: the data keeps a
long text in a row of its own and only points to it. The visible page has the whole text.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"
NATIVE_ID = re.compile(r"(?<![\d.])0\.0\.\d{3,10}(?![\d.])")
EVM = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
WORDS = {
    "hashscan": re.compile(r"hashscan", re.I),
    "testnet": re.compile(r"\btestnet\b", re.I),
    "mainnet": re.compile(r"\bmainnet\b", re.I),
    "HCS / consensus service": re.compile(r"\bHCS\b|consensus service", re.I),
    "HTS / token service": re.compile(r"\bHTS\b|token service", re.I),
    "smart contract": re.compile(r"smart contracts?", re.I),
    "agent kit": re.compile(r"agent kit", re.I),
    "mirror node": re.compile(r"mirror node", re.I),
    "scheduled transaction or service": re.compile(r"schedul\w* (transaction|service)", re.I),
    "the word Hedera at all": re.compile(r"hedera", re.I),
}
KNOWN = ("project description", "how it's made")

pages = 0
have: Counter[str] = Counter()
ids_per_page: Counter[int] = Counter()
lengths = {"project description": [], "how it's made": []}
for body_path in sorted(RAW.glob("*.html")):
    pages += 1
    soup = BeautifulSoup(body_path.read_text(encoding="utf-8", errors="replace"), "lxml")
    for junk in soup(["script", "style", "nav", "footer", "form"]):
        junk.decompose()
    # the two text sections: everything from a known title to the next KNOWN title or the end
    titles = [h for h in soup.find_all("h3") if " ".join(h.get_text().split()).lower() in KNOWN]
    texts = {}
    for title in titles:
        name = " ".join(title.get_text().split()).lower()
        block = title.find_next_sibling()
        texts[name] = " ".join(block.get_text(" ").split()) if block is not None else ""
    for name in KNOWN:
        lengths[name].append(len(texts.get(name, "")))
    text = " ".join(texts.values())
    native = set(NATIVE_ID.findall(text))
    ids_per_page[min(len(native), 5)] += 1
    have["a Hedera id like 0.0.12345"] += bool(native)
    have["an EVM address (0x and 40 letters)"] += bool(EVM.search(text))
    for name, pattern in WORDS.items():
        have[f"the word(s): {name}"] += bool(pattern.search(text))

print(f"saved pages: {pages}")
for name, values in lengths.items():
    values.sort()
    print(f"length of '{name}': smallest {values[0]}, median {values[len(values)//2]}, "
          f"largest {values[-1]} characters; empty on {sum(1 for v in values if v == 0)} page(s)")
for name, count in have.most_common():
    print(f"  {count:3} of {pages}  {name}")
print(f"different Hedera ids in the two texts of a page (5 = five or more): {dict(sorted(ids_per_page.items()))}")
