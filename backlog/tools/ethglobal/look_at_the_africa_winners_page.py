"""A first look at hedera-hackathon.hashgraph.swiss: its rules, and the shape of its first page.

    PYTHONIOENCODING=utf-8 python swiss_look.py

The maintainer named this site on 10 October 2026: "it has few winning projects it would be worth
it to get them too directly". Before anything is collected, the rules of the site are read
(design rule 10). At most three requests, two seconds apart, each with the name of the tool and
the contact address. Nothing is saved. Only the shape of the page is printed: titles of sections
as lengths, link targets, counts. No name of a person.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from urllib.parse import urljoin, urlsplit

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bs4 import BeautifulSoup  # noqa: E402

from hackathon_memory.collect.polite import (  # noqa: E402
    CollectorIdentity,
    FetchFailed,
    PoliteClient,
    StopCollecting,
)
from hackathon_memory.collect.robots import RobotsRules  # noqa: E402
from hackathon_memory.collect.skeleton import skeleton  # noqa: E402
from hackathon_memory.settings import Settings  # noqa: E402

SITE = "hedera-hackathon.hashgraph.swiss"
HOME = f"https://{SITE}/"
RULES_WORDS = re.compile(r"terms|conditions|legal|privacy|imprint|cookie|rules|policy", re.I)


def allow(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname == SITE and parts.port in (None, 443)


def main() -> int:
    identity = CollectorIdentity.from_settings(Settings())
    client = PoliteClient(site=SITE, identity=identity, allow=allow, is_enabled=lambda: True, max_requests=3)
    try:
        robots = client.get(f"https://{SITE}/robots.txt")
        print(f"robots.txt: status {robots.status}, {len(robots.body)} bytes")
        rules_text = robots.body.decode("utf-8", errors="replace") if robots.status == 200 else ""
        if robots.status == 200 and "text/plain" in robots.content_type:
            print("  " + "\n  ".join(rules_text.splitlines()[:25]))
        elif robots.status == 200:
            print(f"  (not a text file: {robots.content_type}), so it is not taken for rules")
            rules_text = ""
        rules = RobotsRules(rules_text)
        if not rules.allows(identity.name, HOME):
            print("robots.txt does not allow this tool to read the first page. Stopped.")
            return 1
        home = client.get(HOME)
    except (StopCollecting, FetchFailed) as stop:
        print(f"STOPPED: {stop}")
        return 1
    print(f"first page: status {home.status}, {len(home.body)} bytes, type {home.content_type}, final address {home.final_url}")
    if home.status != 200:
        return 1
    html = home.body.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True)[:90] if soup.title else "-"
    print(f"title of the page: {title!r}")
    generator = soup.find("meta", attrs={"name": "generator"})
    print(f"made with: {generator.get('content') if generator else 'not said'}")
    hrefs = [urljoin(HOME, str(a['href'])) for a in soup.find_all("a", href=True)]
    hosts = Counter(urlsplit(h).hostname or "" for h in hrefs)
    print(f"links: {len(hrefs)}; by host: {dict(hosts.most_common(12))}")
    inside = sorted({urlsplit(h).path for h in hrefs if urlsplit(h).hostname == SITE})
    print(f"addresses inside the site ({len(inside)}): {inside[:40]}")
    rule_links = sorted({h for h in hrefs if RULES_WORDS.search(h)})
    rule_texts = sorted({" ".join(a.get_text(' ').split())[:40] for a in soup.find_all('a', href=True)
                         if RULES_WORDS.search(" ".join(a.get_text(' ').split()))})
    print(f"links that look like rules of the site: {rule_links[:10]}")
    print(f"link words that look like rules: {rule_texts[:10]}")
    words = {w: len(re.findall(w, html, re.I)) for w in ("winner", "prize", "project", "track", "team", "github", "hashscan", "dorahacks", "hedera")}
    print(f"how often these words stand in the page: {words}")
    scripts = [s for s in soup.find_all("script")]
    print(f"scripts: {len(scripts)}; with a data block (__NEXT_DATA__ or self.__next_f): "
          f"{sum(1 for s in scripts if s.get('id') == '__NEXT_DATA__' or '__next_f' in (s.string or ''))}")
    print(f"images: {len(soup.find_all('img'))}; headings h1 to h3: {len(soup.find_all(['h1', 'h2', 'h3']))}")
    print("\nshape of the page (texts are shown as lengths):")
    print("\n".join(skeleton(home.body).splitlines()[:70]))
    print(f"\nrequests sent: {client.requests_made} (at most 3). Nothing was saved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
