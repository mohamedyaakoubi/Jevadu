"""What could still name a person in the stored texts, after the parser hid what it hides?

Two shapes that the parser does not look at today:

* a link whose path has a piece that starts with "@" (a handle on some site, or a package);
* a link to github.com with one name only (a profile, of a person or of a group).

Counts by site only. It prints no link, no name and no text.

    .venv/Scripts/python.exe backlog/tools/ethglobal/people_left_in_texts.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter

import psycopg

from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LINK = re.compile(r"(?:https?://)?(?:www\.)?([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)(/[^\s<>()\[\]\"']*)?")
KNOWN = {
    "github.com", "medium.com", "youtube.com", "npmjs.com", "unpkg.com", "cdn.jsdelivr.net",
    "hackmd.io", "devfolio.co", "farcaster.xyz", "warpcast.com", "dev.to", "mirror.xyz",
    "substack.com", "gitlab.com", "huggingface.co", "kaggle.com", "esm.sh", "jsr.io",
    "raw.githubusercontent.com", "gist.github.com", "discord.gg", "discord.com",
}  # fmt: skip
# Pages of github.com that are not a profile, though they have one name only.
GITHUB_OWN_PAGES = {
    "features", "about", "pricing", "marketplace", "topics", "explore", "sponsors", "apps",
    "orgs", "login", "signup", "settings", "notifications", "search", "collections", "security",
}  # fmt: skip


def site(host: str) -> str:
    host = host.lower()
    for known in KNOWN:
        if host == known or host.endswith("." + known):
            return known
    return "another site"


with psycopg.connect(Settings().database_conninfo()) as conn:
    rows = conn.execute("SELECT project_id, body FROM sections").fetchall()
    lines = conn.execute("SELECT id, short_line FROM projects").fetchall()

at_piece: Counter[str] = Counter()
at_projects: dict[str, set[int]] = {}
github_one_name = github_repo = github_gist = 0
github_projects: set[int] = set()
subdomain_pages = Counter()
for project_id, body in [*rows, *((pid, line or "") for pid, line in lines)]:
    for match in LINK.finditer(body):
        host, path = match.group(1), (match.group(2) or "")
        pieces = [piece for piece in path.split("?")[0].split("#")[0].split("/") if piece]
        where = site(host)
        if any(piece.startswith("@") for piece in pieces):
            scoped = sum(piece.startswith("@") for piece in pieces)
            last_at = max(i for i, piece in enumerate(pieces) if piece.startswith("@"))
            shape = (
                "the @ piece is followed by more"
                if last_at < len(pieces) - 1
                else "the @ piece is the last"
            )
            at_piece[f"{where}: {shape}"] += scoped
            at_projects.setdefault(where, set()).add(project_id)
        if host.lower() in ("github.com", "www.github.com"):
            if len(pieces) == 1 and pieces[0].lower() not in GITHUB_OWN_PAGES:
                github_one_name += 1
                github_projects.add(project_id)
            elif len(pieces) >= 2:
                github_repo += 1
        if host.lower().endswith(".github.io"):
            subdomain_pages["a page at github.io (the first part is an account name)"] += 1
        if host.lower().endswith(".medium.com") or host.lower().endswith(".substack.com"):
            subdomain_pages["a page at a blog site under an account name"] += 1

print("links with a piece of the path that starts with @, by site and shape:")
for shape, count in at_piece.most_common():
    print(f"  {count:4}  {shape}")
print("  projects, by site:", {where: len(ids) for where, ids in at_projects.items()})
print("links to github.com in the texts:")
print(f"  {github_repo:4}  with an account and a repository (kept: design rule 11)")
print(f"  {github_one_name:4}  with one name only, in {len(github_projects)} project(s)")
print("links where the account name is the first part of the site name:")
for shape, count in subdomain_pages.most_common():
    print(f"  {count:4}  {shape}")
