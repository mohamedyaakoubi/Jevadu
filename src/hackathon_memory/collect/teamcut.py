"""Cut the team part out of a page before it is saved (design 5.3 and 5.7).

The sites were promised: "no names, photos or profiles of team members". So the part of a
page that shows the team never reaches the disk. This module is the only place that decides
what a page looks like when it is saved.

It FAILS CLOSED. If it cannot be sure the team part is gone, it raises CutFailed, and the
page is not saved. There are two kinds. TeamShapeChanged means the page is not shaped as the
rules expect, which will repeat on other pages, so the run should stop. TeamTextRemains means
the cut worked but the same text is also somewhere else in this one page (for example a name
written in the project's own description), so that page is skipped and the run goes on.
Three guards:

1. A rule marked `required` must find its element. A page that has no team part where we
   expect one means the page changed shape, so we cannot trust the cut.
2. Data blocks (JSON in script tags) lose the keys that hold people, by name.
3. A self-check. Before the cut, the strings of the team part are collected in memory:
   visible texts and link, image and label values. After the cut, the page must not contain
   any of them. A string that also stands somewhere else in the visible page ("Team",
   "View profile", a menu word) is generic and is not searched. A name that was copied into
   a script block is not generic, so it is found, and the page is refused.

Nothing that is collected here is written anywhere: not to disk, not to a log, not into an
error message. An error says how many strings were found, never which.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString, Tag

# Attributes whose values can identify a person: a profile link, an avatar file, a label,
# the text of a meta tag.
_HARVEST_ATTRIBUTES = ("href", "src", "srcset", "alt", "title", "aria-label", "content")
_MIN_LENGTH = 4
_HAS_LETTER = re.compile(r"[A-Za-z]")
_JSON_SCRIPT_TYPES = {"application/json", "application/ld+json"}

# Metadata about people that sits outside any team block. Removed on every page.
PERSONAL_METADATA = (
    "meta[name='author']",
    "meta[property='article:author']",
    "meta[name='twitter:creator']",
    "link[rel='author']",
)


class CutFailed(Exception):
    """The team part could not be removed with certainty. The page must not be saved."""


class TeamShapeChanged(CutFailed):
    """The page does not have the shape the rules expect. This will repeat on other pages."""


class TeamTextRemains(CutFailed):
    """The cut worked, but text from the team part is also elsewhere in this one page."""


@dataclass(frozen=True)
class CutRule:
    selector: str
    required: bool = True


@dataclass(frozen=True)
class CutPolicy:
    rules: tuple[CutRule, ...]
    # Keys (lower case) that hold people inside JSON data blocks. The key and its value go.
    json_blocklist: frozenset[str] = frozenset()
    # Selectors that must match NOTHING. A page that shows a profile link or an avatar is a page
    # that has changed shape: the cut cannot be trusted, so the run must stop.
    tripwires: tuple[str, ...] = ()
    # Keys (lower case) that hold people. If one of them stands in a script that is not valid
    # JSON (the data of a React page is kept as text), the cut cannot remove it, so the page is
    # refused as a changed shape.
    script_person_keys: frozenset[str] = frozenset()
    # Texts (lower case) that name the site itself, for example its name and its social handle.
    # They sit in the "personal" metadata of every page, but they are not about a person, so the
    # self-check does not look for them.
    site_names: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CutReport:
    elements_removed: int
    json_keys_removed: int
    strings_guarded: int

    def as_dict(self) -> dict[str, int]:
        return {
            "elements_removed": self.elements_removed,
            "json_keys_removed": self.json_keys_removed,
            "strings_guarded": self.strings_guarded,
        }


def _attribute_values(tag: Tag) -> Iterable[str]:
    for name, value in tag.attrs.items():
        if name in _HARVEST_ATTRIBUTES or (name.startswith("data-") and name != "data-testid"):
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, str):
                    if name == "srcset":
                        yield from (part.split()[0] for part in item.split(",") if part.strip())
                    else:
                        yield item


def _strings_of(tag: Tag) -> set[str]:
    """The texts and the identifying attribute values inside `tag`, `tag` itself included."""
    found: set[str] = set(tag.stripped_strings)
    for element in [tag, *tag.find_all(True)]:
        found.update(v.strip() for v in _attribute_values(element))
    return {s for s in found if len(s) >= _MIN_LENGTH and _HAS_LETTER.search(s)}


def _visible_strings_outside(soup: BeautifulSoup, blocks: list[Tag]) -> set[str]:
    """Texts and attribute values of the page that are not in a block, not in script or style."""
    inside: set[int] = set()
    for block in blocks:
        inside.add(id(block))
        inside.update(id(t) for t in block.find_all(True))
    found: set[str] = set()
    for element in soup.find_all(True):
        if id(element) in inside or element.name in ("script", "style"):
            continue
        found.update(v.strip() for v in _attribute_values(element))
        for child in element.find_all(string=True, recursive=False):
            # Comments and other special strings are not visible text, so they do not count.
            if type(child) is NavigableString and child.strip():
                found.add(child.strip())
    return {s for s in found if len(s) >= _MIN_LENGTH and _HAS_LETTER.search(s)}


def _drop_keys(value: object, blocklist: frozenset[str]) -> tuple[object, int]:
    removed = 0
    if isinstance(value, dict):
        kept = {}
        for key, item in value.items():
            if str(key).lower() in blocklist:
                removed += 1
                continue
            cleaned, count = _drop_keys(item, blocklist)
            kept[key] = cleaned
            removed += count
        return kept, removed
    if isinstance(value, list):
        cleaned_items = []
        for item in value:
            cleaned, count = _drop_keys(item, blocklist)
            cleaned_items.append(cleaned)
            removed += count
        return cleaned_items, removed
    return value, 0


# A key in JSON written as text. Inside a string of a script the quotes are written \", so the
# pattern accepts a backslash before each quote.
_SCRIPT_KEY = re.compile(r'\\*"([A-Za-z_][A-Za-z0-9_]*)\\*"\s*:')


def _refuse_person_keys(script_text: str, policy: CutPolicy) -> None:
    """A script we cannot parse must not hold a key that holds people. Only the key is named."""
    if not policy.script_person_keys:
        return
    for key in _SCRIPT_KEY.findall(script_text):
        if key.lower() in policy.script_person_keys:
            raise TeamShapeChanged(f"a data block holds the key {key!r}, which holds people")


def _top_level(matches: list[Tag]) -> list[Tag]:
    """Drop every match that sits inside another match, so nothing is removed twice."""
    ids = {id(m) for m in matches}
    return [m for m in matches if not any(id(p) in ids for p in m.parents)]


def cut_team(body: bytes, policy: CutPolicy) -> tuple[bytes, CutReport]:
    """Return the page without its team part, or raise CutFailed."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise TeamShapeChanged("the page is not UTF-8, so the cut cannot be checked") from None
    soup = BeautifulSoup(text, "lxml")

    for selector in policy.tripwires:
        if soup.select_one(selector) is not None:
            raise TeamShapeChanged(f"the page shows something that should not exist: {selector!r}")

    # Rules of the policy, then the personal metadata that every page loses.
    blocks: list[Tag] = []
    for rule in policy.rules:
        matches = soup.select(rule.selector)
        if not matches and rule.required:
            raise TeamShapeChanged(f"no element matches the required rule {rule.selector!r}")
        blocks.extend(matches)
    metadata = [m for selector in PERSONAL_METADATA for m in soup.select(selector)]
    blocks = _top_level(blocks)

    # Collect what must be gone, before anything is removed.
    guarded: set[str] = set()
    for element in [*blocks, *metadata]:
        guarded |= _strings_of(element)
    guarded -= _visible_strings_outside(soup, [*blocks, *metadata])
    guarded = {s for s in guarded if s.lower() not in policy.site_names}

    removed = 0
    for element in [*blocks, *metadata]:
        if not getattr(element, "decomposed", False):  # a nested one is already gone
            element.decompose()
            removed += 1

    json_keys_removed = 0
    for script in soup.find_all("script"):
        script_text = script.get_text()
        is_data = script.get("type") in _JSON_SCRIPT_TYPES or script.get("id") == "__NEXT_DATA__"
        data = None
        if is_data and script_text:
            try:
                data = json.loads(script_text)
            except ValueError:
                data = None  # not JSON after all: the keys are looked for in the text below
        if data is None:
            _refuse_person_keys(script_text, policy)
            continue
        cleaned, count = _drop_keys(data, policy.json_blocklist)
        if count:
            script.string = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
            json_keys_removed += count

    output = str(soup)
    haystacks = (output.lower(), html.unescape(output).lower())
    leaked = [s for s in guarded if any(s.lower() in h for h in haystacks)]
    if leaked:
        raise TeamTextRemains(
            f"{len(leaked)} string(s) from the team part are still in the page after the cut"
        )

    report = CutReport(
        elements_removed=removed,
        json_keys_removed=json_keys_removed,
        strings_guarded=len(guarded),
    )
    return output.encode("utf-8"), report
