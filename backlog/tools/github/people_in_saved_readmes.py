"""Is a person left in the saved READMEs? Counts only: no text, no name, no link.

It reads data/raw/api.github.com and counts, over all saved files (the READMEs and the small
files next to them): email-like strings, words that start with "@" outside code and the hidden
marks, links to a profile site, links to an account page on GitHub, and photos of accounts. It
also prints the keys of the small files and the numbers of what was taken out.

    .venv/Scripts/python.exe backlog/tools/github/people_in_saved_readmes.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from hackathon_memory.parse.people import ADDRESS, HIDDEN_ADDRESS, PHOTO_HOST, profile_site
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
folder = Path(Settings().data_dir) / "raw" / "api.github.com"
LINK = re.compile(r"(?:https?://)?(?:www\.)?(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}/[^\s<>()\[\]\"'`]*")
FENCE = re.compile(r"^ {0,3}(```|~~~)")

found: Counter[str] = Counter()
keys: Counter[str] = Counter()
taken_out: Counter[str] = Counter()
files = 0
for path in sorted(folder.glob("*")):
    files += 1
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.name.endswith(".meta.json"):
        meta = json.loads(text)
        keys.update(list(meta))
        for key, value in (meta.get("team_cut") or {}).items():
            taken_out[key] += int(value)
        continue
    found["email-like strings"] += len(ADDRESS.findall(text.replace(HIDDEN_ADDRESS, "")))
    in_code = False
    for line in text.split("\n"):
        if FENCE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        for link in LINK.findall(line):
            if profile_site(link if "://" in link else "https://" + link):
                found["links to a profile site or an account page"] += 1
            if PHOTO_HOST in link.lower():
                found["photos of accounts"] += 1
        outside = re.sub(r"`[^`]*`", "", line)
        for word in re.findall(r"(?<![\w./@+-])@[A-Za-z0-9_][\w.-]*", outside):
            found["words with @ outside code (packages and decorators count too)"] += 1

print("files in the folder:", files)
print("keys of the small files:", dict(keys))
print("taken out before saving, in all:", dict(taken_out))
for kind in (
    "email-like strings",
    "links to a profile site or an account page",
    "photos of accounts",
    "words with @ outside code (packages and decorators count too)",
):
    print(f"{found[kind]:5}  {kind}")
