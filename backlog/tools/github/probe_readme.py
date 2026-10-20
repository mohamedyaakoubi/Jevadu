"""Three real requests to GitHub's API, to see the shape of its answers before the reader is built.

The owner's yes for GitHub's API is recorded (Q17, 10 October 2026). CLAUDE.md, section 1: send
one real request and look at the answer before writing a collector.

The three repositories are public repositories of the Hedera project itself, not of a team:

1. the README of a repository that exists;
2. the README of a repository that was moved to another owner (a redirect is expected);
3. the README of a repository that does not exist (404 is expected).

Each request is counted in data/requests/api.github.com.json before it is sent. The script
prints the status, a fixed list of headers, the keys of the JSON answer and the sizes. It never
prints the token, the contact address or the text of a README.

    .venv/Scripts/python.exe backlog/tools/github/probe_readme.py
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import requests

from hackathon_memory import __version__
from hackathon_memory.collect.polite import RequestCount
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SITE = "api.github.com"
ASKED = [
    "https://api.github.com/repos/hiero-ledger/hiero-sdk-python/readme",
    "https://api.github.com/repos/hashgraph/hedera-sdk-js/readme",
    "https://api.github.com/repos/hiero-ledger/a-repository-that-does-not-exist-3f9k/readme",
]
SHOWN_HEADERS = (
    "content-type",
    "location",
    "x-github-api-version-selected",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-used",
    "x-ratelimit-resource",
    "x-ratelimit-reset",
    "retry-after",
    "cache-control",
    "vary",
)

settings = Settings()
token = settings.github_token.get_secret_value().strip()
contact = settings.collector_contact_email.get_secret_value().strip()
name = settings.collector_name.strip()
if not (token and contact and name):
    raise SystemExit("GITHUB_TOKEN, COLLECTOR_NAME and COLLECTOR_CONTACT_EMAIL must be set")

count = RequestCount(Path(settings.data_dir) / "requests" / f"{SITE}.json", SITE, limit=8000)
session = requests.Session()
session.trust_env = False
headers = {
    "User-Agent": f"{name}/{__version__} (research tool; contact: {contact})",
    "From": contact,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
    "Authorization": f"Bearer {token}",
}

for number, url in enumerate(ASKED, start=1):
    if number > 1:
        time.sleep(1.5)
    count.add_one()
    response = session.get(url, headers=headers, timeout=(10, 30), allow_redirects=False)
    print(f"--- request {number}: status {response.status_code}")
    for header in SHOWN_HEADERS:
        value = response.headers.get(header)
        if value is not None:
            print(f"  {header}: {value[:120]}")
    print("  etag present:", "etag" in response.headers)
    print("  last-modified present:", "last-modified" in response.headers)
    print("  bytes of the answer:", len(response.content))
    try:
        answer = response.json()
    except ValueError:
        print("  the answer is not JSON")
        continue
    if isinstance(answer, dict):
        print("  keys:", sorted(answer))
        if "content" in answer:
            print("  type:", answer.get("type"), " encoding:", answer.get("encoding"))
            print("  name:", answer.get("name"), " path:", answer.get("path"), " size:", answer.get("size"))
            raw = base64.b64decode(answer["content"])
            print("  bytes after base64:", len(raw), " the same as size:", len(raw) == answer.get("size"))
            try:
                raw.decode("utf-8")
                print("  the text is UTF-8")
            except UnicodeDecodeError:
                print("  the text is not UTF-8")
            print("  _links keys:", sorted(answer.get("_links") or {}))
        if "message" in answer:
            print("  message:", str(answer["message"])[:80])
            print("  status field:", answer.get("status"))
        if "url" in answer and number == 2:
            print("  url of a moved repository, shape:", json.dumps(answer["url"])[:20], "...")

print("requests counted for", SITE, "so far:", count.sent())
