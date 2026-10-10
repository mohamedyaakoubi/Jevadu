"""The data that a page built with Next.js carries in its scripts.

Such a page holds its data as text. Each script calls `self.__next_f.push([1, "<text>"])`. The
texts of all the scripts, put together in order, hold JSON objects among other things: rows that
start with a short id, and plain text. One JSON object can be cut in two by the end of a script,
so the texts are joined before anything is looked for in them.

Read on real pages of ethglobal.com on 10 October 2026. Nothing here knows about one site.
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

# The second item of the pushed list is a string written as a JavaScript string. For the letters
# these pages use, that is also a JSON string, so json.loads reads it.
_PUSH = re.compile(r'self\.__next_f\.push\(\[1,\s*("(?:[^"\\]|\\.)*")\s*\]\)', re.DOTALL)

# How many "{" to the left of a key are tried as the start of its object. The object of a key
# starts close to it. The limit only stops a long walk through a page with no such object.
_MAX_STARTS = 50


def page_data_text(soup: BeautifulSoup) -> str:
    """The texts that the scripts of the page push, decoded and joined in the order of the page."""
    parts: list[str] = []
    for script in soup.find_all("script"):
        for literal in _PUSH.findall(script.string or ""):
            try:
                text = json.loads(literal)
            except ValueError:
                continue  # not a string we can read: it holds no data for us
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def objects_with_key(text: str, key: str) -> list[dict]:
    """Every JSON object in `text` that has `key` as one of its own keys, in the order of `text`.

    The text around an object does not have to be JSON. For each place where the key is written,
    the "{" signs to its left are tried, the nearest first, until one of them starts an object
    that holds the key itself (and not only inside a deeper object or inside a string).
    """
    decoder = json.JSONDecoder()
    needle = f'"{key}":'
    found: dict[int, dict] = {}
    at = text.find(needle)
    while at != -1:
        start = at
        for _ in range(_MAX_STARTS):
            start = text.rfind("{", 0, start)
            if start == -1:
                break
            try:
                value, end = decoder.raw_decode(text, start)
            except ValueError:
                continue
            if isinstance(value, dict) and key in value and end > at:
                found.setdefault(start, value)
                break
        at = text.find(needle, at + len(needle))
    return [found[start] for start in sorted(found)]
