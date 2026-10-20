"""Can a person still show in what the database keeps, outside the two texts? Counts only.

The parser hides handles, addresses and profile links in the two texts and in the short line.
Three other places keep words of a page: the links of the header (the code, the demo), the words
around a Hedera ID, and the name of the project. This tool counts what looks like a person there.
It prints no link, no name and no text: only numbers and the names of well-known sites.

    .venv/Scripts/python.exe backlog/tools/ethglobal/people_in_stored_links.py
"""

from __future__ import annotations

import sys
from collections import Counter
from urllib.parse import urlsplit

import psycopg

from hackathon_memory.parse.people import ADDRESS, hide_in_text
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Sites where an address is the profile of somebody, or can be.
PROFILE_SITES = {
    "twitter.com", "x.com", "t.me", "telegram.me", "linkedin.com", "instagram.com",
    "facebook.com", "warpcast.com", "threads.net", "bsky.app", "tiktok.com",
}  # fmt: skip
# Sites that host a thing and not a person: named so that the reader sees the size of each.
THING_SITES = {
    "github.com", "youtube.com", "youtu.be", "vercel.app", "netlify.app", "hashscan.io",
    "docs.google.com", "drive.google.com", "figma.com", "loom.com", "devfolio.co",
}  # fmt: skip


def site_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.").removeprefix("mobile.")
    for known in PROFILE_SITES | THING_SITES:
        if host == known or host.endswith("." + known):
            return known
    return "another site"


with psycopg.connect(Settings().database_conninfo()) as conn:
    links = conn.execute("SELECT kind, url, label FROM links WHERE url IS NOT NULL").fetchall()
    hidden = conn.execute(
        "SELECT kind, hidden_on, count(*) FROM links WHERE url IS NULL GROUP BY 1, 2 ORDER BY 1, 2"
    ).fetchall()
    words = conn.execute("SELECT words_around FROM hedera_ids").fetchall()
    names = conn.execute("SELECT name, short_line FROM projects").fetchall()

by_kind: dict[str, Counter[str]] = {}
labels: Counter[str] = Counter()
with_login = with_address = 0
for kind, url, label in links:
    by_kind.setdefault(kind, Counter())[site_of(url)] += 1
    labels[label if label in ("Source Code", "Live Demo") else "another label"] += 1
    parts = urlsplit(url)
    with_login += bool(parts.username or parts.password)
    with_address += bool(ADDRESS.search(url))

print("links of the header with their address in the database:", len(links))
print("links kept without their address (kind, site, how many):", hidden or "none")
for kind, sites in sorted(by_kind.items()):
    print(f"  kind {kind!r}: {sum(sites.values())}")
    for site, count in sites.most_common():
        mark = "  <- a profile site" if site in PROFILE_SITES else ""
        print(f"    {count:5}  {site}{mark}")
print("  words of the links:", dict(labels))
print("  links with a login inside the address:", with_login)
print("  links with an email-like string inside the address:", with_address)

on_profile_sites = sum(
    count for sites in by_kind.values() for site, count in sites.items() if site in PROFILE_SITES
)
print("links of the header that lead to a profile site:", on_profile_sites)

around = sum(hide_in_text(text)[1] > 0 for (text,) in words)
print(f"words around a Hedera ID: {len(words)} rows, {around} where the parser would still hide")
in_names = sum(hide_in_text(name)[1] > 0 for name, _ in names)
in_lines = sum(hide_in_text(line or "")[1] > 0 for _, line in names)
print(f"names of projects: {len(names)}, {in_names} that hold a handle, an address or a profile")
print(f"short lines where the parser would still hide a word: {in_lines}")
