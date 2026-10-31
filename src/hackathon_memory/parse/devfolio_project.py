"""One Devfolio project, as its saved answer holds it (collect/devfolio.py), read into the facts of
a card (design 4.1), the way parse/ethglobal_page.py reads a page of ETHGlobal's showcase.

What is kept, word for word: the name, the short line, each titled text that the team wrote under
the questions of its event, the team's own words for each track that it entered, and the names
of the technologies that it lists. The questions themselves, written by the event, are not the
team's text and are left out. A text under a title about the team is cut, and handles, addresses
and links to profiles are hidden (parse/markdown.py, parse/people.py, design rule 11).

The prizes are the prizes that Devfolio lists as won. A prize belongs to the track whose name it
carries (the longest such name), and the sponsor of that track, from the event's own data,
decides whether it is a prize of Hedera: Devfolio files some prizes of a track under another
sponsor, such as "Organizer" (31 October 2026).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from hackathon_memory.collect.devfolio import HEDERA, SITE, Event, project_page
from hackathon_memory.parse.blocks import CODE, ITEM, PARAGRAPH, TITLE, Block, squash
from hackathon_memory.parse.ethglobal_page import PageShapeChanged
from hackathon_memory.parse.hedera_ids import find_ids
from hackathon_memory.parse.markdown import hide_in_markdown, is_team_title
from hackathon_memory.parse.people import hide_in_text, profile_site
from hackathon_memory.parse.project import (
    CODE_LINK,
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

PARSER_VERSION = "devfolio-project-1"
# The kinds of a section: a text under a question of the event, the team's words for a track
# that it entered, and the technologies that it lists.
TEXT, TRACK, TECHNOLOGIES = "devfolio_text", "devfolio_track", "technologies"
_CODE_HOSTS = frozenset({"github.com", "gitlab.com", "bitbucket.org"})
_TITLE = re.compile(r"^(#{1,6})\s+(.*)$")
_ITEM = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
_YEAR = re.compile(r"\s+\d{4}$")  # the organiser is the event's name without its year


def markdown_blocks(text: str) -> tuple[Block, ...]:
    """The blocks of a text written in Markdown: its titles, items, code and paragraphs, with
    their words as written (only the marks of Markdown at the start of a line go)."""
    blocks: list[Block] = []
    paragraph: list[str] = []
    code: list[str] = []
    in_code = False

    def close() -> None:
        if paragraph:
            blocks.append(Block(PARAGRAPH, squash(" ".join(paragraph))))
            paragraph.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                blocks.append(Block(CODE, "\n".join(code)))
                code.clear()
            else:
                close()
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
        elif not stripped:
            close()
        elif title := _TITLE.match(stripped):
            close()
            blocks.append(Block(TITLE, squash(title.group(2)), len(title.group(1))))
        elif item := _ITEM.match(line):
            close()
            depth = 1 + len(item.group(1).expandtabs(4)) // 2
            blocks.append(Block(ITEM, squash(item.group(2)), depth))
        else:
            paragraph.append(stripped)
    if code:
        blocks.append(Block(CODE, "\n".join(code)))
    close()
    return tuple(block for block in blocks if block.text.strip())


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _sections(project: dict) -> tuple[tuple[Section, ...], int, int]:
    """The titled texts, the team's words for each track, and the technologies; how many words
    about people were hidden, and how many texts about the team were cut."""
    sections: list[Section] = []
    hidden = cut = 0
    for item in project.get("description") or []:
        if not isinstance(item, dict):
            continue
        title, content = squash(_text(item.get("title"))), _text(item.get("content"))
        if not content.strip():
            continue
        if is_team_title(title):
            cut += 1
            continue
        kept = hide_in_markdown(content)
        hidden += kept.words_hidden
        cut += kept.team_parts_cut
        blocks = markdown_blocks(kept.text)
        if blocks:
            sections.append(Section(TEXT, title, blocks))
    for track in project.get("prize_tracks") or []:
        own = (track.get("project_tracks") or {}) if isinstance(track, dict) else {}
        words = _text(own.get("description") if isinstance(own, dict) else None)
        if not words.strip():
            continue
        kept = hide_in_markdown(words)
        hidden += kept.words_hidden
        blocks = markdown_blocks(kept.text)
        if blocks:
            sections.append(Section(TRACK, f"Tracks applied: {squash(_text(track.get('name')))}",
                                    blocks))  # fmt: skip
    tags = [squash(_text(tag.get("name"))) for tag in project.get("hashtags") or []
            if isinstance(tag, dict) and _text(tag.get("name")).strip()]  # fmt: skip
    if tags:
        sections.append(Section(TECHNOLOGIES, "Technologies used",
                                (Block(PARAGRAPH, ", ".join(tags)),)))  # fmt: skip
    return tuple(sections), hidden, cut


def _links(text: str) -> tuple[tuple[Link, ...], int]:
    """The project's links, which Devfolio gives as one list with commas and no words: code on a
    code host, any other link as it is; a link to a profile keeps its site only."""
    links: list[Link] = []
    hidden = 0
    for url in (part.strip() for part in text.split(",")):
        if not url.lower().startswith(("http://", "https://")):
            continue
        host = (urlsplit(url).hostname or "").removeprefix("www.")
        site = profile_site(url)
        if site:
            links.append(Link(OTHER_LINK, None, site, hidden_on=site))
            hidden += 1
        else:
            links.append(Link(CODE_LINK if host in _CODE_HOSTS else OTHER_LINK, url, host))
    return tuple(links), hidden


def _prizes(project: dict, event: Event | None, organiser: str) -> tuple[Prize, ...]:
    """The prizes won, each with the track whose name it carries and that track's sponsor. A prize
    that no track names, such as "Winner", is the event's own: its sponsor is the organiser."""
    tracks = sorted(event.tracks if event else (), key=lambda track: len(track.name), reverse=True)
    prizes: list[Prize] = []
    for item in project.get("prizes") or []:
        name = squash(_text(item.get("name") if isinstance(item, dict) else None))
        if not name:
            continue
        track = next((one for one in tracks if one.name and one.name.lower() in name.lower()),
                     None)  # fmt: skip
        place = name.split(":", 1)[0].strip() if track and ":" in name else ""
        sponsor = track.sponsor if track and track.sponsor else organiser
        prizes.append(Prize(sponsor=sponsor, sponsor_id=None,
                            track=track.name if track else name, award=place or name,
                            kind=None, pool=name.endswith("Prize(s)"), line=name))  # fmt: skip
    return tuple(prizes)


