"""The two words that start with @ and are not package scopes: what kind are they? No request.

A word is printed only when it is a known word of code (a tag of a code comment, a decorator, a
package without a slash). Any other word could be the handle of a person or of a company: it is
not printed. Only its kind of place is: the section, whether it is inside code, and whether the
word right before it is a word such as "follow" or "by".
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"
AT_WORD = re.compile(r"(?<![A-Za-z0-9._%+-/])@([A-Za-z0-9_-]{2,40})(?![A-Za-z0-9_/-])")
CODE_WORDS = {
    "notice", "param", "dev", "return", "returns", "title", "custom", "inheritdoc", "media",
    "import", "types", "override", "component", "injectable", "decorator", "app", "tool",
    "property", "staticmethod", "classmethod", "openzeppelin", "hashgraph", "next", "latest",
}
SOCIAL_HINT = re.compile(r"\b(follow|twitter|x\.com|telegram|discord|by|contact|dm|tweet|handle)\b", re.I)

for meta_path in sorted(RAW.glob("*.meta.json")):
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    body_path = meta_path.with_name(meta_path.name.replace(".meta.json", ".html"))
    if not body_path.exists():
        continue
    soup = BeautifulSoup(body_path.read_text(encoding="utf-8", errors="replace"), "lxml")
    for junk in soup(["script", "style"]):
        junk.decompose()
    for node in soup.find_all(string=AT_WORD):
        text = str(node)
        for match in AT_WORD.finditer(text):
            word = match.group(1)
            section = node.find_previous("h3")
            where = " ".join(section.get_text().split())[:30] if section else "(before any section)"
            in_code = any(parent.name in ("code", "pre") for parent in node.parents)
            before = text[max(0, match.start() - 40) : match.start()]
            after = text[match.end() : match.end() + 3]
            kind = "a word of code" if word.lower() in CODE_WORDS else "NOT a known word of code"
            shown = f"@{word}" if word.lower() in CODE_WORDS else f"@({len(word)} letters)"
            print(
                f"{shown}: {kind}; section {where!r}; inside code: {in_code}; "
                f"a social word just before it: {bool(SOCIAL_HINT.search(before))}; "
                f"starts with a capital: {word[0].isupper()}; has a digit: {any(c.isdigit() for c in word)}; "
                f"followed by {after[:1]!r}"
            )
