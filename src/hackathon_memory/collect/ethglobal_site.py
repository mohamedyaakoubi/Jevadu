"""The addresses of ETHGlobal that the collector knows. Nothing here sends a request."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

SITE = "ethglobal.com"
ROBOTS_URL = f"https://{SITE}/robots.txt"
PROJECT_PAGE_PATH = re.compile(r"^/showcase/[A-Za-z0-9-]+$")

# The most requests that are ever sent to this site, over all commands and all days. Each one is
# counted on disk (polite.RequestCount). The first collection, the projects with a Hedera prize,
# used 140. On 10 October 2026 the maintainer decided to read every project that the showcase
# ties to Hedera: 658 project pages, and the 21 pages of the list once more. So the limit for
# this site is 800, and it is not raised without a new decision.
REQUEST_LIMIT = 800


def looks_like_a_project_page(url: str) -> bool:
    """The address has the form of one showcase project and nothing more."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != SITE or parts.query or parts.fragment:
        return False
    if parts.port not in (None, 443) or parts.username or parts.password:
        return False  # no other port, and no login written into the address
    return bool(PROJECT_PAGE_PATH.match(parts.path.rstrip("/")))
