"""Does a link to a profile site still stand in the stored texts, in any spelling? Counts only.

The parser hides "x.com/name" and "www.linkedin.com/in/name". This tool looks for what its
pattern may miss: a profile site behind another first part ("uk.linkedin.com", "m.facebook.com"),
or with no path after the name of the site. It reads the texts as they are stored (after the
hiding) and the texts as the parser would give them from the saved pages with no hiding.

It prints the names of the profile sites and numbers. No link, no name, no text.

    .venv/Scripts/python.exe backlog/tools/ethglobal/profile_links_left.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter

import psycopg

from hackathon_memory.parse.people import PROFILE_SITES
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOST = re.compile(r"(?<![A-Za-z0-9.@-])((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})(/[^\s<>()\[\]\"']*)?")


def site_of(host: str) -> str | None:
    host = host.lower()
    for site in PROFILE_SITES:
        if host == site or host.endswith("." + site):
            return site
    return None


with psycopg.connect(Settings().database_conninfo()) as conn:
    texts = conn.execute("SELECT project_id, body FROM sections").fetchall()
    lines = conn.execute("SELECT id, short_line FROM projects").fetchall()

left: Counter[str] = Counter()
projects: set[int] = set()
for project_id, body in [*texts, *((pid, line or "") for pid, line in lines)]:
    for match in HOST.finditer(body):
        host, path = match.group(1), match.group(2) or ""
        site = site_of(host)
        if site is None:
            continue
        first_part = host.lower().removesuffix(site).rstrip(".")
        shape = (
            ("the site itself" if not first_part else "behind another first part")
            + (", with a path" if path.strip("/") else ", with no path")
        )
        left[f"{site}: {shape}"] += 1
        projects.add(project_id)

print("names of profile sites that still stand in the stored texts:", sum(left.values()))
for shape, count in left.most_common():
    print(f"  {count:4}  {shape}")
print("projects:", len(projects))
