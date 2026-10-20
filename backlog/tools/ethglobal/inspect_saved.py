"""Look at the saved pages for anything that should not be there. No request.

    python inspect_saved.py [--skeleton]

It prints counts, key names, hosts of links and the lines of the prize block. It prints no text
of a description and nothing that could be a person: an email address or a handle is only
counted, never shown.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from hackathon_memory.parse.ethglobal_page import prize_lines, took_a_hedera_prize
from hackathon_memory.parse.pagedata import page_data_text
from hackathon_memory.collect.skeleton import skeleton

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HANDLE = re.compile(r"(?<![A-Za-z0-9._%+-])@[A-Za-z0-9_]{3,30}\b")
KEY = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)":')
PERSON_KEY = re.compile(
    r"member|team|user|builder|author|profile|avatar|email|hacker|owner|creator|contributor|"
    r"handle|username|twitter|discord|telegram|linkedin|wallet|address|phone",
    re.I,
)
SOCIAL = ("twitter.com", "x.com", "linkedin.com", "t.me", "discord.gg", "discord.com",
          "instagram.com", "facebook.com", "farcaster.xyz", "warpcast.com")

all_keys: Counter[str] = Counter()
rows = []
for meta_path in sorted(RAW.glob("*.meta.json")):
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    body_path = meta_path.with_name(meta_path.name.replace(".meta.json", ".html"))
    if not body_path.exists():
        continue
    body = body_path.read_bytes()
    text = body.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "lxml")
    data = page_data_text(soup)
    keys = set(KEY.findall(data))
    all_keys.update(keys)
    visible = soup.get_text(" ")
    hosts = Counter(urlsplit(str(a["href"])).hostname or "(same site)" for a in soup.find_all("a", href=True))
    same_site = sorted({urlsplit(str(a["href"])).path.split("/")[1] if urlsplit(str(a["href"])).path.count("/") else "" for a in soup.find_all("a", href=True) if not urlsplit(str(a["href"])).hostname})
    rows.append({
        "page": meta["source_url"].rsplit("/", 1)[1],
        "bytes": meta["bytes"],
        "cut": meta["team_cut"],
        "hedera": took_a_hedera_prize(body),
        "prizes": prize_lines(body),
        "emails_visible": len(EMAIL.findall(visible)),
        "emails_all": len(EMAIL.findall(text)),
        "handles_visible": len(HANDLE.findall(visible)),
        "social_links": sum(n for host, n in hosts.items() if any(host.endswith(s) for s in SOCIAL)),
        "hosts": dict(hosts.most_common(8)),
        "same_site_first_parts": same_site,
        "images": len(soup.find_all("img")),
        "person_keys": sorted(k for k in keys if PERSON_KEY.search(k)),
        "h3": [" ".join(h.get_text().split())[:40] for h in soup.find_all("h3")],
    })

print(f"saved pages: {len(rows)}")
for row in rows:
    print(f"\n{row['page']}: {row['bytes']} bytes, cut {row['cut']}, Hedera prize: {row['hedera']}")
    print(f"  prize lines: {row['prizes']}")
    print(f"  titles of the sections (h3): {row['h3']}")
    print(f"  emails: {row['emails_visible']} visible, {row['emails_all']} in the whole file; "
          f"@handles visible: {row['handles_visible']}; links to social sites: {row['social_links']}; images: {row['images']}")
    print(f"  hosts of the links: {row['hosts']}")
    print(f"  first parts of the links inside the site: {row['same_site_first_parts']}")
    print(f"  data keys that could hold a person: {row['person_keys']}")

print(f"\nall key names of the page data, in {len(rows)} page(s): {len(all_keys)} different")
print("  " + ", ".join(sorted(all_keys)))
if "--skeleton" in sys.argv and rows:
    first = sorted(RAW.glob("*.html"))[0]
    print(f"\nskeleton of {first.name}:")
    print(skeleton(first.read_bytes()))
