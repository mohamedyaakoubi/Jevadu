"""Print the structure of a saved page without printing its people.

    python -m hackathon_memory.collect.skeleton path/to/page.html

Why it exists. To write the page shape of a site (which element is the team block, where the
project links are), someone has to read a real page. But a real page shows names of people, and
the sites were promised that we do not collect them (design 5.7). This tool shows the SHAPE of
a page and none of its text:

* every text is shown as its length, for example <text 16 chars>;
* a heading is shown only if it is one of the plain section words in SECTION_WORDS;
* a link is shown as its host and the shape of its path: the first words of a path are shown only
  when they are known structure words, and the rest becomes {x};
* a data block (JSON in a script tag) is shown as keys and kinds of values, never values;
* the data that the scripts of a Next.js page push is shown as its keys and how often each key
  stands in it, never a value. A key seen once is not shown, and the keys of a map of records
  are not counted: such a key can be the handle of a person;
* a meta tag is shown by its name, never by its content.

Nothing the tool prints can name a person, except a class name or an id that happens to hold one.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from hackathon_memory.parse.pagedata import page_data_text

# Headings that are plain section words. Any other heading is shown by its length only.
SECTION_WORDS = {
    "team",
    "built with",
    "project description",
    "how it's made",
    "how its made",
    "description",
    "prizes",
    "winners",
    "links",
    "tech stack",
    "hedera",
    "demo",
    "video",
    "overview",
    "about",
    "project",
    "winner of",
    "created at",
}
# Words that are part of the structure of a path and not a person or a project.
PATH_WORDS = {
    "showcase",
    "events",
    "prizes",
    "hackers",
    "projects",
    "users",
    "user",
    "u",
    "profile",
    "team",
    "teams",
    "about",
    "hedera",
    "sponsors",
    "partners",
    "robots.txt",
}
_MAX_DEPTH = 12
_JSON_TYPES = {"application/json", "application/ld+json"}


def path_shape(url: str) -> str:
    """The host and the shape of the path: known structure words stay, the rest becomes {x}."""
    parts = urlsplit(url)
    segments = [s for s in parts.path.split("/") if s]
    shown = [s if s.lower() in PATH_WORDS else "{x}" for s in segments]
    shape = "/" + "/".join(shown)
    if parts.query:
        shape += "?{query}"
    host = parts.netloc
    return f"{host}{shape}" if host else shape


def _kinds(value: object, path: str, lines: list[str], depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(value, dict):
        records = list(value.values())
        same_shape = len({tuple(sorted(r)) for r in records if isinstance(r, dict)}) == 1
        if len(records) >= 2 and all(isinstance(r, dict) for r in records) and same_shape:
            # A map from something to records of one shape. The keys may be handles or ids of
            # people, so they are not shown.
            lines.append(f"{path}: map of {len(records)} records")
            _kinds(records[0], f"{path}{{}}", lines, depth + 1)
            return
        for key, item in value.items():
            _kinds(item, f"{path}.{key}" if path else str(key), lines, depth + 1)
    elif isinstance(value, list):
        lines.append(f"{path}: list of {len(value)}")
        if value:
            _kinds(value[0], f"{path}[]", lines, depth + 1)
    else:
        lines.append(f"{path}: {type(value).__name__}")


_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,40}$")
_SHOWN_KEYS = 90


def _is_map_of_records(value: dict) -> bool:
    records = list(value.values())
    shapes = {tuple(sorted(r)) for r in records if isinstance(r, dict)}
    return len(records) >= 2 and all(isinstance(r, dict) for r in records) and len(shapes) == 1


def _count_keys(value: object, counts: Counter[str], depth: int = 0) -> None:
    if depth > 60:
        return
    if isinstance(value, dict):
        if not _is_map_of_records(value):
            counts.update(key for key in value if _KEY.match(key))
        for item in value.values():
            _count_keys(item, counts, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _count_keys(item, counts, depth + 1)


def pushed_keys(text: str) -> Counter[str]:
    """How often each key stands in the JSON of the text that a Next.js page pushes."""
    counts: Counter[str] = Counter()
    decoder = json.JSONDecoder()
    at = 0
    while True:
        starts = [i for i in (text.find("{", at), text.find("[", at)) if i != -1]
        if not starts:
            return counts
        start = min(starts)
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            at = start + 1
            continue
        _count_keys(value, counts)
        at = end


def _attributes(tag: Tag) -> str:
    shown: list[str] = []
    for name, value in tag.attrs.items():
        if name in ("class", "id", "style"):
            continue
        text = " ".join(value) if isinstance(value, list) else str(value)
        if name in ("href", "src", "action"):
            shown.append(f"{name}={path_shape(text)}")
        elif name == "srcset":
            shown.append("srcset=<list>")
        elif name in ("alt", "title", "aria-label", "content", "value", "placeholder"):
            shown.append(f"{name}=<text {len(text)} chars>")
        elif name.startswith("data-"):
            shown.append(f"{name}=<{len(text)} chars>")
        elif name in ("type", "rel", "name", "property", "charset", "lang", "role"):
            shown.append(f"{name}={text}")
        else:
            shown.append(name)
    return f"[{', '.join(shown)}]" if shown else ""


def _label(tag: Tag) -> str:
    label = tag.name
    if tag.get("id"):
        label += f"#{tag['id']}"
    for css in tag.get("class", []) or []:
        label += f".{css}"
    return label + _attributes(tag)


def _walk(tag: Tag, depth: int, lines: list[str]) -> None:
    indent = "  " * depth
    if tag.name in ("script", "style"):
        kind = tag.get("type") or tag.name
        lines.append(f"{indent}{_label(tag)} <{len(tag.string or '')} chars of {kind}>")
        return
    own_text = [
        s.strip()
        for s in tag.children
        if isinstance(s, NavigableString) and not isinstance(s, Comment) and s.strip()
    ]
    line = f"{indent}{_label(tag)}"
    if own_text:
        joined = " ".join(own_text)
        is_heading = tag.name in ("h1", "h2", "h3", "h4", "h5", "h6", "summary", "legend")
        if is_heading and joined.lower().rstrip(":") in SECTION_WORDS:
            line += f' "{joined}"'
        else:
            line += f" <text {len(joined)} chars>"
    lines.append(line)
    if depth >= _MAX_DEPTH:
        if tag.find(True):
            lines.append(f"{indent}  ... (deeper elements not shown)")
        return
    for child in tag.children:
        if isinstance(child, Tag):
            _walk(child, depth + 1, lines)


def skeleton(html: bytes) -> str:
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml")
    out: list[str] = [f"Size: {len(html)} bytes"]

    title = soup.title.string if soup.title and soup.title.string else ""
    out.append(f"Title: <text {len(title)} chars>")

    names = sorted(
        {(m.get("name") or m.get("property") or "?") for m in soup.find_all("meta") if m.attrs}
    )
    out.append(f"Meta tags (names only): {', '.join(str(n) for n in names) or 'none'}")

    out.append("Data blocks (keys and kinds, never values):")
    found_data = False
    for script in soup.find_all("script"):
        if script.get("type") in _JSON_TYPES or script.get("id") == "__NEXT_DATA__":
            found_data = True
            out.append(f"  script#{script.get('id', '')} type={script.get('type', '')}")
            try:
                data = json.loads(script.string or "")
            except ValueError:
                out.append("    (not valid JSON)")
                continue
            lines: list[str] = []
            _kinds(data, "", lines)
            out.extend(f"    {line}" for line in lines[:80])
    if not found_data:
        out.append("  none")

    out.append("Data pushed by the scripts of a Next.js page (key: count, never a value):")
    pushed = page_data_text(soup)
    if not pushed:
        out.append("  none")
    else:
        counts = pushed_keys(pushed)
        once = sum(1 for count in counts.values() if count == 1)
        out.append(
            f"  {len(pushed)} characters, {len(counts)} different keys "
            f"({once} seen only once, not shown)"
        )
        shown = [f"{key}: {count}" for key, count in counts.most_common() if count >= 2]
        for at in range(0, min(len(shown), _SHOWN_KEYS), 6):
            out.append("  " + ", ".join(shown[at : at + 6]))

    out.append("Link shapes (count, shape):")
    shapes = Counter(path_shape(str(a["href"])) for a in soup.find_all("a", href=True))
    for shape, count in shapes.most_common():
        out.append(f"  {count:3}  {shape}")
    if not shapes:
        out.append("  none")

    out.append("Structure (text is shown by length only):")
    root = soup.html or soup
    lines = []
    for child in root.children:
        if isinstance(child, Tag):
            _walk(child, 1, lines)
    out.extend(lines)
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m hackathon_memory.collect.skeleton path/to/page.html")
        return 2
    path = Path(argv[0])
    if not path.is_file():
        print(f"No such file: {path}")
        return 1
    print(skeleton(path.read_bytes()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
