"""What a project page of ETHGlobal's showcase says (design 6.1).

This is the one place that knows where a fact stands on a project page. The collector asks it
whether a page shows a Hedera prize, and so does the proof of the lists. The path from a saved
page to a card asks it for everything that a card takes from the page.

The shape of a page, read on the saved pages on 11 October 2026:

* a header with the name (h1), the short line (the p that follows) and up to two links, "Live
  Demo" and "Source Code";
* the title "Created At" with a link to the event, and, for a project with a prize, the title
  "Winner of" with one line for each prize: the sponsor, a dash, and the prize;
* the titles "Project Description" and "How it's Made", each followed by one box with the text.
  A team can write titles of its own inside such a box;
* the data of the page as text in its scripts. One object holds the project: its name, its short
  line, its event with the start time, its prizes, its links and its video.

The page and its data must tell the same story. Where they do not, the parser does not choose:
it raises PageShapeChanged, and a person looks.

The data also holds scores that the site computes for each project. They are never read out
(design rule 1): the parser takes the keys that it names here and no other.

A team can name a person inside its own text: a handle, an email address, a link to a profile.
These words are hidden in the short line and in the two texts before anything else is done with
them (people.py, design rule 11). So they reach no table, no model and no card. A link of the
header that leads to a profile site is kept without its address, for the same reason.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from hackathon_memory.collect.ethglobal_site import SITE
from hackathon_memory.parse.blocks import blocks_of, squash
from hackathon_memory.parse.hedera_ids import find_ids
from hackathon_memory.parse.pagedata import objects_with_key, page_data_text
from hackathon_memory.parse.people import hide_in_box, hide_in_text, profile_site
from hackathon_memory.parse.project import (
    CODE_LINK,
    DEMO_LINK,
    HEDERA_PRIZE,
    NO_PRIZE,
    OTHER_LINK,
    OTHER_PRIZE,
    EventRef,
    Link,
    Prize,
    ProjectPage,
    Section,
)

# Stored with every parsed page. A change of this word means: read every saved page again.
PARSER_VERSION = "ethglobal-page-13"  # "schedule" only right before an id (22 October 2026)

DESCRIPTION = "description"
HOW_ITS_MADE = "how_its_made"
_SECTION_TITLES = {"project description": DESCRIPTION, "how it's made": HOW_ITS_MADE}
_LINK_LABELS = {"source code": CODE_LINK, "live demo": DEMO_LINK}

# The line of a prize on a project page: the sponsor, a dash, the prize name, the place. The dash
# can be the plain one or one of the six from U+2010 to U+2015.
HEDERA_PRIZE_LINE = re.compile(r"^\s*hedera\s*[-‐-―]\s*\S", re.IGNORECASE)
_BEFORE_THE_DASH = re.compile(r"\s+[-‐-―]\s+")


class PageShapeChanged(Exception):
    """The page is not built as the parser expects. Nothing is guessed: a person must look."""


def _soup(html: bytes) -> BeautifulSoup:
    return BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml")


def _titles(soup: BeautifulSoup, wanted: str) -> list[Tag]:
    return [h for h in soup.find_all("h3") if squash(h.get_text()).lower() == wanted]


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str:
    return squash(value) if isinstance(value, str) else ""


# --------------------------------------------------------------------- the prizes


def _prize_lines(soup: BeautifulSoup) -> list[str]:
    lines: list[str] = []
    for heading in _titles(soup, "winner of"):
        block = heading.find_next_sibling()
        if block is not None:
            lines.extend(squash(line.get_text(" ")) for line in block.find_all("h4"))
    return lines


def prize_lines(html: bytes) -> list[str]:
    """The lines of the "Winner of" blocks of a page, one for each prize, with plain spaces."""
    return _prize_lines(_soup(html))


def took_a_hedera_prize(html: bytes) -> bool:
    """True if a "Winner of" block of the page has a line that starts with "Hedera -"."""
    return any(HEDERA_PRIZE_LINE.match(line) for line in prize_lines(html))


def prize_sponsors(html: bytes) -> list[str]:
    """The sponsors that the "Winner of" blocks name: the part of each line before the dash.

    Only for a message of the run, so that a person can see what a page shows.
    """
    names = (_BEFORE_THE_DASH.split(line, maxsplit=1)[0][:60] for line in prize_lines(html))
    return list(dict.fromkeys(name for name in names if name))


def _prizes(soup: BeautifulSoup, data: dict) -> tuple[Prize, ...]:
    """The prizes of the data, each with the line that the page shows for it."""
    lines = _prize_lines(soup)
    listed = data.get("prizes") or []
    if not isinstance(listed, list) or len(listed) != len(lines):
        raise PageShapeChanged(
            f'the page shows {len(lines)} line(s) under "Winner of", and its data does not '
            "hold as many prizes"
        )
    prizes: list[Prize] = []
    for line, item in zip(lines, listed, strict=True):
        inner = _dict(_dict(item).get("prize"))
        sponsor = _dict(inner.get("sponsor"))
        name = _text(sponsor.get("name"))
        if not name or not line.lower().startswith(name.lower()):
            raise PageShapeChanged(
                'a line under "Winner of" does not start with the sponsor that the data of '
                "the page names for it"
            )
        prizes.append(
            Prize(
                sponsor=name,
                sponsor_id=_text(_dict(sponsor.get("organization")).get("uuid")) or None,
                track=_text(inner.get("name")),
                award=_text(_dict(item).get("name")),
                kind=_text(inner.get("type")) or None,
                pool=_dict(item).get("poolPrize") is True,
                line=line,
            )
        )
    return tuple(prizes)


# --------------------------------------------------------------------- the whole page


def read_project_page(html: bytes, page: str) -> ProjectPage:
    """Everything that a card takes from the saved page at the address `page`."""
    soup = _soup(html)
    site_key = urlsplit(page).path.rstrip("/").rsplit("/", 1)[-1]
    data = _project_data(soup, site_key)
    header, name, short_line = _header(soup, data)
    short_line, hidden_in_the_line = hide_in_text(short_line)
    prizes = _prizes(soup, data)
    sections, boxes, hidden_in_the_texts = _sections(soup)
    links, hidden_in_the_links = _links(header)
    targets = [link.url for link in links if link.url]
    targets.extend(str(a["href"]) for box in boxes for a in box.find_all("a", href=True))
    video = _dict(data.get("video"))
    return ProjectPage(
        site=SITE,
        page=page,
        site_key=site_key,
        name=name,
        short_line=short_line,
        event=_event(soup, data),
        prizes=prizes,
        prize_state=(
            HEDERA_PRIZE
            if any(HEDERA_PRIZE_LINE.match(prize.line) for prize in prizes)
            else OTHER_PRIZE
            if prizes
            else NO_PRIZE
        ),
        links=links,
        sections=sections,
        hedera_ids=tuple(find_ids(*(section.text for section in sections), *targets)),
        has_video=any(video.get(key) for key in ("file", "muxUrl", "youtubeId")),
        parser=PARSER_VERSION,
        people_words_hidden=hidden_in_the_line + hidden_in_the_texts + hidden_in_the_links,
    )


def _project_data(soup: BeautifulSoup, site_key: str) -> dict:
    """The object of the page data that holds this project. Its scores are left alone."""
    found = [
        candidate
        for candidate in objects_with_key(page_data_text(soup), "tagline")
        if f"{candidate.get('slug')}-{candidate.get('uuid')}" == site_key
    ]
    if not found or any(candidate != found[0] for candidate in found):
        raise PageShapeChanged(
            f"the data of the page holds the project of this address {len(found)} time(s), "
            "and not once"
        )
    return found[0]


def _header(soup: BeautifulSoup, data: dict) -> tuple[Tag, str, str]:
    """The header of the project, its name and its short line."""
    for header in soup.find_all("header"):
        title = header.find("h1")
        if isinstance(title, Tag):
            break
    else:
        raise PageShapeChanged("the page has no header with a name in it")
    name = squash(title.get_text())
    if not name or name != _text(data.get("name")):
        raise PageShapeChanged("the name in the header is not the name in the data of the page")
    following = title.find_next_sibling()
    if not isinstance(following, Tag) or following.name != "p":
        raise PageShapeChanged("the name in the header is not followed by a short line")
    short_line = squash(following.get_text())
    if short_line != _text(data.get("tagline")):
        raise PageShapeChanged("the short line of the header is not the one in the data")
    return header, name, short_line


def _links(header: Tag) -> tuple[tuple[Link, ...], int]:
    """The links of the header that lead out of the site, with the words of each one, and how
    many words about people were hidden in them.

    A link that leads to a profile site is kept without its address: the tool cannot tell a
    bot of the project from a person there.
    """
    links: list[Link] = []
    hidden = 0
    for anchor in header.find_all("a", href=True):
        url = str(anchor["href"]).strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        words = squash(anchor.get_text())
        kind = _LINK_LABELS.get(words.lower(), OTHER_LINK)
        label, hidden_in_the_words = hide_in_text(words)
        site = profile_site(url)
        links.append(Link(kind, None, label, hidden_on=site) if site else Link(kind, url, label))
        hidden += hidden_in_the_words + (site is not None)
    return tuple(links), hidden


def _event(soup: BeautifulSoup, data: dict) -> EventRef:
    headings = _titles(soup, "created at")
    link = headings[0].find_next_sibling() if len(headings) == 1 else None
    if not isinstance(link, Tag) or link.name != "a":
        raise PageShapeChanged('the title "Created At" is not followed by a link, once')
    href = str(link.get("href", ""))
    slug = href.removeprefix("/events/").strip("/").split("/")[0]
    event = _dict(data.get("event"))
    if not href.startswith("/events/") or not slug or slug != _text(event.get("slug")):
        raise PageShapeChanged("the event of the page is not the event in its data")
    return EventRef(
        site=SITE,
        slug=slug,
        name=squash(link.get_text()),
        starts_at=_text(event.get("startTime")) or None,
    )


def _sections(soup: BeautifulSoup) -> tuple[tuple[Section, ...], list[Tag], int]:
    """The two texts of the page, the boxes that hold them, and how many words about people
    were hidden in them.

    A title that a team wrote inside a text is not a title of the page, also when it uses the
    same words: a title inside a box that was already taken is passed over.
    """
    sections: list[Section] = []
    boxes: list[Tag] = []
    hidden = 0
    for heading in soup.find_all("h3"):
        kind = _SECTION_TITLES.get(squash(heading.get_text()).lower())
        if kind is None or any(parent is box for parent in heading.parents for box in boxes):
            continue
        box = heading.find_next_sibling()
        if not isinstance(box, Tag):
            raise PageShapeChanged(f"no text follows the title of the part {kind!r}")
        boxes.append(box)
        hidden += hide_in_box(box)  # before the text is copied: no later step sees a person
        sections.append(Section(kind, squash(heading.get_text()), tuple(blocks_of(box))))
    if [section.kind for section in sections] != [DESCRIPTION, HOW_ITS_MADE]:
        raise PageShapeChanged(
            'the page does not have the titles "Project Description" and "How it\'s Made", '
            "once each and in this order"
        )
    return tuple(sections), boxes, hidden
