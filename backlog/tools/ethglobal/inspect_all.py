"""All the saved pages, in one table of counts. No request, no text of a page, no person shown."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from hackathon_memory.parse.ethglobal_page import prize_lines, prize_sponsors, took_a_hedera_prize
from hackathon_memory.parse.pagedata import page_data_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
AT_WORD = re.compile(r"(?<![A-Za-z0-9._%+-/])@([A-Za-z0-9_-]{2,40})(/?)")
KEY = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)":')
PERSON_KEY = re.compile(
    r"member|team|user|builder|author|profile|avatar|email|hacker|owner|creator|contributor|"
    r"handle|username|twitter|discord|telegram|linkedin|phone",
    re.I,
)
SOCIAL = ("twitter.com", "x.com", "linkedin.com", "t.me", "instagram.com", "facebook.com",
          "farcaster.xyz", "warpcast.com")
SITE_LINKS = {"https://x.com/ethglobal", "https://twitter.com/ethglobal"}

pages = 0
sizes = []
no_prize = 0
h3_sets: Counter[tuple[str, ...]] = Counter()
sponsor_sets: Counter[tuple[str, ...]] = Counter()
prize_count: Counter[int] = Counter()
emails_visible = emails_file = 0
at_people = 0
at_people_pages = 0
at_scopes: Counter[str] = Counter()
person_keys: Counter[str] = Counter()
social_hosts: Counter[str] = Counter()
social_pages = 0
same_site_parts: Counter[str] = Counter()
keys_all: Counter[str] = Counter()
github = demo = 0
cut_reports: Counter[str] = Counter()
hedera_id_like = 0

for meta_path in sorted(RAW.glob("*.meta.json")):
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    body_path = meta_path.with_name(meta_path.name.replace(".meta.json", ".html"))
    if not body_path.exists():
        continue
    pages += 1
    body = body_path.read_bytes()
    text = body.decode("utf-8", errors="replace")
    sizes.append(len(body))
    cut_reports[json.dumps(meta["team_cut"], sort_keys=True)] += 1
    no_prize += not took_a_hedera_prize(body)
    lines = prize_lines(body)
    prize_count[len(lines)] += 1
    sponsor_sets[tuple(prize_sponsors(body))] += 1
    soup = BeautifulSoup(text, "lxml")
    keys = set(KEY.findall(page_data_text(soup)))
    keys_all.update(keys)
    person_keys.update(k for k in keys if PERSON_KEY.search(k))
    h3_sets[tuple(" ".join(h.get_text().split())[:30] for h in soup.find_all("h3"))] += 1
    hrefs = [str(a["href"]) for a in soup.find_all("a", href=True)]
    here_social = 0
    for href in hrefs:
        parts = urlsplit(href)
        host = parts.hostname or ""
        if not host:
            same_site_parts[parts.path.split("/")[1] if parts.path.count("/") else ""] += 1
        elif any(host == s or host.endswith("." + s) for s in SOCIAL) and href.rstrip("/") not in SITE_LINKS:
            social_hosts[host] += 1
            here_social += 1
    social_pages += bool(here_social)
    github += any((urlsplit(h).hostname or "").endswith("github.com") for h in hrefs)
    for junk in soup(["script", "style"]):
        junk.decompose()
    visible = soup.get_text(" ")
    emails_visible += len(EMAIL.findall(visible))
    emails_file += len(EMAIL.findall(text))
    here_people = 0
    for word, slash in AT_WORD.findall(visible):
        if slash:
            at_scopes[f"@{word}/"] += 1
        else:
            here_people += 1
    at_people += here_people
    at_people_pages += bool(here_people)
    hedera_id_like += bool(re.search(r"\b0\.0\.\d{3,}\b", visible))

sizes.sort()
print(f"saved pages: {pages}; bytes: smallest {sizes[0]}, median {sizes[len(sizes)//2]}, largest {sizes[-1]}, total {sum(sizes)}")
print(f"pages with no Hedera prize: {no_prize}")
print(f"team cut reports: {dict(cut_reports)}")
print(f"number of prize lines on a page: {dict(sorted(prize_count.items()))}")
print(f"different sets of section titles (h3): {len(h3_sets)}")
for titles, count in h3_sets.most_common(6):
    print(f"  {count:3}  {list(titles)}")
print(f"sponsors named in the prize blocks (first 12 sets): ")
for sponsors, count in sponsor_sets.most_common(12):
    print(f"  {count:3}  {list(sponsors)}")
print(f"emails: {emails_visible} in visible text, {emails_file} in the whole files")
print(f"words that start with @ and are not a package scope: {at_people} in {at_people_pages} page(s)")
print(f"package scopes: {dict(at_scopes.most_common(12))}")
print(f"data keys that could hold a person: {dict(person_keys)}")
print(f"links to social sites, other than the site's own: {dict(social_hosts)} in {social_pages} page(s)")
print(f"first parts of the links inside the site: {dict(same_site_parts.most_common(30))}")
print(f"pages with a link to github.com: {github}; pages whose text shows something like 0.0.12345: {hedera_id_like}")
print(f"key names of the page data over all pages: {len(keys_all)}")
rare = sorted(k for k, n in keys_all.items() if n < pages)
print(f"  keys that are not on every page: {rare}")
