"""What the parser gives for one project page, whatever the site (design 4.1, first row).

These are the facts of a card that come from the page itself: the name, the short line, the
event, the prizes, the links, the texts as they stand, and the Hedera ids. Nothing here is
written by a model, and nothing here is about a person (design rule 11).
"""

from __future__ import annotations

from dataclasses import dataclass

from hackathon_memory.parse.blocks import Block, plain_text
from hackathon_memory.parse.hedera_ids import FoundId

# What a project took at its event. A card says which of the three it is.
HEDERA_PRIZE = "hedera_prize"
OTHER_PRIZE = "other_prize"  # a prize of another sponsor only
NO_PRIZE = "no_prize"

# The kinds of a link.
CODE_LINK = "code"
DEMO_LINK = "demo"
OTHER_LINK = "other"


@dataclass(frozen=True)
class EventRef:
    """The event of a project, as its page names it."""

    site: str
    slug: str  # the short name that the site gives the event
    name: str
    starts_at: str | None  # the start of the event as the page gives it, or None


@dataclass(frozen=True)
class Prize:
    """One prize of a project. `line` is what the page shows. The rest is the page's data."""

    sponsor: str
    sponsor_id: str | None  # the id that the site gives the sponsor
    track: str  # the name of the prize
    award: str  # what was won in it: a place, or the name of the prize once more
    kind: str | None  # the site's own word for the kind of prize
    pool: bool  # a prize that is shared by all the projects that meet its conditions
    line: str


@dataclass(frozen=True)
class Link:
    """A link of a project. It has its address, or the site of an address that is hidden."""

    kind: str  # code, demo or other
    # None when the address is hidden: it leads to a profile on a social site and could name a
    # person (people.py). A card then sends the reader to the page of the project.
    url: str | None
    label: str  # the words of the link on the page
    hidden_on: str | None = None  # the site of a hidden address, such as "t.me"


@dataclass(frozen=True)
class Section:
    """A titled text of the page, copied block by block."""

    kind: str
    title: str  # as the page writes it
    blocks: tuple[Block, ...]

    @property
    def text(self) -> str:
        return plain_text(self.blocks)


@dataclass(frozen=True)
class ProjectPage:
    site: str
    page: str  # the address of the page
    site_key: str  # the name that the site gives the project: the last part of the address
    name: str
    short_line: str
    event: EventRef
    prizes: tuple[Prize, ...]
    prize_state: str  # HEDERA_PRIZE, OTHER_PRIZE or NO_PRIZE
    links: tuple[Link, ...]
    sections: tuple[Section, ...]
    hedera_ids: tuple[FoundId, ...]
    has_video: bool
    parser: str  # the version of the parser that read the page
    # How many handles, addresses and links to profiles were hidden, in the texts and among
    # the links (people.py).
    people_words_hidden: int = 0

    def section(self, kind: str) -> Section | None:
        return next((section for section in self.sections if section.kind == kind), None)

    def link(self, kind: str) -> str | None:
        """The first address of this kind that is not hidden."""
        return next((link.url for link in self.links if link.kind == kind and link.url), None)