def read_devfolio_project(body: bytes, page: str, events: Mapping[str, Event]) -> ProjectPage:
    """Everything that a card takes from the saved answer of one project (at the address `page`
    of the data service); `events` are the events of the find."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise PageShapeChanged("the saved answer is not JSON") from None
    project = data.get("project") if isinstance(data, dict) else None
    event = data.get("hackathon") if isinstance(data, dict) else None
    if not isinstance(project, dict) or not isinstance(event, dict):
        raise PageShapeChanged("the saved answer has no project or no event")
    name, slug, event_slug = (_text(project.get("name")), _text(project.get("slug")),
                              _text(event.get("slug")))  # fmt: skip
    if not (name and slug and event_slug):
        raise PageShapeChanged("the project has no name, or no short name, or no event")
    known = events.get(event_slug)
    short_line, hidden_in_the_line = hide_in_text(squash(_text(project.get("tagline"))))
    sections, hidden_in_the_texts, _ = _sections(project)
    links, hidden_in_the_links = _links(_text(project.get("links")))
    event_name = squash(_text(event.get("name"))) or event_slug
    prizes = _prizes(project, known, _YEAR.sub("", event_name) or event_name)
    targets = [link.url for link in links if link.url]
    return ProjectPage(
        site=SITE,
        page=project_page(slug),
        site_key=slug,
        name=squash(name),
        short_line=short_line,
        event=EventRef(
            SITE,
            event_slug,
            squash(_text(event.get("name"))) or event_slug,
            known.starts_at if known else None,
        ),  # fmt: skip
        prizes=prizes,
        prize_state=(
            HEDERA_PRIZE
            if any(HEDERA.search(prize.sponsor) for prize in prizes)
            else OTHER_PRIZE
            if prizes
            else NO_PRIZE
        ),
        links=links,
        sections=sections,
        hedera_ids=tuple(find_ids(*(section.text for section in sections), *targets)),
        has_video=bool(_text(project.get("video_url")).strip()),
        parser=PARSER_VERSION,
        people_words_hidden=hidden_in_the_line + hidden_in_the_texts + hidden_in_the_links,
    )
