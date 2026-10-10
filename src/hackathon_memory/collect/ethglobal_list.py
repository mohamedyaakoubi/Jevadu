"""One page of ETHGlobal's showcase list, filtered by the partner Hedera.

The showcase has a filter by partner: /showcase?partners=hedera lists the projects that are tied
to Hedera, 33 for each page. Most of them took no prize. This module reads one such page and
says, for each project, where its own page is and which sponsors gave it a prize.

What a page of the list looks like (pages 1, 2 and 3 were read on 10 October 2026):

* 33 cards. Each card is a link to a project page, /showcase/<name>-<id>.
* A link to the next page of the list, while there is one.
* The data of the page as text in scripts (pagedata.py). One object holds the number of the
  page ("currentPage") and the records of the projects ("projects"). A record has a name, a
  short line, the event, and "prizes". A prize names its sponsor by a short id and a logo, and
  not by a name. A record holds nothing about a person.

Three things are taken from a page: the address of each project, the name of its event, and the
ids of the sponsors of its prizes. Nothing else is read out, and the page is never saved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urljoin, urlsplit

from bs4 import BeautifulSoup

from hackathon_memory.collect.ethglobal import PROJECT_PAGE_PATH, SITE
from hackathon_memory.collect.pagedata import objects_with_key, page_data_text

LIST_PATH = "/showcase"
PARTNER = "hedera"
MAX_LIST_PAGE = 999

_PAGE_NUMBER = re.compile(r"^[1-9][0-9]{0,2}$")
_SPONSOR_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_EVENT_NAME_LENGTH = 120


class ListShapeChanged(Exception):
    """A page of the list is not shaped as expected. The message holds no text of the page."""


@dataclass(frozen=True)
class ListedProject:
    page: str  # the address of the project page
    event: str  # the name of the event, as the list gives it
    sponsors: tuple[str, ...]  # the ids of the sponsors of its prizes. Empty: it took no prize.


@dataclass(frozen=True)
class ListPage:
    number: int
    projects: tuple[ListedProject, ...]
    has_next: bool  # the page links to the page after it


def list_url(page: int) -> str:
    """The address of one page of the list. The first page has no page number, as on the site."""
    if not 1 <= page <= MAX_LIST_PAGE:
        raise ValueError("a page of the list has a number from 1 to 999")
    first = f"https://{SITE}{LIST_PATH}?partners={PARTNER}"
    return first if page == 1 else f"{first}&page={page}"


def list_page_number(url: str) -> int | None:
    """The number of the page if `url` is a page of this list and nothing more, else None."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != SITE or parts.fragment:
        return None
    if parts.port not in (None, 443) or parts.username or parts.password:
        return None
    if parts.path.rstrip("/") != LIST_PATH:
        return None
    try:
        pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    query = dict(pairs)
    if len(query) != len(pairs) or query.get("partners") != PARTNER:
        return None  # a name written twice, or another partner, or no filter at all
    if set(query) - {"partners", "page"}:
        return None
    number = query.get("page", "1")
    return int(number) if _PAGE_NUMBER.match(number) else None


def is_list_url(url: str) -> bool:
    return list_page_number(url) is not None


def read_list_page(html: bytes) -> ListPage:
    """What one page of the list says. Raises ListShapeChanged when the page is not as expected."""
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "lxml")
    holders = objects_with_key(page_data_text(soup), "currentPage")
    if len(holders) != 1:
        raise ListShapeChanged(
            f"the data of the page holds the number of the page {len(holders)} times, not once"
        )
    number, records = holders[0].get("currentPage"), holders[0].get("projects")
    if type(number) is not int or not 1 <= number <= MAX_LIST_PAGE or not isinstance(records, list):
        raise ListShapeChanged("the data of the page has no page number or no list of projects")

    hrefs = [
        urljoin(f"https://{SITE}{LIST_PATH}", str(a["href"])) for a in soup.find_all("a", href=True)
    ]
    cards = {urlsplit(href).path.rstrip("/") for href in hrefs if _is_project_link(href)}
    projects = tuple(_listed(record) for record in records)
    without_card = sum(1 for project in projects if urlsplit(project.page).path not in cards)
    if without_card:
        raise ListShapeChanged(
            f"{without_card} project(s) of the data have no card in the page: the data may not "
            "be the list that the page shows"
        )
    has_next = any(list_page_number(href) == number + 1 for href in hrefs)
    return ListPage(number=number, projects=projects, has_next=has_next)


def _is_project_link(href: str) -> bool:
    parts = urlsplit(href)
    return (
        parts.hostname == SITE
        and not parts.query
        and bool(PROJECT_PAGE_PATH.match(parts.path.rstrip("/")))
    )


def _listed(record: object) -> ListedProject:
    if not isinstance(record, dict):
        raise ListShapeChanged("a project of the list is not a record")
    slug, short_id, prizes = record.get("slug"), record.get("uuid"), record.get("prizes")
    if not isinstance(slug, str) or not isinstance(short_id, str) or not isinstance(prizes, list):
        raise ListShapeChanged("a project of the list has no name part, no id or no prizes part")
    path = f"{LIST_PATH}/{slug}-{short_id}"
    if not PROJECT_PAGE_PATH.match(path):
        raise ListShapeChanged(
            "the name part and the id of a project do not give a project address"
        )
    event = record.get("event")
    event_name = event.get("name") if isinstance(event, dict) else None
    if not isinstance(event_name, str) or not event_name.strip():
        raise ListShapeChanged("a project of the list does not name its event")
    sponsors = tuple(dict.fromkeys(_sponsor_id(prize) for prize in prizes))
    return ListedProject(
        page=f"https://{SITE}{path}",
        event=" ".join(event_name.split())[:_EVENT_NAME_LENGTH],
        sponsors=sponsors,
    )


def _sponsor_id(prize: object) -> str:
    """The id of the organisation that gave the prize: prize / sponsor / organization / uuid."""
    value: object = prize
    for key in ("prize", "sponsor", "organization", "uuid"):
        value = value.get(key) if isinstance(value, dict) else None
    if not isinstance(value, str) or not _SPONSOR_ID.match(value):
        raise ListShapeChanged("a prize of the list does not name its sponsor by an id")
    return value
