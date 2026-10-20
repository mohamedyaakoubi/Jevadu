"""The pieces of links in the stored texts that start with "@": hidden or not? Counts only.

It prints, for each such piece, only: whether it is the hidden mark, whether the link starts
with a scheme or "www.", and whether its site is a site of packages. No link, no name.

    .venv/Scripts/python.exe backlog/tools/ethglobal/at_pieces_in_links.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter

import psycopg

from hackathon_memory.parse.people import HIDDEN_HANDLE, PACKAGE_SITES
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LINK = re.compile(r"((?:https?://|www\.)?)((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})(/[^\s<>()\"']*)")

with psycopg.connect(Settings().database_conninfo()) as conn:
    texts = [body for (body,) in conn.execute("SELECT body FROM sections")]

shapes: Counter[str] = Counter()
for body in texts:
    for match in LINK.finditer(body):
        scheme, host, path = match.groups()
        for piece in path.split("/"):
            if not piece.startswith("@"):
                continue
            hidden = piece.startswith(HIDDEN_HANDLE.split(" ")[0])  # the mark has a space
            package = any(host.lower().endswith(site) for site in PACKAGE_SITES)
            shapes[
                f"hidden: {hidden}, scheme or www: {bool(scheme)}, site of packages: {package}"
            ] += 1
for shape, count in shapes.most_common():
    print(f"{count:3}  {shape}")
print("total:", sum(shapes.values()))
