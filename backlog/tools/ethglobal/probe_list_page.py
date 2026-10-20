"""Page 3 of the showcase filtered by the partner Hedera: read the project records of the list.

    PYTHONIOENCODING=utf-8 python eth_listing3.py [page]

One signed request. The page keeps its data as text inside a script. This decodes that text,
finds the record of each project of the list, and shows which keys a record has and what its
"prizes" part holds. Only key names, project addresses, event names and prize names are printed.
Nothing is saved.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

os.environ["COLLECT_ETHGLOBAL"] = "on"  # this process only
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

from bs4 import BeautifulSoup  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
import eth_listing as one  # noqa: E402
from hackathon_memory.collect.polite import (  # noqa: E402
    CollectorIdentity,
    FetchFailed,
    PoliteClient,
    StopCollecting,
)
from hackathon_memory.settings import Settings  # noqa: E402

PERSON = re.compile(r"member|team|user|builder|author|profile|avatar|email|hacker|owner|creator", re.I)
PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.S)


def flight_text(soup: BeautifulSoup) -> str:
    """The data of the page: the strings that the scripts push, decoded and joined."""
    parts = []
    for script in soup.find_all("script"):
        for literal in PUSH.findall(script.string or ""):
            try:
                parts.append(json.loads(literal))
            except ValueError:
                continue
    return "".join(parts)


def objects_with_key(text: str, key: str) -> list[str]:
    """The text of every JSON object that has `key` as one of its own keys."""
    stack: list[int] = []
    wanted: set[int] = set()
    found: list[str] = []
    needle = f'"{key}":'
    i, n, in_string = 0, len(text), False
    while i < n:
        c = text[i]
        if in_string:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_string = False
        elif c == '"':
            if stack and text.startswith(needle, i):
                wanted.add(stack[-1])
            in_string = True
        elif c == "{":
            stack.append(i)
        elif c == "}" and stack:
            start = stack.pop()
            if start in wanted:
                wanted.discard(start)
                found.append(text[start : i + 1])
        i += 1
    return found


def main(page: int) -> int:
    identity = CollectorIdentity.from_settings(Settings())
    client = PoliteClient(
        site=one.SITE, identity=identity, allow=one.allow, is_enabled=lambda: True, max_requests=1
    )
    url = f"https://{one.SITE}/showcase?partners=hedera&page={page}"
    try:
        got = client.get(url)
    except (StopCollecting, FetchFailed) as error:
        print(f"STOPPED OR FAILED: {error}")
        return 1
    print(f"status {got.status}, {len(got.body)} bytes, final address: {got.final_url}")
    if got.status != 200:
        return 1
    soup = BeautifulSoup(got.body.decode("utf-8", errors="replace"), "lxml")
    hrefs = [str(a["href"]) for a in soup.find_all("a", href=True)]
    slugs = list(dict.fromkeys(
        h.rsplit("/", 1)[1] for h in hrefs if re.fullmatch(r"/showcase/[A-Za-z0-9-]+", h)
    ))
    print(f"project addresses on page {page}: {len(slugs)}")
    print("paging links:", sorted({h for h in hrefs if "partners=hedera" in h}))

    text = flight_text(soup)
    print(f"decoded page data: {len(text)} characters")
    records = []
    for raw in objects_with_key(text, "tagline"):
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if isinstance(record, dict) and "prizes" in record:
            records.append(record)
    print(f"records with a tagline and a prizes part: {len(records)}")
    if not records:
        return 1
    first = records[0]
    print("keys of one record:", sorted(first))
    print("keys that look like a person:", sorted(k for k in first if PERSON.search(k)))
    nested = Counter()
    for record in records:
        for key, value in record.items():
            if isinstance(value, dict):
                nested[f"{key}: object with {sorted(value)[:8]}"] += 1
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                nested[f"{key}: list of objects with {sorted(value[0])[:8]}"] += 1
    for shape, count in nested.most_common(8):
        print(f"  {count:3}  {shape}")

    def address(record: dict) -> str:
        return f"{record.get('slug')}-{record.get('uuid')}"

    matched = sum(1 for r in records if address(r) in slugs)
    print(f"records whose slug and uuid give an address of the page: {matched} of {len(records)}")
    events = Counter(str((r.get("event") or {}).get("name")) for r in records)
    print(f"events: {dict(events)}")

    with_prize = [r for r in records if r.get("prizes")]
    print(f"records with at least one prize: {len(with_prize)} of {len(records)}")
    hedera = 0
    for record in with_prize:
        lines = []
        for prize in record["prizes"]:
            inner = prize.get("prize") or {}
            sponsor = (inner.get("sponsor") or {}).get("name")
            lines.append(f"{sponsor} - {inner.get('name')} [{prize.get('name')}] ({inner.get('type')})")
            if str(sponsor).lower() == "hedera":
                hedera += 1
        print(f"  {address(record)}: {lines[:4]}")
    print(f"prizes whose sponsor is Hedera: {hedera}")
    print(f"requests sent: {client.requests_made}")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3))
