"""What shape do the header links to a profile site have? Counts of shapes only, no link.

Four "Live Demo" links lead to t.me. A name on Telegram that ends in "bot" is a bot and not a
person. This tool says how many of the links have that shape. It prints no name.

    .venv/Scripts/python.exe backlog/tools/ethglobal/shape_of_profile_site_links.py
"""

from __future__ import annotations

import sys
from collections import Counter
from urllib.parse import urlsplit

import psycopg

from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PROFILE_SITES = {
    "twitter.com", "x.com", "t.me", "telegram.me", "linkedin.com", "instagram.com",
    "facebook.com", "warpcast.com", "threads.net", "bsky.app", "tiktok.com",
}  # fmt: skip

with psycopg.connect(Settings().database_conninfo()) as conn:
    links = conn.execute("SELECT kind, url FROM links").fetchall()

shapes: Counter[str] = Counter()
for kind, url in links:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("mobile.")
    if host not in PROFILE_SITES:
        continue
    pieces = [piece for piece in parts.path.split("/") if piece]
    first = pieces[0] if pieces else ""
    shape = (
        "no name"
        if not first
        else "an invitation to a group"
        if first.startswith("+") or first.lower() == "joinchat"
        else "a name that ends in bot"
        if first.lower().endswith("bot")
        else "another name"
    )
    more = ", and more of a path" if len(pieces) > 1 else ""
    query = ", and a question part" if parts.query else ""
    shapes[f"{kind} link to {host}: {shape}{more}{query}"] += 1

for shape, count in shapes.most_common():
    print(f"{count:3}  {shape}")
print("total:", sum(shapes.values()))
