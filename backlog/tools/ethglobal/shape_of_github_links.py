"""What shape do the stored links to github.com have? Counts of shapes only, no link.

A link to a repository holds the name of its account: that is allowed, because the link needs
it (design rule 11). A link with one name only is the profile of an account. This tool says how
many of each shape the header links have, by kind.

    .venv/Scripts/python.exe backlog/tools/ethglobal/shape_of_github_links.py
"""

from __future__ import annotations

import sys
from collections import Counter
from urllib.parse import urlsplit

import psycopg

from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with psycopg.connect(Settings().database_conninfo()) as conn:
    links = conn.execute("SELECT kind, url FROM links WHERE url IS NOT NULL").fetchall()

shapes: Counter[str] = Counter()
for kind, url in links:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    if host == "gist.github.com":
        shapes[f"{kind}: a gist"] += 1
        continue
    if host.endswith(".github.io"):
        shapes[f"{kind}: a page at github.io"] += 1
        continue
    if host != "github.com":
        continue
    pieces = [piece for piece in parts.path.split("/") if piece]
    shape = (
        "no name"
        if not pieces
        else "one name only (a profile)"
        if len(pieces) == 1
        else "an account and a repository"
        if len(pieces) == 2
        else f"a repository and more ({pieces[2]})"
        if pieces[2] in ("tree", "blob", "releases", "issues", "pull", "wiki", "actions", "pulls")
        else "a repository and more (another word)"
    )
    shapes[f"{kind}: {shape}"] += 1

for shape, count in sorted(shapes.items()):
    print(f"{count:4}  {shape}")
