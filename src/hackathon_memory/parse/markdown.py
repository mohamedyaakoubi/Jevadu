"""Take people out of a Markdown text, such as the README of a project's code (design 5.4).

A README is written by a team for other developers. It can say about people what a project page
says, and more: a part that lists the team, with names, photos and links to profiles. The tool
keeps no names, photos or profiles of team members (design rule 11). So before a README is
saved, two things are done.

1. **A part about the team is cut out whole**: its title and everything under it. It ends at the
   next title of the same or a higher level, or at a title that names a part of the project,
   such as "Installation" or "Features". A part about the team is one whose title is in
   `TEAM_TITLES`, after signs, emoji and a name after a colon are taken away: "## 👥 Our Team",
   "### Team: Pebble" and "<h2>Contributors</h2>" are three of them.
2. **In the rest, the words of people.py are hidden**: handles, email addresses, links to
   profiles and to the photo of an account. A Markdown link to a profile is hidden with its
   words, because the words of such a link are most often the name of the person. Inside code,
   only email addresses are hidden.

Both are counted. So is every Hedera id that stood in a part that was cut out, so that a person
can see whether the cut ever takes something that the check needs. The text that was cut is
kept nowhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hackathon_memory.parse.hedera_ids import find_ids
from hackathon_memory.parse.people import (
    HIDDEN_LINK,
    HIDDEN_PHOTO,
    hide_in_code,
    hide_in_text,
    is_photo_of_an_account,
    profile_site,
)

# The titles of a part about the team, in small letters, without signs and emoji.
TEAM_TITLES = frozenset(
    {
        "team",
        "the team",
        "our team",
        "my team",
        "team members",
        "team member",
        "members",
        "meet the team",
        "meet our team",
        "core team",
        "project team",
        "hackathon team",
        "team info",
        "team information",
        "team details",
        "about the team",
        "about us",
        "who we are",
        "contributors",
        "authors",
        "author",
        "maintainers",
        "built by",
        "made by",
        "created by",
        "developed by",
        "builders",
        "the builders",
        "creators",
        "founders",
        "contact",
        "contacts",
        "contact us",
        "get in touch",
        "reach out",
    }
)
# Words in a title that name a part of the project: such a title ends a part about the team,
# whatever its level.
_PART_OF_THE_PROJECT = re.compile(
    r"\b(?:install\w*|setup|set up|getting started|quick ?start|usage|features?|architecture|"
    r"tech|stack|technolog\w*|how it works|demo|deploy\w*|licen[cs]e|roadmap|problem|solution|"
    r"overview|contracts?|hedera|hashgraph|tokens?|topics?|tests?|testing|structure|"
    r"environment|prerequisites|requirements|api|links|resources|screenshots?|video|pitch|"
    r"future|next steps|acknowledg\w*|contributing|faq|docs|documentation|configuration|"
    r"running|build|building)\b"
)

_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_SETEXT_LINE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_HTML_HEADING = re.compile(r"^\s*<h([1-6])\b[^>]*>(.*?)</h\1\s*>\s*$", re.IGNORECASE)
_NOT_A_SETEXT_TITLE = re.compile(r"^\s*(?:[-*+>]|\d+[.)])\s")  # an item of a list, a quote
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
# A Markdown link or image: [words](address "title").
_MARKDOWN_LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"\n]*\")?\s*\)")
# An anchor of HTML, on one line: <a href="address">words</a>.
_HTML_ANCHOR = re.compile(
    r"<a\b[^>]*?\bhref\s*=\s*[\"']([^\"']+)[\"'][^>]*>.*?</a\s*>", re.IGNORECASE
)
# An image of HTML: <img src="address">.
_HTML_IMAGE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)


@dataclass(frozen=True)
class MarkdownHidden:
    text: str
    words_hidden: int  # handles, addresses, links to profiles and photos, outside the cut
    team_parts_cut: int
    team_lines_cut: int
    ids_in_the_cut: int  # Hedera ids that stood in a part that was cut out


def title_key(title: str) -> str:
    """A title in small letters, with no tags, signs or emoji, and no name after a colon."""
    text = re.sub(r"<[^>]+>", " ", title)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # a link or an image: its words
    text = re.split(r":|\s[-|–—]\s", text, maxsplit=1)[0]  # "Team: Pebble" is "Team"
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def is_team_title(title: str) -> bool:
    return title_key(title) in TEAM_TITLES


def names_a_part_of_the_project(title: str) -> bool:
    key = title_key(title)
    return bool(_PART_OF_THE_PROJECT.search(key)) and key not in TEAM_TITLES


def hide_in_markdown(text: str) -> MarkdownHidden:
    """The text with its parts about the team cut out, and words about people hidden."""
    lines = text.split("\n")
    in_code, titles = _shape(lines)
    cut, parts = _team_parts(titles, len(lines))
    kept: list[str] = []
    hidden = 0
    for number, line in enumerate(lines):
        if number in cut:
            continue
        shown, count = hide_in_code(line) if in_code[number] else _hide_in_a_line(line)
        kept.append(shown)
        hidden += count
    cut_text = "\n".join(lines[number] for number in sorted(cut))
    return MarkdownHidden(
        text="\n".join(kept),
        words_hidden=hidden,
        team_parts_cut=parts,
        team_lines_cut=len(cut),
        ids_in_the_cut=len({found.entity_id for found in find_ids(cut_text)}),
    )


def _shape(lines: list[str]) -> tuple[list[bool], dict[int, tuple[int, str]]]:
    """Which lines are code, and the titles: their line, level and words."""
    in_code = [False] * len(lines)
    titles: dict[int, tuple[int, str]] = {}
    underlines: set[int] = set()  # the line under a title of the other kind ("Team" / "----")
    fence: tuple[str, int] | None = None  # the sign and the length of an open fence
    for number, raw in enumerate(lines):
        line = raw.rstrip("\r")
        if number in underlines:
            continue
        if fence is not None:
            in_code[number] = True
            closing = _FENCE_CLOSE.match(line)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= fence[1]:
                fence = None
            continue
        opening = _FENCE_OPEN.match(line)
        if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
            fence = (opening.group(1)[0], len(opening.group(1)))
            in_code[number] = True
            continue
        atx = _ATX.match(line)
        html = _HTML_HEADING.match(line)
        if atx:
            titles[number] = (len(atx.group(1)), atx.group(2) or "")
        elif html:
            titles[number] = (int(html.group(1)), html.group(2))
        elif (
            line.strip()
            and number + 1 < len(lines)
            and _SETEXT_LINE.match(lines[number + 1].rstrip("\r"))
            and not _NOT_A_SETEXT_TITLE.match(line)
        ):
            level = 1 if lines[number + 1].strip().startswith("=") else 2
            titles[number] = (level, line.strip())
            underlines.add(number + 1)
    return in_code, titles


def _team_parts(titles: dict[int, tuple[int, str]], line_count: int) -> tuple[set[int], int]:
    """The numbers of the lines that belong to a part about the team, and how many parts."""
    cut: set[int] = set()
    parts = 0
    order = sorted(titles)
    for at, start in enumerate(order):
        level, words = titles[start]
        if start in cut or not is_team_title(words):
            continue
        end = line_count
        for later in order[at + 1 :]:
            later_level, later_words = titles[later]
            if later_level <= level or names_a_part_of_the_project(later_words):
                end = later
                break
        cut.update(range(start, end))
        parts += 1
    return cut, parts


def _hide_in_a_line(line: str) -> tuple[str, int]:
    """A line of text: code spans keep everything but addresses, the rest is hidden as text."""
    pieces: list[str] = []
    hidden = 0
    last = 0
    for span in _INLINE_CODE.finditer(line):
        text, count = _hide_links_and_words(line[last : span.start()])
        code, in_code = hide_in_code(span.group(0))
        pieces.extend((text, code))
        hidden += count + in_code
        last = span.end()
    text, count = _hide_links_and_words(line[last:])
    pieces.append(text)
    return "".join(pieces), hidden + count


def _hide_links_and_words(text: str) -> tuple[str, int]:
    """Links to a profile or a photo go whole, with their words. Then the words of the rest."""
    hidden = 0

    def markdown_link(match: re.Match[str]) -> str:
        nonlocal hidden
        image, address = match.group(1), match.group(3)
        if is_photo_of_an_account(address) or (image and profile_site(address)):
            hidden += 1
            return HIDDEN_PHOTO
        if profile_site(address):
            hidden += 1
            return HIDDEN_LINK
        return match.group(0)

    def html_anchor(match: re.Match[str]) -> str:
        nonlocal hidden
        if profile_site(match.group(1)) or is_photo_of_an_account(match.group(1)):
            hidden += 1
            return HIDDEN_LINK
        return match.group(0)

    def html_image(match: re.Match[str]) -> str:
        nonlocal hidden
        if is_photo_of_an_account(match.group(1)) or profile_site(match.group(1)):
            hidden += 1
            return HIDDEN_PHOTO
        return match.group(0)

    text = _MARKDOWN_LINK.sub(markdown_link, text)
    text = _HTML_ANCHOR.sub(html_anchor, text)
    text = _HTML_IMAGE.sub(html_image, text)
    text, count = hide_in_text(text)
    return text, hidden + count
