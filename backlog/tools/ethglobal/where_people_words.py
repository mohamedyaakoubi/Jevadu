"""Where email-like strings, words with @ and Telegram links stand on the saved pages.

It prints only the place: the part of the page, the tag, the attribute, whether the parser
copies it into the database. Never the string itself.

    .venv/Scripts/python.exe backlog/tools/ethglobal/where_people_words.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Not followed by one more letter of the word or by a slash: the word cannot step back to make
# "@scope/package" look like a handle (lessons, 10 October 2026).
AT_WORD = re.compile(r"(?<![A-Za-z0-9._%+-/])@([A-Za-z0-9_-]{2,40})(?![A-Za-z0-9_/-])")
TELEGRAM = re.compile(r"t\.me/", re.IGNORECASE)
TITLES = ("project description", "how it's made")
SOCIAL_BEFORE = re.compile(r"(twitter|x\.com|follow|telegram|discord|by|team|dm|contact)\W*$", re.I)

places: Counter[str] = Counter()
at_kinds: Counter[str] = Counter()

for body_path in sorted(RAW.glob("*.html")):
    text = body_path.read_bytes().decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "lxml")
    boxes = []
    for heading in soup.find_all("h3"):
        if " ".join(heading.get_text().split()).lower() in TITLES:
            box = heading.find_next_sibling()
            if isinstance(box, Tag):
                boxes.append(box)

    def part_of(node: object) -> str:
        parents = list(getattr(node, "parents", []))
        if any(p.name == "script" for p in parents):
            return "a script (the data of the page)"
        if any(p is box for p in parents for box in boxes):
            return "one of the two texts (the parser copies it)"
        if any(p.name == "header" for p in parents):
            return "the header"
        return "elsewhere on the page"

    # email-like strings: in text nodes, then in attributes
    for string in soup.find_all(string=EMAIL):
        if type(string) is NavigableString or string.parent.name == "script":
            places[f"email-like, in {part_of(string)}"] += 1
    for tag in soup.find_all(True):
        for name, value in tag.attrs.items():
            values = value if isinstance(value, list) else [value]
            if any(isinstance(v, str) and EMAIL.search(v) for v in values):
                places[f"email-like, in the attribute {name} of a {tag.name}"] += 1
            if any(isinstance(v, str) and TELEGRAM.search(v) for v in values):
                places[f"Telegram link, in the attribute {name} of a {tag.name}, in {part_of(tag)}"] += 1
    # words with @ in the visible text
    for string in soup.find_all(string=AT_WORD):
        if type(string) is not NavigableString or string.parent.name in ("script", "style"):
            continue
        where = part_of(string)
        for match in AT_WORD.finditer(str(string)):
            before = str(string)[: match.start()]
            in_code = any(p.name in ("code", "pre") for p in string.parents)
            kind = (
                "inside code"
                if in_code
                else "after a word such as twitter, follow, by or team"
                if SOCIAL_BEFORE.search(before)
                else "other"
            )
            at_kinds[f"@word in {where}: {kind}"] += 1

    # The key of the page data that holds an email-like string: the path of keys only.
    from hackathon_memory.parse.pagedata import page_data_text  # noqa: E402

    data = page_data_text(soup)
    for match in EMAIL.finditer(data):
        keys = re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)":', data[max(0, match.start() - 400) : match.start()])
        places[f"email-like in the page data, after the keys {keys[-3:]}"] += 1

for title, counter in (("places", places), ("words with @", at_kinds)):
    print(f"{title}:")
    for value, count in counter.most_common():
        print(f"  {count:4}  {value}")
