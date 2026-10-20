"""How many links to profiles on social sites stand in the copied texts. Counts only.

The parser hides words that start with "@". A profile can also be written as a link in the text,
such as "x.com/name". This tool counts them by site, in the texts that are in the database, and
prints no link.

    .venv/Scripts/python.exe backlog/tools/ethglobal/people_links_in_texts.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter

import psycopg

from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PROFILE = re.compile(
    r"(?<![A-Za-z0-9.-])(?:https?://)?(?:www\.)?"
    r"(twitter\.com|x\.com|t\.me|telegram\.me|linkedin\.com|instagram\.com|facebook\.com|"
    r"warpcast\.com|farcaster\.xyz|discord\.gg|discord\.com|discordapp\.com|medium\.com|"
    r"youtube\.com|youtu\.be|tiktok\.com|threads\.net|bsky\.app)"
    r"/([A-Za-z0-9_@./?=&%-]*)",
    re.IGNORECASE,
)

with psycopg.connect(Settings().database_conninfo()) as conn:
    rows = conn.execute("SELECT project_id, kind, body FROM sections").fetchall()

by_host: Counter[str] = Counter()
projects: dict[str, set[int]] = {}
shapes: Counter[str] = Counter()
for project_id, _kind, body in rows:
    for match in PROFILE.finditer(body):
        host = match.group(1).lower()
        path = match.group(2)
        by_host[host] += 1
        projects.setdefault(host, set()).add(project_id)
        first = path.split("/")[0].split("?")[0]
        shapes[
            f"{host}: "
            + (
                "no path"
                if not first
                else "a status, a post or a video"
                if re.search(r"status|watch|/p/|/in/|/video/|/posts/|share", path)
                else "one name after the site"
                if "/" not in path.strip("/")
                else "a longer path"
            )
        ] += 1

print("links to social sites in the copied texts, by site (links, projects):")
for host, count in by_host.most_common():
    print(f"  {count:4} {len(projects[host]):4}  {host}")
print("their shapes:")
for shape, count in shapes.most_common():
    print(f"  {count:4}  {shape}")
at_words = sum(len(re.findall(r"(?<![A-Za-z0-9._%+/-])@[A-Za-z0-9_]", body)) for _, _, body in rows)
print(f"words that start with @ in the texts (code blocks included): {at_words}")
